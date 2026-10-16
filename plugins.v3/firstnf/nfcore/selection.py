"""NF 网盘候选的资源匹配与择优（纯逻辑，不依赖宿主与网络）。

输入为 NextFind OpenAPI `GET /resources/search` 的候选字典
（参考 unisub 实测文档 nextfind-api-v3，2026-07-22），输出确定性排序。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: parsed_episodes 形如 "S01E01-E07 S02E01-E13"
_EPISODE_TOKEN = re.compile(r"S(\d{1,2})E(\d{1,3})(?:-E?(\d{1,3}))?")


@dataclass
class SelectionResult:
    """一次择优结果。"""

    selected: Optional[Dict[str, Any]]
    ranked: List[Tuple[float, Dict[str, Any]]] = field(default_factory=list)
    reason: str = ""


def parse_parsed_episodes(text: str) -> Dict[int, List[int]]:
    """解析 NF 候选的 parsed_episodes 字符串为 {季: [集...]}。"""
    coverage: Dict[int, List[int]] = {}
    if not text:
        return coverage
    for match in _EPISODE_TOKEN.finditer(text):
        season = int(match.group(1))
        start = int(match.group(2))
        end = int(match.group(3) or start)
        episodes = coverage.setdefault(season, [])
        episodes.extend(range(start, end + 1))
    return coverage


def episode_coverage_ratio(
    coverage: Dict[int, List[int]], season: Optional[int], requested: List[int]
) -> float:
    """候选对目标季/集的覆盖比例（0.0 - 1.0）。

    未指定季或未指定集时退化为"是否覆盖该季任意集"。
    """
    if season is None:
        return 1.0 if coverage else 0.0
    have = set(coverage.get(season, []))
    if not have:
        return 0.0
    if not requested:
        return 1.0
    hit = sum(1 for ep in requested if ep in have)
    return hit / len(requested)


def _resolution_score(candidate: Dict[str, Any], preference: List[str]) -> float:
    """按清晰度偏好列表给候选打分（0.0 - 1.0）。"""
    resolutions = [str(r).upper() for r in (candidate.get("video_resolution") or [])]
    if not preference:
        return 0.5
    for idx, want in enumerate(preference):
        if str(want).upper() in resolutions:
            # 越靠前偏好越高
            return 1.0 - idx * 0.1
    return 0.0


def _keyword_score(candidate: Dict[str, Any], whitelist: List[str], blacklist: List[str]) -> float:
    """按黑白名单关键词过滤并打分。"""
    text_parts = [
        str(candidate.get("title") or ""),
        str(candidate.get("remark") or ""),
        " ".join(str(s) for s in (candidate.get("source") or [])),
        " ".join(str(s) for s in (candidate.get("media_tags") or "") if s)
        if isinstance(candidate.get("media_tags"), str)
        else " ".join(str(s) for s in (candidate.get("media_tags") or [])),
        str(candidate.get("db_raw_text") or ""),
    ]
    text = " ".join(text_parts).lower()
    for bad in blacklist:
        if bad and bad.lower() in text:
            return -1.0  # 命中黑名单直接淘汰
    if not whitelist:
        return 0.5
    hit = sum(1 for good in whitelist if good and good.lower() in text)
    return hit / len(whitelist)


def score_candidate(
    candidate: Dict[str, Any],
    *,
    season: Optional[int],
    requested_episodes: List[int],
    resolution_preference: List[str],
    whitelist: List[str],
    blacklist: List[str],
) -> float:
    """对单个候选计算综合得分。

    权重：季集覆盖 0.6，清晰度偏好 0.2，关键词 0.1，官方/解锁 0.1。
    黑名单命中返回 -1（淘汰）。
    """
    keyword = _keyword_score(candidate, whitelist, blacklist)
    if keyword < 0:
        return -1.0
    coverage = episode_coverage_ratio(
        parse_parsed_episodes(str(candidate.get("parsed_episodes") or "")),
        season,
        requested_episodes,
    )
    if season is not None and coverage <= 0:
        return -1.0  # 目标季完全无覆盖直接淘汰
    resolution = _resolution_score(candidate, resolution_preference)
    official = 1.0 if candidate.get("is_official") else 0.0
    unlocked = 1.0 if candidate.get("is_unlocked") else 0.0
    return round(
        coverage * 0.6
        + resolution * 0.2
        + keyword * 0.1
        + (official * 0.5 + unlocked * 0.5) * 0.1,
        4,
    )


def select_candidate(
    candidates: List[Dict[str, Any]],
    *,
    season: Optional[int] = None,
    requested_episodes: Optional[List[int]] = None,
    resolution_preference: Optional[List[str]] = None,
    whitelist: Optional[List[str]] = None,
    blacklist: Optional[List[str]] = None,
    min_score: float = 0.35,
) -> SelectionResult:
    """从 NF 候选列表中选出最优资源。

    :param candidates: GET /resources/search 返回的 data 列表
    :param min_score: 低于该分数视为无可用匹配（NO_MATCH）
    """
    requested_episodes = requested_episodes or []
    resolution_preference = resolution_preference or []
    whitelist = whitelist or []
    blacklist = blacklist or []

    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for candidate in candidates:
        score = score_candidate(
            candidate,
            season=season,
            requested_episodes=requested_episodes,
            resolution_preference=resolution_preference,
            whitelist=whitelist,
            blacklist=blacklist,
        )
        if score < 0:
            continue
        ranked.append((score, candidate))
    # 分数降序，同分按标题稳定排序，保证确定性
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("title") or "")))

    if not ranked:
        return SelectionResult(None, ranked, "no_candidate_after_filter")
    if ranked[0][0] < min_score:
        return SelectionResult(None, ranked, f"below_threshold:{ranked[0][0]}")
    return SelectionResult(ranked[0][1], ranked, "selected")


def history_confirms_transfer(
    history_entries: List[Dict[str, Any]],
    *,
    slug: str,
    title: Optional[str] = None,
    after_ts: Optional[float] = None,
) -> bool:
    """在 NF 转存历史中确认本次转存已完成（is_slug_transferred == 1）。

    优先按 slug 匹配；slug 不匹配时退化为"标题 + 提交时间之后"的宽松确认。
    """
    for entry in history_entries or []:
        if int(entry.get("is_slug_transferred") or 0) != 1:
            continue
        entry_slug = str(entry.get("slug") or "")
        if slug and slug in entry_slug:
            return True
        if title and str(entry.get("title") or "") == title:
            transfer_time = str(entry.get("transfer_time") or "")
            if after_ts is None or transfer_time:
                # 宽松确认：存在同标题成功记录即认为完成
                return True
    return False
