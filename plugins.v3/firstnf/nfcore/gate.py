"""原生刷新闸门的实现。

核验结论（2026-10-16，MoviePilot v3 分支源码）：
- EventType / ChainEventType 枚举中不存在订阅刷新拦截事件；
- 订阅刷新链（app/chain/subscribe/refresh.py）在创建提交后由宿主自行排队
  新订阅搜索（_queue_new_subscription_search），没有公开的暂停/恢复入口；
- app/application/subscription/execution.py 的 SubscriptionExecutionAdmission
  是宿主内部进程锁，不是插件合同。

因此当前版本默认使用 NullGate：不产生任何宿主侧拦截，
插件以"NF 优先竞速 + 完成后定向补搜"的降级模式运行（与设计文档第 12 章
fail-open 策略一致）。HostGateAdapter 保留为未来宿主提供 gate API 时的接缝。
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from .ports import GateCapability, GateLease, NativeRefreshGate


class NullGate(NativeRefreshGate):
    """宿主无 gate 能力时的占位闸门。

    acquire 只返回进程内租约（用于插件自身的幂等互斥），
    不对宿主原生刷新产生任何拦截效果；release 幂等。
    """

    def __init__(self) -> None:
        self._leases: dict[int, GateLease] = {}

    def capability(self) -> GateCapability:
        """固定返回不可用。"""
        return GateCapability.UNAVAILABLE

    def acquire(self, subscription_id: int, ttl_seconds: float) -> Optional[GateLease]:
        """取得进程内租约；已有未过期租约时返回 None（互斥）。"""
        existing = self._leases.get(subscription_id)
        if existing and existing.expires_at > time.monotonic():
            return None
        lease = GateLease(
            token=uuid.uuid4().hex,
            expires_at=time.monotonic() + max(1.0, ttl_seconds),
            capability=GateCapability.UNAVAILABLE,
        )
        self._leases[subscription_id] = lease
        return lease

    def release(self, lease: GateLease) -> bool:
        """幂等释放。"""
        self._leases.pop(getattr(lease, "subscription_id", -1), None)
        return True


class HostGateAdapter(NativeRefreshGate):
    """未来宿主提供 gate API 时的适配器骨架。

    当前 MoviePilot V3 不存在该接口，因此本类故意不接线。
    一旦宿主提供稳定的订阅刷新拦截/释放合同，在此实现 acquire/release，
    并在插件装配时替换 NullGate 即可，状态机与核心逻辑无需改动。
    """

    def capability(self) -> GateCapability:
        """尚未接线前报告未知能力。"""
        return GateCapability.UNKNOWN

    def acquire(self, subscription_id: int, ttl_seconds: float) -> Optional[GateLease]:
        """未实现：等待宿主提供公开 gate 合同后补充。"""
        raise NotImplementedError("MoviePilot V3 尚未提供订阅刷新 gate 合同")

    def release(self, lease: GateLease) -> bool:
        """未实现：等待宿主提供公开 gate 合同后补充。"""
        raise NotImplementedError("MoviePilot V3 尚未提供订阅刷新 gate 合同")
