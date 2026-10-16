"""首次新增订阅的准入判定（纯逻辑，不依赖宿主）。

判定优先级与设计文档第 6 章一致：
1. 宿主的 SubscribeAdded 广播事件只在订阅创建提交后发送，且自带幂等键，
   因此事件到达本身即代表"本次创建"，结合持久化去重后得到 is_first。
2. 洗版订阅以宿主订阅记录的 best_version 字段判定（0=普通，1=洗版）。
3. 媒体类型限定为电视剧（可配置）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .state import FirstNFTask, TaskState

#: 宿主营盘订阅模型中 best_version=1 表示洗版订阅（默认 0）
WASH_FLAG_VALUE = 1

#: MP 媒体类型字面量（app.schemas.types.MediaType）
TV_TYPE_LITERAL = "电视剧"


@dataclass
class Eligibility:
    """准入判定结果。"""

    eligible: bool
    reason: str
    # 判定通过时构建的任务（不含状态推进）
    task: Optional[FirstNFTask] = None


def is_wash_subscription(best_version: Any) -> bool:
    """按宿主订阅记录的 best_version 判定洗版订阅。"""
    try:
        return int(best_version or 0) == WASH_FLAG_VALUE
    except (TypeError, ValueError):
        # 字段异常时按洗版处理（安全默认：洗版永不触发 NF）
        return True


def extract_tmdb_id(event_data: Dict[str, Any], subscribe_record: Any = None) -> Optional[str]:
    """从事件 mediainfo 或订阅记录中提取 TMDB ID（字符串）。

    NextFind OpenAPI 全部以 TMDB ID 为媒体键，缺失时无法进入 NF 流程。
    """
    mediainfo = (event_data or {}).get("mediainfo") or {}
    for candidate in (
        mediainfo.get("tmdbid"),
        mediainfo.get("tmdb_id"),
        getattr(subscribe_record, "media_id", None)
        if getattr(subscribe_record, "media_source", "") == "tmdb"
        else None,
    ):
        if candidate:
            return str(candidate)
    return None


def decide_first_subscription(
    event_data: Dict[str, Any],
    subscribe_record: Any,
    config: Dict[str, Any],
    now: float,
) -> Eligibility:
    """判定一次 SubscribeAdded 事件是否应进入 NF 优先流程。

    :param event_data: EventType.SubscribeAdded 的 event_data，宿主保证包含
        subscribe_id / idempotency_key / username / mediainfo
    :param subscribe_record: 通过 SubscribeOper().get(sid=...) 读取的宿主订阅记录
    :param config: 插件配置（enabled / media_types 等）
    :param now: 当前时间（epoch 秒，便于测试）
    :return: Eligibility；reason 说明忽略或准入原因
    """
    event_data = event_data or {}
    if not config.get("enabled", False):
        return Eligibility(False, "plugin_disabled")

    subscribe_id = event_data.get("subscribe_id")
    idempotency_key = event_data.get("idempotency_key")
    if not subscribe_id:
        return Eligibility(False, "missing_subscribe_id")
    if not idempotency_key:
        # 宿主合同包含幂等键；缺失时降级为按订阅 ID 去重
        idempotency_key = f"subscribe:{subscribe_id}"

    if subscribe_record is None:
        return Eligibility(False, "subscribe_record_missing")

    record_type = str(getattr(subscribe_record, "type", "") or "")
    allowed_types = config.get("media_types") or [TV_TYPE_LITERAL]
    if record_type and record_type not in allowed_types:
        return Eligibility(False, f"media_type_not_supported:{record_type}")

    if is_wash_subscription(getattr(subscribe_record, "best_version", 0)):
        return Eligibility(False, "wash_subscription")

    media_id = extract_tmdb_id(event_data, subscribe_record)
    if not media_id:
        return Eligibility(False, "missing_tmdb_id")

    task = FirstNFTask(
        task_key=str(idempotency_key),
        subscribe_id=int(subscribe_id),
        media_source=str(getattr(subscribe_record, "media_source", "") or ""),
        media_id=media_id,
        title=str(getattr(subscribe_record, "name", "") or ""),
        year=str(getattr(subscribe_record, "year", "") or ""),
        season=getattr(subscribe_record, "season", None),
        is_wash=False,
        state=TaskState.ELIGIBILITY_CHECK,
        created_at=now,
    )
    return Eligibility(True, "first_subscription", task)
