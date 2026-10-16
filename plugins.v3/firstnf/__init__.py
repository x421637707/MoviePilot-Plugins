"""FirstNF —— 首次新增订阅优先经 NextFind 搜索网盘并转存 115 的 MoviePilot V3 插件。

宿主装配层：事件入口、端口适配、生命周期与页面。
核心状态机、判定与择优逻辑位于同目录 nfcore 子包（可在宿主外独立测试）。

已核实契约（2026-10-16，MoviePilot v3 分支 + 官方插件开发指南）：
- _PluginBase 位于 app.sdk.plugin；init_plugin/get_state/get_api/get_form/
  get_page/stop_service 为必须方法，get_command/get_service 为可选扩展点；
- EventType.SubscribeAdded 在订阅创建提交后广播，event_data 含
  subscribe_id / idempotency_key / username / mediainfo；
- SubscribeOper().get(sid=...) 只读宿主订阅（best_version=1 即洗版）；
- SubscribeChain().search(sid=..., manual=True) 为定向补搜（释放动作）；
- 调度：get_service() 周期任务 + app.sdk.scheduler.add_plugin_once_job()；
- 数据：save_data()/get_data()/get_data_path() 与 update_config()。

未核实/不存在（已在代码中显式标注，不得假定）：
- 原生订阅刷新拦截/gate 接口：V3 源码核验确认不存在，默认 NullGate 竞速模式；
- NextFind OpenAPI 合同来自第三方实测参考（unisub nextfind-api-v3，
  2026-07-22），接入前需以目标实例校准；若 nextfind 以 MP 插件形态提供，
  应替换 NextfindHttpAdapter 为其实际接口。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    from app.sdk.plugin import _PluginBase
except ImportError:  # pragma: no cover - 宿主外独立运行（测试）时的最小占位
    class _PluginBase:
        """宿主外占位基类：仅保证模块可在无 MoviePilot 环境导入。"""

        def update_config(self, config: dict) -> bool:
            """占位：宿主中由基类实现。"""
            return True

        def get_config(self) -> dict:
            """占位：宿主中由基类实现。"""
            return {}

        def save_data(self, key: str, data: Any) -> None:
            """占位：宿主中由基类实现。"""

        def get_data(self, key: str) -> Any:
            """占位：宿主中由基类实现。"""
            return None

        def get_data_path(self):
            """占位：宿主中由基类实现。"""
            from pathlib import Path

            return Path(".")

        def post_message(self, *args: Any, **kwargs: Any) -> None:
            """占位：宿主中由基类实现。"""

        def __init__(self) -> None:
            """占位初始化。"""

from .nfcore import (
    CmsWebhookAdapter,
    FileTaskStore,
    FirstNFTask,
    HostDataStore,
    NextfindHttpAdapter,
    NullGate,
    Orchestrator,
    TaskState,
    decide_first_subscription,
    normalize_cms_domain,
    normalize_nf_base_url,
)
from .nfcore.gate import HostGateAdapter
from .nfcore.ports import MediaStatePort, NativeReleasePort, NotifyPort

try:
    from app.sdk.events import eventmanager
    from app.schemas.types import EventType
except ImportError:  # pragma: no cover - 宿主外独立运行（测试）时无事件系统
    eventmanager = None
    EventType = None


def _passthrough(func: Any) -> Any:
    """直通装饰器：原样返回（宿主外或事件类型不可用时使用）。"""
    return func


def _register_event(event_type_name: str):
    """事件注册装饰器（官方 V3 指南 9.1 模式）。

    宿主内：解析 EventType 枚举并注册；
    宿主外（测试）：返回直通装饰器，保证模块可独立导入。
    """
    if eventmanager is None or EventType is None:
        return _passthrough
    event_type = getattr(EventType, event_type_name, None)
    if event_type is None:
        return _passthrough
    return eventmanager.register(event_type)


class FirstNF(_PluginBase):
    """首次订阅 NF 优先插件主类。"""

    plugin_name = "NF订阅兜底"
    plugin_desc = (
        "首次新增电视剧订阅时优先走 NextFind：向其添加订阅触发全量搜索+转存 115，"
        "入库稳定后移除 NF 订阅并交还 PT 追更，可选联动 CMS 整理；"
        "洗版订阅与后续追更不触发。"
    )
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.9"
    plugin_author = "firstnf-design"
    author_url = ""
    plugin_config_prefix = "firstnf_"
    plugin_order = 50
    auth_level = 1

    #: 默认配置（get_form 的默认模型需与此保持一致）
    DEFAULT_CONFIG: Dict[str, Any] = {
        "enabled": False,
        "nf_base_url": "",
        "nf_api_key": "",
        "target_folder": "",
        "media_types": ["电视剧"],
        "resolution_preference": ["2160P", "4K", "1080P"],
        "whitelist": [],
        "blacklist": [],
        "min_score": 0.35,
        "total_timeout": 5400,
        "search_timeout": 300,
        "transfer_timeout": 3600,
        "nf_grab_settle": 300,
        "nf_grab_timeout": 1800,
        "gate_ttl": 1800,
        "poll_interval": 60,
        "blocking_mode": "race",  # race | strict
        "library_scan_on_transfer": False,
        "cms_enabled": False,
        "cms_domain": "",
        "cms_token": "",
        "cms_webhook_path": "/api/emby/webhook",
        "notify": True,
    }

    def __init__(self) -> None:
        """初始化实例字段（不触碰宿主资源）。"""
        super().__init__()
        self._config: Dict[str, Any] = dict(self.DEFAULT_CONFIG)
        self._store = None
        self._orchestrator: Optional[Orchestrator] = None
        self._nextfind: Optional[NextfindHttpAdapter] = None
        self._active_job_keys: List[str] = []

    # ------------------------------------------------------------- 生命周期

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置并建立本次运行状态；必须可重复调用。"""
        merged = dict(self.DEFAULT_CONFIG)
        merged.update(config or {})
        self._config = merged

        # 存储：宿主 save_data/get_data；读取失败时回退数据目录文件
        self._store = HostDataStore(self)
        try:
            data_dir = self.get_data_path()
            self._fallback_store = FileTaskStore(data_dir / "tasks.json")
        except Exception:
            self._fallback_store = None

        # 端口装配：nf_base_url 自动补全 /api/openapi 前缀（官方文档约定）
        nf_url = normalize_nf_base_url(str(merged.get("nf_base_url") or ""))
        if nf_url and nf_url != str(merged.get("nf_base_url") or "").strip().rstrip("/"):
            self._log_info(f"nf_base_url 已自动补全 NextFind OpenAPI 前缀：{nf_url}")
        if nf_url and merged.get("nf_api_key"):
            self._nextfind = NextfindHttpAdapter(
                nf_url, merged["nf_api_key"],
                timeout=float(merged.get("search_timeout", 300)),
            )
        else:
            self._nextfind = None

        # CMS 联动端口装配（可选）：转存完成后通知 CMS 触发整理
        cms = None
        if merged.get("cms_enabled"):
            cms_domain = normalize_cms_domain(str(merged.get("cms_domain") or ""))
            cms_token = str(merged.get("cms_token") or "")
            if cms_domain and cms_token:
                cms = CmsWebhookAdapter(
                    cms_domain,
                    cms_token,
                    str(merged.get("cms_webhook_path") or "/api/emby/webhook"),
                )
            else:
                self._log_error(
                    "CMS 联动已启用但 cms_domain/cms_token 未配置完整，本次跳过 CMS 联动"
                )

        gate = HostGateAdapter() if merged.get("blocking_mode") == "strict" else NullGate()
        self._orchestrator = Orchestrator(
            self._store,
            gate=gate,
            nextfind=self._nextfind or _UnconfiguredNextfind(),
            release=_SubscribeReleaseAdapter(),
            media_state=_MediaServerScanAdapter() if merged.get("library_scan_on_transfer") else None,
            cms=cms,
            config=merged,
        )

        # 启动日志（可观测性：确认插件已加载及关键配置，不含密钥）
        self._log_info(
            f"插件已加载：enabled={self.get_state()}，"
            f"nf={'已配置' if self._nextfind else '未配置'}，"
            f"target_folder={merged.get('target_folder') or '-'}，"
            f"mode={merged.get('blocking_mode')}，"
            f"cms={'已启用' if cms else '未启用'}"
        )

        # 启动健康检查（延迟 5 秒，验证 NF 可达与密钥有效）
        self._schedule_startup_health_check()

        # 重启恢复：为未完成任务排队
        self._reschedule_active_tasks()

    def _schedule_startup_health_check(self) -> None:
        """注册一次性的 NF 健康检查任务（失败仅记录+通知，不阻塞）。"""
        if not self.get_state():
            return
        plugin_id = self.__class__.__name__
        try:
            from app.sdk import scheduler as scheduler_sdk

            scheduler_sdk.add_plugin_once_job(
                plugin_id, "firstnf_healthcheck", self._startup_health_check,
                "NF订阅兜底 启动健康检查", delay_seconds=5,
            )
        except Exception:
            pass  # 调度器不可用时静默跳过

    def _startup_health_check(self) -> None:
        """启动后验证 NF 可达性；失败时记录并通知。"""
        if not self._nextfind:
            self._log_info("NF 未配置（缺少地址或 API Key），首次订阅将跳过 NF 流程")
            return
        try:
            quota = Orchestrator._run_async(self._nextfind.quota())
            self._log_info(f"NF 健康检查通过：{quota}")
        except Exception as error:
            self._log_error(
                f"NF 健康检查失败：{type(error).__name__}: {error}"
                f"（地址 {self._nextfind.base_url}；首次订阅将跳过 NF 流程，订阅不受影响）"
            )
            self._notify(
                "NF订阅兜底：NextFind 不可达",
                f"健康检查失败：{type(error).__name__}: {error}\n"
                f"地址：{self._nextfind.base_url}\n"
                "请检查 nf_base_url / nf_api_key 配置。",
            )

    def get_state(self) -> bool:
        """返回插件是否启用。"""
        return bool(self._config.get("enabled", False))

    def stop_service(self) -> None:
        """取消一次性任务并释放后台资源（可重复调用）。"""
        plugin_id = self.__class__.__name__
        for job_key in list(self._active_job_keys):
            try:
                from app.sdk import scheduler as scheduler_sdk

                scheduler_sdk.remove_plugin_once_job(plugin_id, f"firstnf_{job_key}")
            except Exception:
                pass
        self._active_job_keys = []
        self._orchestrator = None
        self._nextfind = None

    # ------------------------------------------------------------- 页面与接口

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """返回配置页面与默认配置。

        页面为 Vuetify 组件 JSON，由前端 FormRender 递归渲染
        （支持 content 嵌套 / slots 具名插槽 / text 文本）。
        布局：顶部流程说明 → 卡片式分组（基础 / NextFind 连接 /
        抓取与超时 / CMS 联动 / 高级遗留参数），字段用 VRow+VCol 两列自适应。
        """

        def text_field(
            model: str,
            label: str,
            hint: str = "",
            placeholder: str = "",
            type_: str = "",
        ) -> dict:
            """构造一个文本输入字段（绑定配置模型）。"""
            props: Dict[str, Any] = {
                "model": model,
                "label": label,
                "variant": "outlined",
                "density": "comfortable",
                "hideDetails": "auto",
                "persistentPlaceholder": True,
            }
            if hint:
                props["hint"] = hint
            if placeholder:
                props["placeholder"] = placeholder
            if type_:
                props["type"] = type_
            return {"component": "VTextField", "props": props}

        def switch_field(model: str, label: str, hint: str = "") -> dict:
            """构造一个开关字段。"""
            props: Dict[str, Any] = {
                "model": model,
                "label": label,
                "color": "primary",
                "hideDetails": "auto",
                "density": "comfortable",
            }
            if hint:
                props["hint"] = hint
            return {"component": "VSwitch", "props": props}

        def select_field(model: str, label: str, items: list, hint: str = "") -> dict:
            """构造一个下拉选择字段。"""
            props: Dict[str, Any] = {
                "model": model,
                "label": label,
                "items": items,
                "variant": "outlined",
                "density": "comfortable",
                "hideDetails": "auto",
            }
            if hint:
                props["hint"] = hint
            return {"component": "VSelect", "props": props}

        def col(child: dict, md: int = 6) -> dict:
            """两列自适应栅格单元。"""
            return {"component": "VCol", "props": {"cols": 12, "md": md}, "content": [child]}

        def row(children: list) -> dict:
            """一行栅格容器。"""
            return {"component": "VRow", "props": {"dense": True}, "content": children}

        def alert(text: str, type_: str = "info", title: str = "") -> dict:
            """提示条。"""
            props: Dict[str, Any] = {
                "type": type_,
                "variant": "tonal",
                "class": "mb-3",
                "text": text,
            }
            if title:
                props["title"] = title
            return {"component": "VAlert", "props": props}

        def section(title: str, subtitle: str, children: list) -> dict:
            """卡片式分组（标题 + 副标题 + 内容）。"""
            return {
                "component": "VCard",
                "props": {"variant": "outlined", "class": "mb-4"},
                "content": [
                    {
                        "component": "VCardTitle",
                        "props": {"class": "text-subtitle-1 font-weight-medium pb-1"},
                        "text": title,
                    },
                    {
                        "component": "VCardSubtitle",
                        "props": {"class": "text-caption text-medium-emphasis pt-0 pb-2"},
                        "text": subtitle,
                    },
                    {"component": "VCardText", "content": children},
                ],
            }

        page = [
            {
                "component": "VForm",
                "content": [
                    alert(
                        "仅对首次新增的电视剧订阅生效：向 NextFind 添加订阅触发其全量搜索并"
                        "转存到 115 目标目录，轮询入库稳定后移除 NF 订阅、交还 PT 追更，"
                        "可选联动 CMS 整理。洗版订阅与后续追更不触发。",
                        type_="info",
                        title="NF订阅兜底 · 首次订阅优先 NextFind",
                    ),
                    section(
                        "基础设置",
                        "开关、运行模式与 115 落盘目录",
                        [
                            row(
                                [
                                    col(switch_field("enabled", "启用插件", "关闭后不处理任何订阅事件"), md=4),
                                    col(switch_field("notify", "终态发送通知", "任务结束或失败时推送消息"), md=4),
                                    col(
                                        switch_field(
                                            "library_scan_on_transfer",
                                            "转存后扫描媒体库",
                                            "可选，失败不影响主流程",
                                        ),
                                        md=4,
                                    ),
                                ]
                            ),
                            row(
                                [
                                    col(
                                        select_field(
                                            "blocking_mode",
                                            "运行模式",
                                            [
                                                {"title": "竞速（宿主无 gate，推荐）", "value": "race"},
                                                {"title": "严格（无 gate 能力时跳过）", "value": "strict"},
                                            ],
                                            "当前 MoviePilot 无原生刷新闸门，一般保持竞速",
                                        ),
                                        md=6,
                                    ),
                                    col(
                                        text_field(
                                            "target_folder",
                                            "115 转存目标目录",
                                            "NextFind 把资源转存到该目录，如 /00待归档媒体",
                                            "/00待归档媒体",
                                        ),
                                        md=6,
                                    ),
                                ]
                            ),
                        ],
                    ),
                    section(
                        "NextFind 连接",
                        "NextFind OpenAPI 地址与密钥（建议只填主机根地址）",
                        [
                            row(
                                [
                                    col(
                                        text_field(
                                            "nf_base_url",
                                            "NextFind 地址",
                                            "可只填主机地址，插件会自动补全 /api/openapi",
                                            "http://192.168.50.91:8092/",
                                        ),
                                        md=8,
                                    ),
                                    col(
                                        text_field(
                                            "nf_api_key",
                                            "NextFind API Key",
                                            "请求头 X-API-Key",
                                            "",
                                            "password",
                                        ),
                                        md=4,
                                    ),
                                ]
                            ),
                        ],
                    ),
                    section(
                        "抓取与超时",
                        "NF 抓取节奏与超时兜底（默认值适用于多数场景）",
                        [
                            row(
                                [
                                    col(
                                        text_field(
                                            "poll_interval",
                                            "轮询间隔（秒）",
                                            "NF 入库进度检查间隔",
                                            "",
                                            "number",
                                        ),
                                        md=3,
                                    ),
                                    col(
                                        text_field(
                                            "nf_grab_settle",
                                            "无资源判定窗口（秒）",
                                            "超过该时间仍无集入库即判无资源并放行 PT",
                                            "",
                                            "number",
                                        ),
                                        md=3,
                                    ),
                                    col(
                                        text_field(
                                            "nf_grab_timeout",
                                            "抓取总上限（秒）",
                                            "NF 抓取的最长等待时间",
                                            "",
                                            "number",
                                        ),
                                        md=3,
                                    ),
                                    col(
                                        text_field(
                                            "total_timeout",
                                            "任务总超时（秒）",
                                            "整条流程的兜底超时",
                                            "",
                                            "number",
                                        ),
                                        md=3,
                                    ),
                                ]
                            ),
                        ],
                    ),
                    section(
                        "CMS 联动（转存后整理）",
                        "可选：让 CMS 在 NF 转存后立即整理并生成 STRM",
                        [
                            alert(
                                "转存完成后向 CMS 发送 Emby 入库 Webhook，触发其自动整理"
                                "（与已安装的 CMSNotify 插件同一通道）。不启用则跳过。",
                            ),
                            row(
                                [
                                    col(switch_field("cms_enabled", "启用 CMS 联动"), md=4),
                                    col(
                                        text_field(
                                            "cms_domain",
                                            "CMS 地址",
                                            "云盘媒体整理工具地址",
                                            "http://192.168.50.91:9527",
                                        ),
                                        md=4,
                                    ),
                                    col(
                                        text_field(
                                            "cms_token",
                                            "CMS Webhook Token",
                                            "CMS 配置页给出的 webhook 令牌",
                                            "",
                                            "password",
                                        ),
                                        md=4,
                                    ),
                                ]
                            ),
                            row(
                                [
                                    col(
                                        text_field(
                                            "cms_webhook_path",
                                            "Webhook 路径",
                                            "默认 /api/emby/webhook",
                                            "/api/emby/webhook",
                                        ),
                                        md=6,
                                    ),
                                ]
                            ),
                        ],
                    ),
                    section(
                        "高级（遗留参数）",
                        "仅 v1.0.7 及以前的直转存路径使用，当前主路径不参与",
                        [
                            alert(
                                "以下参数仅用于旧的直转存路径（/resources/search + slug 转存），"
                                "当前 NF 订阅驱动主路径不参与，通常无需修改。",
                                type_="warning",
                            ),
                            row(
                                [
                                    col(text_field("min_score", "匹配置信度阈值（0-1）", "", "", "number"), md=3),
                                    col(
                                        text_field(
                                            "transfer_timeout",
                                            "转存确认超时（秒）",
                                            "",
                                            "",
                                            "number",
                                        ),
                                        md=3,
                                    ),
                                    col(text_field("gate_ttl", "闸门占位 TTL（秒）", "", "", "number"), md=3),
                                    col(
                                        text_field(
                                            "search_timeout",
                                            "NF 请求超时（秒）",
                                            "",
                                            "",
                                            "number",
                                        ),
                                        md=3,
                                    ),
                                ]
                            ),
                        ],
                    ),
                ],
            }
        ]
        return page, dict(self.DEFAULT_CONFIG)

    def get_page(self) -> list[dict]:
        """返回插件详情页（任务概览，卡片式布局）。"""
        if not self._orchestrator:
            return [
                {
                    "component": "VAlert",
                    "props": {"type": "info", "variant": "tonal", "text": "插件未初始化"},
                }
            ]
        tasks = list(self._store.load().values()) if self._store else []
        active = sorted(
            [t for t in tasks if t.is_active], key=lambda t: t.created_at
        )
        terminal = [t for t in tasks if t.is_terminal]

        def tile(label: str, value: str) -> dict:
            """统计小卡片。"""
            return {
                "component": "VCol",
                "props": {"cols": 6, "md": 3},
                "content": [
                    {
                        "component": "VCard",
                        "props": {"variant": "outlined", "class": "h-100"},
                        "content": [
                            {
                                "component": "VCardTitle",
                                "props": {"class": "text-h6 justify-center pb-0"},
                                "text": value,
                            },
                            {
                                "component": "VCardSubtitle",
                                "props": {
                                    "class": "text-caption text-center text-medium-emphasis pt-0",
                                },
                                "text": label,
                            },
                        ],
                    }
                ],
            }

        page: list[dict] = [
            {
                "component": "VRow",
                "props": {"dense": True, "class": "mb-3"},
                "content": [
                    tile("活动任务", str(len(active))),
                    tile("终态任务", str(len(terminal))),
                    tile("宿主 gate", self._orchestrator.gate.capability().value),
                    tile("CMS 联动", "已启用" if self._config.get("cms_enabled") else "未启用"),
                ],
            }
        ]

        if active:
            lines = []
            for task in active[-10:]:
                extra = f"（已入库 {task.nf_grab_last_episodes} 集）" if task.nf_grab_last_episodes else ""
                lines.append(
                    f"#{task.subscribe_id} {task.title}（{task.year}）"
                    f" S{task.season or '-'} → {task.state.value}{extra}"
                )
            page.append(
                {
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "class": "mb-2",
                        "title": "进行中的任务",
                        "text": "\n".join(lines),
                    },
                }
            )
        else:
            page.append(
                {
                    "component": "VAlert",
                    "props": {
                        "type": "success",
                        "variant": "tonal",
                        "text": "当前没有进行中的任务；新增电视剧订阅时会自动接管。",
                    },
                }
            )
        return page

    def get_api(self) -> list[dict[str, Any]]:
        """注册插件后端 API。"""
        return [
            {
                "path": "/status",
                "endpoint": self.api_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询插件运行状态",
            },
            {
                "path": "/tasks",
                "endpoint": self.api_tasks,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询任务列表",
            },
        ]

    def api_status(self) -> dict[str, Any]:
        """返回运行状态摘要。"""
        tasks = list(self._store.load().values()) if self._store else []
        return {
            "enabled": self.get_state(),
            "gate_capability": self._orchestrator.gate.capability().value
            if self._orchestrator
            else "unknown",
            "active_tasks": sum(1 for t in tasks if t.is_active),
            "terminal_tasks": sum(1 for t in tasks if t.is_terminal),
            "total_tasks": len(tasks),
        }

    def api_tasks(self) -> dict[str, Any]:
        """返回任务明细（脱敏：不含任何凭据）。"""
        tasks = list(self._store.load().values()) if self._store else []
        return {"tasks": [t.to_dict() for t in sorted(tasks, key=lambda t: t.created_at)]}

    # ------------------------------------------------------------- 命令与服务

    def get_command(self) -> list[dict[str, Any]]:
        """注册远程命令。"""
        from app.schemas.types import EventType

        return [
            {
                "cmd": "/firstnf_watchdog",
                "event": EventType.PluginAction,
                "desc": "立即执行一次 FirstNF 看门狗",
                "category": "插件命令",
                "data": {"action": "firstnf_watchdog"},
            }
        ]

    def get_service(self) -> list[dict]:
        """注册周期看门狗（每 5 分钟）。"""
        if not self.get_state():
            return []
        from apscheduler.triggers.cron import CronTrigger

        return [
            {
                "id": "FirstNF.Watchdog",
                "name": "FirstNF 看门狗",
                "trigger": CronTrigger.from_crontab("*/5 * * * *"),
                "func": self.run_watchdog,
                "kwargs": {},
            }
        ]

    # ------------------------------------------------------------- 事件处理

    @_register_event("SubscribeAdded")
    def on_subscribe_added_event(self, event) -> None:
        """EventType.SubscribeAdded：首次新增订阅入口。

        经 @eventmanager.register 注册（官方 V3 指南 9.1 模式），
        宿主在订阅创建提交后广播该事件，event_data 含
        subscribe_id / idempotency_key / username / mediainfo。
        """
        if not self.get_state() or not self._orchestrator:
            return
        event_data = getattr(event, "event_data", None) or {}
        try:
            record = self._load_subscribe(event_data.get("subscribe_id"))
        except Exception:
            record = None
        eligibility = decide_first_subscription(
            event_data, record, self._config, time.time()
        )
        if not eligibility.eligible or eligibility.task is None:
            self._log_info(f"订阅跳过：{eligibility.reason}")
            return
        task = self._orchestrator.on_subscribe_added(eligibility.task)
        self._schedule_task_job(task.task_key)

    @_register_event("SubscribeDeleted")
    def on_subscribe_deleted_event(self, event) -> None:
        """EventType.SubscribeDeleted：清理已删除订阅的任务记录。"""
        if not self._store:
            return
        event_data = getattr(event, "event_data", None) or {}
        sid = event_data.get("subscribe_id")
        if sid is None:
            return
        tasks = self._store.load()
        removed = [k for k, t in tasks.items() if t.subscribe_id == sid]
        for key in removed:
            del tasks[key]
        if removed:
            self._store.save(tasks)

    @_register_event("PluginAction")
    def on_plugin_action_event(self, event) -> None:
        """EventType.PluginAction：远程命令路由。"""
        event_data = getattr(event, "event_data", None) or {}
        if event_data.get("action") == "firstnf_watchdog":
            self.run_watchdog()

    @_register_event("PluginReload")
    def on_plugin_reload_event(self, event) -> None:
        """EventType.PluginReload：重载后重建适配器。"""
        self.init_plugin(self._config)

    # ------------------------------------------------------------- 任务执行

    def _schedule_task_job(self, task_key: str, delay: int = 0) -> None:
        """把任务推进加入宿主调度器（同 ID 任务只保留最后一次，天然去重）。

        task_key 经 func_kwargs 传递（add_plugin_once_job 合同：
        调度器以 func(**func_kwargs) 调用；无参调用会丢参数）。
        """
        plugin_id = self.__class__.__name__
        job_id = f"firstnf_{task_key}"
        try:
            from app.sdk import scheduler as scheduler_sdk

            scheduler_sdk.add_plugin_once_job(
                plugin_id, job_id, self._run_task_job, "NF订阅兜底 任务推进",
                delay_seconds=delay,
                func_kwargs={"task_key": task_key},
            )
            if task_key not in self._active_job_keys:
                self._active_job_keys.append(task_key)
        except Exception as error:
            self._log_error(f"任务调度失败：{error}")

    def _run_task_job(self, task_key: str) -> None:
        """推进一个任务直至阻塞或终态；轮询阶段自我续期。"""
        if not self._orchestrator or not self._store:
            return
        tasks = self._store.load()
        task = tasks.get(task_key)
        if task is None or task.is_terminal:
            return
        before = task.state
        task = self._orchestrator.run_until_blocked(task)
        if task.is_active and task.state == TaskState.TRANSFER_POLL:
            # 转存未确认：按间隔自我续期，等待看门狗或下一次轮询
            self._schedule_task_job(task_key, delay=int(self._config.get("poll_interval", 60)))
        self._maybe_notify(before, task)

    def run_watchdog(self) -> None:
        """看门狗：超时释放、释放重试、推进卡住任务；每轮输出心跳日志。"""
        if not self._orchestrator or not self._store:
            return
        try:
            handled = self._orchestrator.watchdog()
            tasks = list(self._store.load().values())
            active = sum(1 for t in tasks if t.is_active)
            terminal = sum(1 for t in tasks if t.is_terminal)
            self._log_info(
                f"看门狗心跳：活动任务 {active} / 终态 {terminal} / 本次推进 {len(handled)}"
            )
        except Exception as error:
            self._log_error(f"看门狗执行失败：{error}")

    def _reschedule_active_tasks(self) -> None:
        """重启恢复：为所有未完成任务排队。"""
        if not self._store:
            return
        for task in self._store.load().values():
            if task.is_active:
                self._schedule_task_job(task.task_key, delay=5)

    def _maybe_notify(self, before: TaskState, task: FirstNFTask) -> None:
        """任务进入终态时发送通知（可配置）。"""
        if not self._config.get("notify"):
            return
        if not (task.is_terminal and before != task.state):
            return
        text = (
            f"订阅 #{task.subscribe_id}《{task.title}》"
            f"（{task.year}）S{task.season or '-'} 流程结束：{task.state.value}"
            f"（{task.release_reason or '-'}）"
        )
        self._notify(f"NF订阅兜底：{text.splitlines()[0] if text else ''}", text)

    def _notify(self, title: str, text: str) -> None:
        """发送插件通知（受 notify 配置控制）。

        按 _PluginBase.post_message 官方签名以关键字参数调用
        （channel/mtype/title/text 均为可选关键字参数；位置参数会被
        当作 channel 校验失败）。mtype 取不到时退化为纯标题文本。
        """
        if not self._config.get("notify"):
            return
        try:
            from app.schemas.types import NotificationType

            self.post_message(
                mtype=NotificationType.Subscribe,
                title=title,
                text=text,
            )
        except Exception:
            try:
                self.post_message(title=title, text=text)
            except Exception:
                pass  # 通知失败不影响主流程

    # ------------------------------------------------------------- 工具

    def _load_subscribe(self, subscribe_id: Any):
        """通过 SubscribeOper 只读宿主订阅。"""
        from app.db.oper.subscribe import SubscribeOper

        return SubscribeOper().get(sid=int(subscribe_id))

    def _log_info(self, message: str) -> None:
        """记录信息日志。"""
        try:
            from app.sdk.logging import logger

            logger.info(f"[FirstNF] {message}")
        except Exception:
            pass

    def _log_error(self, message: str) -> None:
        """记录错误日志。"""
        try:
            from app.sdk.logging import logger

            logger.error(f"[FirstNF] {message}")
        except Exception:
            pass


# ------------------------------------------------------------- 宿主适配器


class _UnconfiguredNextfind:
    """NF 未配置时的占位实现（能力探测失败，所有调用抛配置错误）。"""

    async def search_resources(self, *args, **kwargs):
        """NF 未配置。"""
        raise RuntimeError("NF 未配置（缺少 nf_base_url/nf_api_key）")

    async def library_progress(self, *args, **kwargs):
        """NF 未配置。"""
        raise RuntimeError("NF 未配置（缺少 nf_base_url/nf_api_key）")

    async def submit_transfer(self, *args, **kwargs):
        """NF 未配置。"""
        raise RuntimeError("NF 未配置（缺少 nf_base_url/nf_api_key）")

    async def transfer_history(self, *args, **kwargs):
        """NF 未配置。"""
        raise RuntimeError("NF 未配置（缺少 nf_base_url/nf_api_key）")

    async def add_subscription(self, *args, **kwargs):
        """NF 未配置。"""
        raise RuntimeError("NF 未配置（缺少 nf_base_url/nf_api_key）")

    async def remove_subscription(self, *args, **kwargs):
        """NF 未配置。"""
        raise RuntimeError("NF 未配置（缺少 nf_base_url/nf_api_key）")


class _SubscribeReleaseAdapter(NativeReleasePort):
    """释放适配器：调用宿主 SubscribeChain 定向补搜（已核实合同）。"""

    def trigger_native_search(self, subscribe_id: int) -> bool:
        """触发指定订阅的手动定向补搜。"""
        from app.chain.subscribe import SubscribeChain

        SubscribeChain().search(sid=subscribe_id, manual=True)
        return True


class _MediaServerScanAdapter(MediaStatePort):
    """媒体库扫描适配器（可选，失败非致命）。"""

    async def refresh_library(self) -> bool:
        """触发已配置媒体服务器的库扫描。"""
        try:
            from app.sdk.services import MediaServerHelper

            services = MediaServerHelper().get_services()
            for service in (services or {}).values():
                instance = getattr(service, "instance", None)
                scanner = getattr(instance, "library_scan", None)
                if callable(scanner):
                    scanner()
            return True
        except Exception:
            return False
