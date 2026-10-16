"""插件与宿主/外部服务之间的端口定义。

所有端口都是抽象接口：宿主适配器在插件主类中装配，测试使用内存假实现。
这样既满足"代码结构清晰、可直接运行"，也保证未核实接口不会污染核心逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional


class GateCapability(Enum):
    """宿主原生订阅刷新闸门的能力状态。"""

    AVAILABLE = "available"      # 宿主提供可拦截/释放的 gate API（截至核验日 V3 未提供）
    UNAVAILABLE = "unavailable"  # 宿主不提供（当前状态）
    UNKNOWN = "unknown"          # 尚未探测


class GateLease:
    """闸门租约。宿主不可用时仅为进程内占位，不产生任何宿主侧拦截效果。"""

    def __init__(self, token: str, expires_at: float, capability: GateCapability) -> None:
        self.token = token
        self.expires_at = expires_at
        self.capability = capability


class NativeRefreshGate(ABC):
    """原生 PT 订阅刷新闸门端口。

    设计文档第 7 章 GATE_ACQUIRING 状态依赖此端口。
    重要：MoviePilot V3 源码核验（2026-10-16）确认不存在订阅刷新拦截/gate
    接口，因此默认实现为 NullGate（能力不可用 + 进程内占位）。
    未来宿主提供该能力时，替换为 HostGateAdapter 即可，状态机无需改动。
    """

    @abstractmethod
    def capability(self) -> GateCapability:
        """返回宿主闸门能力状态。"""

    @abstractmethod
    def acquire(self, subscription_id: int, ttl_seconds: float) -> Optional[GateLease]:
        """申请订阅刷新闸门；失败返回 None。"""

    @abstractmethod
    def release(self, lease: GateLease) -> bool:
        """释放闸门；幂等，重复释放返回 True。"""


class NextfindPort(ABC):
    """NextFind OpenAPI 端口。

    合同来源（2026-10-16 核对）：
    - NextFind 官方智能体开发文档（用户提供）：端点前缀 /api/openapi、
      X-API-Key 鉴权、/resources/search、/transfer、/history、
      /subscriptions/info、/subscriptions/add、/subscriptions/remove 等；
    - unisub 实测参考（nextfind-api-v3，2026-07-22）：响应字段级细节；
    - 目标实例已安装的 NextFindController 源码：调用方式交叉验证。

    主路径（v1.0.8，设计文档第 13 章实测结论）：**NF 订阅驱动**。
    实测证明 NF 的「搜索→匹配→转存」管线由 NF 订阅驱动，`/resources/search`
    只返回已完成匹配的待转存候选（未命中雷达缓存的标题返回 0）。因此改为
    添加 NF 订阅触发 NF 全量搜索+转存，轮询 local_episodes 至稳定后移除
    NF 订阅，交还追更主权给 MP/PT。

    以下为官方文档确认存在但本插件有意不使用的端点（附理由）：
    - GET /local_library/filter：仅返回 missing/error/duplicate 问题项，
      响应结构未明确，无法安全用作完成确认信号；
    - POST /media/fill_missing：NF 侧补缺——无 NF 订阅时会被队列直接丢弃
      （实测「已被取消订阅，从排队中移除跳过」），且补缺由 PT 承担；
    - POST /transfer 的 tmdb_id 直转：目标实例校验 slug 为必填，不支持。
    """

    @abstractmethod
    async def search_resources(
        self, tmdb_id: str, media_type: str, season: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """GET /resources/search，返回候选列表（直转存遗留路径）。"""

    @abstractmethod
    async def library_progress(self, tmdb_id: str, media_type: str) -> Optional[int]:
        """POST /subscriptions/info，返回 NF 侧 local_episodes（转存完成的主确认信号）。"""

    @abstractmethod
    async def submit_transfer(self, slug: str, target_folder: str) -> bool:
        """POST /transfer，提交转存任务；返回是否受理（直转存遗留路径）。"""

    @abstractmethod
    async def transfer_history(self, slug: str) -> List[Dict[str, Any]]:
        """GET /history，用于按 slug 兜底确认转存完成。"""

    async def add_subscription(
        self, tmdb_id: str, media_type: str, title: str = ""
    ) -> bool:
        """POST /subscriptions/add：添加 NF 订阅以触发全量搜索+转存。

        主路径核心动作（v1.0.8）。适配器不支持时抛异常，由编排层处理。
        """
        raise NotImplementedError

    async def remove_subscription(self, tmdb_id: str, media_type: str) -> bool:
        """POST /subscriptions/remove：移除 NF 订阅，交还追更主权给 MP/PT。

        释放阶段调用；幂等（重复移除返回成功）。适配器不支持时抛异常。
        """
        raise NotImplementedError

    async def quota(self) -> Optional[Dict[str, Any]]:
        """GET /quota 健康预检（NF 可达 + 密钥有效）。

        适配器不支持或宿主未启用该检查时返回 None（跳过预检）。
        """
        return None

    async def recent_logs(self, lines: int = 20) -> Optional[List[str]]:
        """GET /logs 最近日志行；不支持时返回 None（仅用于失败诊断富化）。"""
        return None


class MediaStatePort(ABC):
    """媒体库状态刷新端口（可选）。"""

    @abstractmethod
    async def refresh_library(self) -> bool:
        """触发媒体服务器库扫描；失败返回 False（非致命）。"""


class CmsNotifyPort(ABC):
    """CMS（云盘媒体整理工具，如 CloudMediaSync）联动端口。

    转存完成后通知 CMS 触发其整理流程，使 115 落盘资源尽快生成 STRM 并入库。

    实测契约（2026-10-16，目标实例 http://192.168.50.91:9527）：
    - 端点：``POST {domain}/api/emby/webhook?token={token}``
    - 响应：``{"status":"success"}``；token 错误时 ``{"code":"400","message":"token错误"}``
    - 该 token 为 CMS 侧配置的 webhook 令牌（默认 ``cloud_media_sync``），
      与 CMS 网页登录会话令牌不同（后者无法从插件侧获得）。

    失败必须非致命：CMS 不可用不得阻塞释放与 PT 接管。
    """

    @abstractmethod
    async def trigger_organize(self, title: str, path: str = "") -> bool:
        """通知 CMS 执行整理；返回是否受理。"""


class NativeReleasePort(ABC):
    """原生 PT 释放端口：触发宿主对指定订阅的定向补搜。"""

    @abstractmethod
    def trigger_native_search(self, subscribe_id: int) -> bool:
        """调用 SubscribeChain().search(sid=..., manual=True)，返回是否受理。"""


class NotifyPort(ABC):
    """通知端口（post_message 的薄封装）。"""

    @abstractmethod
    def notify(self, title: str, text: str) -> None:
        """发送一条插件通知；失败应静默降级。"""
