"""首次订阅 NF 优先插件的任务状态定义与持久化任务记录。

本模块不依赖 MoviePilot 宿主，可在宿主外独立测试。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskState(str, Enum):
    """任务状态机状态，含义与设计文档第 7 / 13 章一致。

    v1.0.8 起主路径改为「NF 订阅驱动」（设计文档第 13 章实测结论）：
    新订阅到达即向 NF 添加订阅，由 NF 执行全量搜索+转存，插件轮询
    local_episodes 至稳定后移除 NF 订阅、交还追更主权给 MP/PT。
    MATCH_SELECT / TRANSFER_SUBMIT / TRANSFER_POLL 为 v1.0.7 及以前的
    直转存路径遗留状态，仅用于兼容历史持久化任务，不再进入。
    """

    ELIGIBILITY_CHECK = "eligibility_check"      # 准入判定
    GATE_ACQUIRING = "gate_acquiring"            # 申请原生刷新闸门（当前宿主不可用时为进程内占位）
    NF_SEARCHING = "nf_searching"                # NF 健康预检 + 添加 NF 订阅
    NF_GRABBING = "nf_grabbing"                  # 等待 NF 全量搜索+转存（轮询 local_episodes）
    MATCH_SELECT = "match_select"                # [遗留] 候选择优（直转存路径）
    TRANSFER_SUBMIT = "transfer_submit"          # [遗留] 提交 NF->115 转存
    TRANSFER_POLL = "transfer_poll"              # [遗留] 轮询转存完成
    LIBRARY_REFRESH = "library_refresh"          # 刷新媒体库（可选）
    RELEASING = "releasing"                      # 移除 NF 订阅 + 触发原生定向补搜
    NATIVE_REFRESH_ALLOWED = "native_refresh_allowed"  # 终态：已交还 PT 追更
    NO_MATCH = "no_match"                        # 终态：无匹配
    TRANSFER_FAILED = "transfer_failed"          # 终态：转存失败
    REFRESH_FAILED = "refresh_failed"            # 终态：库刷新失败（非致命）
    TIMEOUT_RELEASED = "timeout_released"        # 终态：超时释放
    RELEASE_FAILED = "release_failed"            # 终态：释放失败（已重试上限）
    IGNORED = "ignored"                          # 终态：不处理


#: 需要继续推进的活动状态
ACTIVE_STATES = (
    TaskState.ELIGIBILITY_CHECK,
    TaskState.GATE_ACQUIRING,
    TaskState.NF_SEARCHING,
    TaskState.NF_GRABBING,
    TaskState.MATCH_SELECT,
    TaskState.TRANSFER_SUBMIT,
    TaskState.TRANSFER_POLL,
    TaskState.LIBRARY_REFRESH,
    TaskState.RELEASING,
)

#: 所有终态
TERMINAL_STATES = (
    TaskState.NATIVE_REFRESH_ALLOWED,
    TaskState.NO_MATCH,
    TaskState.TRANSFER_FAILED,
    TaskState.REFRESH_FAILED,
    TaskState.TIMEOUT_RELEASED,
    TaskState.RELEASE_FAILED,
    TaskState.IGNORED,
)


@dataclass
class FirstNFTask:
    """一次首次订阅 NF 优先流程的任务记录（可 JSON 序列化）。"""

    # 幂等键：优先使用宿主 SubscribeAdded 事件提供的 idempotency_key
    task_key: str
    # 宿主订阅 ID
    subscribe_id: int
    # 媒体身份（TMDB 源 + TMDB ID）
    media_source: str = ""
    media_id: str = ""
    # 媒体标题/年份/季（用于日志与展示）
    title: str = ""
    year: str = ""
    season: Optional[int] = None
    # 是否为洗版订阅（判定后即 IGNORED）
    is_wash: bool = False
    # 状态机
    state: TaskState = TaskState.ELIGIBILITY_CHECK
    state_version: int = 0
    # 时间戳（epoch 秒）
    created_at: float = field(default_factory=time.time)
    deadline_at: Optional[float] = None
    updated_at: float = field(default_factory=time.time)
    # 闸门占位（当前宿主无原生 gate，仅进程内租约；HostGate 可用时替换）
    gate_token: Optional[str] = None
    gate_expires_at: Optional[float] = None
    gate_capability: str = "unknown"  # available / unavailable / unknown
    # NF 侧
    nf_baseline_local_episodes: Optional[int] = None
    nf_selected_slug: Optional[str] = None
    nf_selected_title: Optional[str] = None
    nf_transfer_submitted_at: Optional[float] = None
    nf_transfer_confirmed_at: Optional[float] = None
    nf_retries: int = 0
    # NF 订阅驱动（v1.0.8 主路径）：订阅添加/移除与全量抓取轮询
    nf_subscription_added: bool = False
    nf_subscription_added_at: Optional[float] = None
    nf_subscription_removed: bool = False
    nf_grab_last_episodes: Optional[int] = None
    nf_grab_stable_polls: int = 0
    nf_grab_completed_at: Optional[float] = None
    # CMS 联动（转存后触发整理）
    cms_notified_at: Optional[float] = None
    # 释放侧
    release_attempts: int = 0
    release_confirmed_at: Optional[float] = None
    release_reason: str = ""
    # 诊断
    last_error: str = ""
    phase_timeline: List[Dict[str, Any]] = field(default_factory=list)

    def touch(self, now: Optional[float] = None) -> None:
        """刷新更新时间戳。"""
        self.updated_at = now if now is not None else time.time()

    def mark_phase(self, phase: str, now: Optional[float] = None) -> None:
        """记录阶段时间线，用于审计与看门狗诊断。"""
        self.phase_timeline.append(
            {"phase": phase, "at": now if now is not None else time.time()}
        )

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 持久化的字典。"""
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FirstNFTask":
        """从持久化字典还原任务记录。"""
        data = dict(data)
        data["state"] = TaskState(data.get("state", TaskState.ELIGIBILITY_CHECK.value))
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def is_active(self) -> bool:
        """是否仍处于需要推进的活动状态。"""
        return self.state in ACTIVE_STATES

    @property
    def is_terminal(self) -> bool:
        """是否已进入终态。"""
        return self.state in TERMINAL_STATES
