"""首次订阅 NF 优先流程编排器（状态机驱动）。

设计对应设计文档第 7-8 章，主路径按第 13 章实测结论修正为 **NF 订阅驱动**：
- 每次 advance() 只执行一个阶段动作并原子推进状态（CAS）。
- 主路径：NF 健康预检 → POST /subscriptions/add（NF 执行全量搜索+转存）→
  轮询 /subscriptions/info 的 local_episodes 至稳定 → POST /subscriptions/remove
  交还追更主权给 MP/PT → 触发宿主定向补搜释放。
- 所有失败/超时路径最终都经过 RELEASING：先尽力移除 NF 订阅（避免双轨追更），
  再触发宿主定向补搜（SubscribeChain().search(sid=..., manual=True)），
  保证订阅不长期停滞。
- 宿主无原生 gate 时（当前状态）以竞速模式运行，仅记录 gate_capability。
- 终态按 release_reason 区分：pipeline_done→NATIVE_REFRESH_ALLOWED，
  no_match/search_failed→NO_MATCH，transfer_failed/transfer_timeout→TRANSFER_FAILED，
  timeout→TIMEOUT_RELEASED。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import selection
from .ports import (
    CmsNotifyPort,
    GateCapability,
    MediaStatePort,
    NativeRefreshGate,
    NativeReleasePort,
    NextfindPort,
)
from .selection import SelectionResult
from .state import FirstNFTask, TaskState
from .store import JsonTaskStore

#: 默认超时（秒）
DEFAULT_TOTAL_TIMEOUT = 5400      # 任务总期限
DEFAULT_SEARCH_TIMEOUT = 300      # NF 搜索
DEFAULT_TRANSFER_TIMEOUT = 3600   # 转存轮询（遗留直转存路径）
DEFAULT_GATE_TTL = 1800           # 闸门占位 TTL（进程内）
DEFAULT_GRAB_SETTLE = 300         # NF 全量抓取无集入库的判定窗口（超过则视为无资源）
DEFAULT_GRAB_TIMEOUT = 1800       # NF 全量抓取总等待上限
MAX_NF_RETRIES = 3                # NF 暂态错误重试上限
MAX_RELEASE_ATTEMPTS = 5          # 释放重试上限

#: release_reason → 终态映射
_TERMINAL_BY_REASON: Dict[str, TaskState] = {
    "pipeline_done": TaskState.NATIVE_REFRESH_ALLOWED,
    "no_match": TaskState.NO_MATCH,
    "search_failed": TaskState.NO_MATCH,
    "transfer_failed": TaskState.TRANSFER_FAILED,
    "transfer_timeout": TaskState.TRANSFER_FAILED,
    "timeout": TaskState.TIMEOUT_RELEASED,
}


class Orchestrator:
    """任务状态机：事件入口 + 阶段推进 + 看门狗。"""

    def __init__(
        self,
        store: JsonTaskStore,
        *,
        gate: NativeRefreshGate,
        nextfind: NextfindPort,
        release: NativeReleasePort,
        media_state: Optional[MediaStatePort] = None,
        cms: Optional[CmsNotifyPort] = None,
        config: Optional[Dict[str, Any]] = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.gate = gate
        self.nextfind = nextfind
        self.native_release = release
        self.media_state = media_state
        self.cms = cms
        self.config = config or {}
        self.clock = clock
        self._lock = threading.Lock()

    # ------------------------------------------------------------- 事件入口

    def on_subscribe_added(self, task: FirstNFTask) -> FirstNFTask:
        """登记新任务；幂等键命中时返回既有任务（去重）。"""
        with self._lock:
            tasks = self.store.load()
            existing = tasks.get(task.task_key)
            if existing is not None:
                return existing  # 重复事件：幂等忽略
            task.deadline_at = task.created_at + float(
                self.config.get("total_timeout", DEFAULT_TOTAL_TIMEOUT)
            )
            task.gate_capability = self.gate.capability().value
            task.mark_phase("created")
            self._persist(tasks, task)
            return task

    # ------------------------------------------------------------- 阶段推进

    def advance(self, task: FirstNFTask) -> FirstNFTask:
        """推进一个阶段；返回更新后的任务（引用可能已变化）。"""
        if not task.is_active:
            return task
        now = self.clock()
        if (
            task.deadline_at
            and now >= task.deadline_at
            and task.state != TaskState.RELEASING
        ):
            # 超时且尚未进入释放：强制走释放路径（RELEASING 后不再被超时检查拦截）
            return self._to_release(task, now, reason="timeout")

        handlers: Dict[TaskState, Callable[[FirstNFTask, float], FirstNFTask]] = {
            TaskState.ELIGIBILITY_CHECK: self._step_gate,
            TaskState.GATE_ACQUIRING: self._step_nf_search,
            TaskState.NF_SEARCHING: self._step_nf_search,
            TaskState.NF_GRABBING: self._step_nf_grab,
            # 遗留直转存路径（v1.0.7 及以前的任务恢复时按原逻辑收敛）
            TaskState.MATCH_SELECT: self._step_match,
            TaskState.TRANSFER_SUBMIT: self._step_transfer_poll,
            TaskState.TRANSFER_POLL: self._step_transfer_poll,
            TaskState.LIBRARY_REFRESH: self._step_release_lib,
            TaskState.RELEASING: self.release,
        }
        handler = handlers.get(task.state)
        if handler is None:
            return task
        return handler(task, now)

    def run_until_blocked(self, task: FirstNFTask) -> FirstNFTask:
        """连续推进直至需要等待（轮询/重试阶段）或终态。"""
        guard = 0
        while task.is_active and guard < 20:
            before = task.state
            task = self.advance(task)
            if task.state == before:
                break  # 等待外部重试（轮询未完成或释放重试中）
            guard += 1
        return task

    # ------------------------------------------------------------- 持久化

    def _persist(self, tasks: Dict[str, FirstNFTask], task: FirstNFTask) -> None:
        """CAS 持久化：版本号 +1 后保存。"""
        task.state_version += 1
        task.touch(self.clock())
        tasks[task.task_key] = task
        self.store.save(tasks)

    def _transition(self, task: FirstNFTask, state: TaskState, now: float) -> FirstNFTask:
        """安全状态迁移并持久化。"""
        task.state = state
        task.mark_phase(state.value, now)
        with self._lock:
            tasks = self.store.load()
            self._persist(tasks, task)
        return task

    # ------------------------------------------------------------- 各阶段

    def _step_gate(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """GATE_ACQUIRING：宿主 gate 不可用时进入竞速模式。"""
        ttl = float(self.config.get("gate_ttl", DEFAULT_GATE_TTL))
        lease = self.gate.acquire(task.subscribe_id, ttl)
        task.gate_token = lease.token if lease else None
        task.gate_expires_at = lease.expires_at if lease else None
        task.gate_capability = self.gate.capability().value
        if (
            self.config.get("blocking_mode") == "strict"
            and self.gate.capability() != GateCapability.AVAILABLE
        ):
            # 严格模式：宿主无 gate 能力时拒绝运行 NF 流程（不阻塞也不竞速）
            return self._transition(task, TaskState.IGNORED, now)
        return self._transition(task, TaskState.GATE_ACQUIRING, now)

    def _step_nf_search(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """GATE_ACQUIRING/NF_SEARCHING：NF 健康预检后添加 NF 订阅触发全量抓取。

        设计文档 6.1 将"NF 适配器健康"列为准入条件；预检不支持
        （quota() 返回 None）时跳过，保证旧适配器与测试替身行为不变。

        设计文档第 13 章实测结论：NF 的资源管线由 NF 订阅驱动，
        /resources/search 只返回已完成匹配的待转存候选（未命中雷达缓存
        的标题返回 0）。因此这里直接 POST /subscriptions/add，由 NF 执行
        全量搜索+转存，随后进入 NF_GRABBING 轮询 local_episodes。
        """
        try:
            quota = self._run_async(self.nextfind.quota())
        except Exception as error:
            return self._handle_nf_health(task, error, now)
        if quota is not None:
            task.last_error = ""  # 预检通过，清理历史健康错误
        try:
            accepted = self._run_async(
                self.nextfind.add_subscription(task.media_id, "tv", task.title)
            )
        except Exception as error:
            return self._handle_nf_error(task, error, now)
        if not accepted:
            return self._handle_nf_error(task, NextfindRejected(), now)
        task.nf_retries = 0
        task.nf_subscription_added = True
        task.nf_subscription_added_at = now
        task.nf_subscription_removed = False
        task.nf_grab_last_episodes = None
        task.nf_grab_stable_polls = 0
        return self._transition(task, TaskState.NF_GRABBING, now)

    def _step_nf_grab(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """NF_GRABBING：轮询 NF 侧 local_episodes，等待全量搜索+转存完成。

        - 完成：local_episodes > 0 且连续两次轮询不变（抓取已稳定）→ LIBRARY_REFRESH。
        - 无资源：超过 nf_grab_settle 仍无任何 local_episodes → no_match 释放。
        - 超时：超过 nf_grab_timeout → timeout 释放。
        所有退出路径都经 _to_release（内部会移除 NF 订阅）。
        """
        started = task.nf_subscription_added_at or now
        settle = float(self.config.get("nf_grab_settle", DEFAULT_GRAB_SETTLE))
        timeout = float(self.config.get("nf_grab_timeout", DEFAULT_GRAB_TIMEOUT))
        try:
            current = self._run_async(self.nextfind.library_progress(task.media_id, "tv"))
        except Exception as error:
            return self._handle_nf_error(task, error, now)
        if current is not None and current > 0:
            if task.nf_grab_last_episodes == current:
                task.nf_grab_stable_polls += 1
            else:
                task.nf_grab_last_episodes = current
                task.nf_grab_stable_polls = 0
            if task.nf_grab_stable_polls >= 1:
                # 连续两次读数一致：本次全量抓取已稳定
                task.nf_grab_completed_at = now
                task.nf_transfer_confirmed_at = now
                return self._transition(task, TaskState.LIBRARY_REFRESH, now)
            return task  # 等待下一次轮询确认稳定
        # 尚无任何入库集：settle 窗口内继续等待，超窗判定无资源
        if now - started >= timeout:
            task.last_error = "nf_grab_timeout"
            self._enrich_with_nf_logs(task)
            return self._to_release(task, now, reason="timeout")
        if now - started >= settle:
            task.last_error = "no_match:nf_grab_no_episodes"
            return self._to_release(task, now, reason="no_match")
        return task  # 保持 NF_GRABBING，等待下一次推进

    def _step_match(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """MATCH_SELECT：候选择优。"""
        candidates: List[Dict[str, Any]] = task.__dict__.pop("_nf_candidates", None) or []
        result: SelectionResult = selection.select_candidate(
            candidates,
            season=task.season,
            resolution_preference=self.config.get("resolution_preference") or [],
            whitelist=self.config.get("whitelist") or [],
            blacklist=self.config.get("blacklist") or [],
            min_score=float(self.config.get("min_score", 0.35)),
        )
        if result.selected is None:
            task.last_error = f"no_match:{result.reason}"
            return self._to_release(task, now, reason="no_match")
        task.nf_selected_slug = result.selected.get("slug")
        task.nf_selected_title = result.selected.get("title")
        return self._transition(task, TaskState.MATCH_SELECT, now)

    def _step_transfer_submit(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """TRANSFER_SUBMIT：取 NF 基线进度后提交转存。"""
        try:
            baseline = self._run_async(self.nextfind.library_progress(task.media_id, "tv"))
        except Exception:
            baseline = None
        task.nf_baseline_local_episodes = baseline
        try:
            accepted = self._run_async(
                self.nextfind.submit_transfer(
                    task.nf_selected_slug or "",
                    str(self.config.get("target_folder") or ""),
                )
            )
        except Exception as error:
            return self._handle_nf_error(task, error, now)
        if not accepted:
            return self._handle_nf_error(task, NextfindRejected(), now)
        task.nf_transfer_submitted_at = now
        return self._transition(task, TaskState.TRANSFER_SUBMIT, now)

    def _step_transfer_poll(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """TRANSFER_POLL：确认转存完成（主信号 local_episodes 增长，兜底 history）。"""
        if task.state == TaskState.TRANSFER_SUBMIT:
            # 提交后首次轮询：归一化为 TRANSFER_POLL
            task = self._transition(task, TaskState.TRANSFER_POLL, now)
        timeout = float(self.config.get("transfer_timeout", DEFAULT_TRANSFER_TIMEOUT))
        if (
            task.nf_transfer_submitted_at
            and now - task.nf_transfer_submitted_at > timeout
        ):
            task.last_error = "transfer_timeout"
            self._enrich_with_nf_logs(task)
            return self._to_release(task, now, reason="transfer_timeout")
        # 主确认：NF 侧 local_episodes 相对基线增长
        try:
            current = self._run_async(self.nextfind.library_progress(task.media_id, "tv"))
        except Exception as error:
            return self._handle_nf_error(task, error, now)
        baseline = task.nf_baseline_local_episodes
        if current is not None and baseline is not None and current > baseline:
            task.nf_transfer_confirmed_at = now
            return self._transition(task, TaskState.LIBRARY_REFRESH, now)
        # 兜底确认：转存历史 slug 命中
        try:
            history = self._run_async(
                self.nextfind.transfer_history(task.nf_selected_slug or "")
            )
            if selection.history_confirms_transfer(
                history,
                slug=task.nf_selected_slug or "",
                title=task.nf_selected_title,
                after_ts=task.nf_transfer_submitted_at,
            ):
                task.nf_transfer_confirmed_at = now
                return self._transition(task, TaskState.LIBRARY_REFRESH, now)
        except Exception:
            pass  # 兜底确认失败不影响下一轮轮询
        return task  # 未完成：保持 TRANSFER_POLL，等待下一次推进

    def _step_release_lib(self, task: FirstNFTask, now: float) -> FirstNFTask:
        """LIBRARY_REFRESH：媒体库扫描（可选）+ CMS 联动整理（可选），随后进入 RELEASING。

        两者均失败非致命：CMS 不可用不得阻塞释放与 PT 接管。
        """
        if self.media_state is not None and self.config.get("library_scan_on_transfer"):
            try:
                self._run_async(self.media_state.refresh_library())
            except Exception as error:
                task.last_error = f"library_refresh_non_fatal:{error}"
        self._trigger_cms_organize(task, now)
        return self._to_release(task, now, reason="pipeline_done")

    def _trigger_cms_organize(self, task: FirstNFTask, now: float) -> None:
        """转存完成后通知 CMS 触发整理（可选、非致命）。

        对应设计需求「转存后触发 CMS 联动整理」；CMS 不可用仅记录 last_error。
        """
        if self.cms is None or not self.config.get("cms_enabled"):
            return
        try:
            ok = self._run_async(
                self.cms.trigger_organize(
                    task.title, str(self.config.get("target_folder") or "")
                )
            )
        except Exception as error:
            task.last_error = (task.last_error or "") + f" | cms_notify_failed:{error}"
            return
        if ok:
            task.cms_notified_at = now

    # ------------------------------------------------------------- 释放动作

    def release(self, task: FirstNFTask, now: Optional[float] = None) -> FirstNFTask:
        """执行释放：移除 NF 订阅 + 触发宿主定向补搜；幂等重试由看门狗驱动。"""
        now = now if now is not None else self.clock()
        if task.state != TaskState.RELEASING:
            return task
        self._remove_nf_subscription(task)  # 幂等补漏：释放重试时再尝试移除 NF 订阅
        task.release_attempts += 1
        try:
            accepted = self.native_release.trigger_native_search(task.subscribe_id)
        except Exception as error:
            accepted = False
            task.last_error = f"release_error:{error}"
        if not accepted:
            if task.release_attempts >= MAX_RELEASE_ATTEMPTS:
                return self._transition(task, TaskState.RELEASE_FAILED, now)
            return task  # 等待看门狗重试
        task.release_confirmed_at = now
        self._release_gate(task)
        terminal = _TERMINAL_BY_REASON.get(
            task.release_reason or "pipeline_done", TaskState.NATIVE_REFRESH_ALLOWED
        )
        return self._transition(task, terminal, now)

    def _release_gate(self, task: FirstNFTask) -> None:
        """释放闸门占位租约（宿主 gate 可用时同步释放）。"""
        if not task.gate_token:
            return
        try:
            self.gate.release(_LeaseShim(task.gate_token, task.gate_expires_at or 0.0))
        except Exception:
            pass

    # ------------------------------------------------------------- 错误处理

    def _handle_nf_health(self, task: FirstNFTask, error: Exception, now: float) -> FirstNFTask:
        """NF 健康预检（GET /quota）失败：有界重试；超限直接 IGNORED（不进入 NF 分支）。

        对应设计文档 6.1"NF 和 115 适配器健康"准入条件：宿主无 gate，
        跳过不阻塞原生 PT，订阅不受影响。
        """
        kind = getattr(error, "kind", "network")
        if task.nf_retries >= MAX_NF_RETRIES:
            task.last_error = f"nf_unhealthy:{kind}:{error}"
            self._enrich_with_nf_logs(task)
            return self._transition(task, TaskState.IGNORED, now)
        task.nf_retries += 1
        task.last_error = f"nf_health_retry:{kind}:{error}"
        return task  # 保持 GATE_ACQUIRING，等待下一次推进重试

    def _handle_nf_error(self, task: FirstNFTask, error: Exception, now: float) -> FirstNFTask:
        """NF 错误：暂态错误有界重试；致命或超限进入失败释放。"""
        kind = getattr(error, "kind", "network")
        if kind == "config" or task.nf_retries >= MAX_NF_RETRIES:
            task.last_error = f"nf_error:{kind}:{error}"
            self._enrich_with_nf_logs(task)
            if task.state in (TaskState.TRANSFER_SUBMIT, TaskState.TRANSFER_POLL):
                return self._to_release(task, now, reason="transfer_failed")
            return self._to_release(task, now, reason="search_failed")
        task.nf_retries += 1
        task.last_error = f"nf_retry:{kind}:{error}"
        return task  # 保持当前阶段，等待下一次推进重试

    def _enrich_with_nf_logs(self, task: FirstNFTask) -> None:
        """失败终态前拉取 NF 最近日志，富化 last_error 便于诊断（非致命）。"""
        try:
            logs = self._run_async(self.nextfind.recent_logs(10))
        except Exception:
            return
        if logs:
            tail = " / ".join(str(line).strip() for line in logs[-3:] if str(line).strip())
            if tail:
                task.last_error = (task.last_error or "") + f" | NF日志: {tail}"

    def _to_release(self, task: FirstNFTask, now: float, reason: str) -> FirstNFTask:
        """统一进入 RELEASING（记录原因）；进入前尽力移除 NF 订阅。"""
        task.release_reason = reason
        self._remove_nf_subscription(task)
        return self._transition(task, TaskState.RELEASING, now)

    def _remove_nf_subscription(self, task: FirstNFTask) -> None:
        """尽力移除 NF 订阅，交还追更主权给 MP/PT（幂等、非致命）。

        失败不阻塞释放：保留 nf_subscription_removed=False，由看门狗补漏重试。
        """
        if not task.nf_subscription_added or task.nf_subscription_removed:
            return
        try:
            ok = self._run_async(self.nextfind.remove_subscription(task.media_id, "tv"))
        except Exception as error:
            task.last_error = (task.last_error or "") + f" | nf_unsubscribe_failed:{error}"
            return
        if ok:
            task.nf_subscription_removed = True

    # ------------------------------------------------------------- 看门狗

    def watchdog(self) -> List[str]:
        """扫描全部任务：超时强制释放、释放重试、推进卡住的任务。

        :return: 本次处理的 task_key 列表（供日志/通知）
        """
        handled: List[str] = []
        for task in list(self.store.load().values()):
            if task.is_terminal:
                continue
            task = self.advance(task)  # 内部含超时检查与单阶段推进
            if task.state == TaskState.RELEASING:
                task = self.release(task)
            handled.append(task.task_key)
        self._cleanup_leaked_subscriptions()
        return handled

    def _cleanup_leaked_subscriptions(self) -> None:
        """补漏：终态任务若仍持有 NF 订阅则重试移除，避免双轨追更。"""
        tasks = self.store.load()
        changed = False
        for task in tasks.values():
            if not task.is_terminal:
                continue
            if task.nf_subscription_added and not task.nf_subscription_removed:
                self._remove_nf_subscription(task)
                if task.nf_subscription_removed:
                    changed = True
        if changed:
            self.store.save(tasks)

    # ------------------------------------------------------------- 工具

    @staticmethod
    def _run_async(coro):
        """在同步阶段内执行异步端口调用。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            # 已在运行中的事件循环（宿主事件线程等）：隔离到新循环执行
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return asyncio.run(coro)


class NextfindRejected(Exception):
    """NF 受理但拒绝（status != success）。"""

    kind = "api"


class _LeaseShim:
    """把任务记录中的 gate_token 包装为闸门释放所需的租约对象。"""

    def __init__(self, token: str, expires_at: float) -> None:
        self.token = token
        self.expires_at = expires_at
