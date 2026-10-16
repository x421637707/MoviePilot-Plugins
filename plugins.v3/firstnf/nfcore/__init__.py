"""FirstNF 插件核心包：状态机、判定、择优、端口与适配器。

本包不依赖 MoviePilot 宿主，可在宿主外独立运行与测试；
宿主装配位于 plugins.v3/firstnf/__init__.py。
"""

from .cmsapi import CmsNotifyError, CmsWebhookAdapter, normalize_cms_domain
from .decision import Eligibility, decide_first_subscription, extract_tmdb_id, is_wash_subscription
from .gate import HostGateAdapter, NullGate
from .nfapi import NextfindError, NextfindHttpAdapter, normalize_nf_base_url
from .orchestrator import Orchestrator
from .ports import (
    CmsNotifyPort,
    GateCapability,
    GateLease,
    MediaStatePort,
    NativeRefreshGate,
    NativeReleasePort,
    NextfindPort,
)
from .selection import SelectionResult, select_candidate
from .state import FirstNFTask, TaskState
from .store import FileTaskStore, HostDataStore, MemoryTaskStore

__all__ = [
    "Eligibility",
    "decide_first_subscription",
    "extract_tmdb_id",
    "is_wash_subscription",
    "HostGateAdapter",
    "NullGate",
    "NextfindError",
    "NextfindHttpAdapter",
    "normalize_nf_base_url",
    "CmsNotifyError",
    "CmsWebhookAdapter",
    "normalize_cms_domain",
    "Orchestrator",
    "CmsNotifyPort",
    "GateCapability",
    "GateLease",
    "MediaStatePort",
    "NativeRefreshGate",
    "NativeReleasePort",
    "NextfindPort",
    "SelectionResult",
    "select_candidate",
    "FirstNFTask",
    "TaskState",
    "FileTaskStore",
    "HostDataStore",
    "MemoryTaskStore",
]
