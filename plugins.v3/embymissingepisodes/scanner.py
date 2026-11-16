"""Emby 缺集扫描：读取媒体服务器剧集季集，与 TMDB 已播出集号对比并输出缺集清单。"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from app.chain.tmdb import TmdbChain
from app.domain.meta.metabase import MetaBase
from app.schemas.media import resolve_media_identity
from app.schemas.types import MediaSource, MediaType
from app.sdk.logging import logger
from app.sdk.services import MediaServerHelper

# 插件配置默认值
DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": False,
    "servers": [],
    "libraries": [],
    "cron": "",
    "onlyonce": False,
    "notify": True,
    "air_buffer_days": 1,
    "include_specials": False,
    "only_existing_seasons": True,
    "max_series": 0,
    # 已忽略条目键列表，格式 "{media_id}:{season}"
    "ignored": [],
}

# TMDB 海报地址模板
POSTER_URL = "https://{domain}/t/p/w300{path}"


def _as_int(value: Any, default: int = 0) -> int:
    """把配置值转换为整数，无法转换时返回默认值。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> List[str]:
    """把配置值规范化为去空的字符串列表。"""
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    return [str(item).strip() for item in items if str(item).strip()]


def normalize_config(config: Optional[dict]) -> Dict[str, Any]:
    """把插件配置补齐为完整字典，避免缺键导致属性缺失。"""
    raw = dict(config or {})
    return {
        "enabled": bool(raw.get("enabled")),
        "servers": _as_list(raw.get("servers")),
        "libraries": _as_list(raw.get("libraries")),
        "cron": str(raw.get("cron") or "").strip(),
        "onlyonce": bool(raw.get("onlyonce")),
        "notify": bool(raw.get("notify", True)),
        "air_buffer_days": max(0, _as_int(raw.get("air_buffer_days"), 1)),
        "include_specials": bool(raw.get("include_specials")),
        "only_existing_seasons": bool(raw.get("only_existing_seasons", True)),
        "max_series": max(0, _as_int(raw.get("max_series"), 0)),
        "ignored": _as_list(raw.get("ignored")),
    }


def poster_url(path: Any, domain: str = "image.tmdb.org") -> str:
    """把 TMDB poster_path 转为可访问的海报地址。"""
    text = str(path or "").strip()
    if not text or text == "None":
        return ""
    if text.startswith("http"):
        return text
    return POSTER_URL.format(domain=domain, path=text)


def parse_air_date(value: Any) -> Optional[date]:
    """解析 TMDB 播出日期，无法解析时返回 None。"""
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


class MissingEpisodeScanner:
    """遍历已连接的媒体服务器剧集，计算相对 TMDB 已播出集的缺集。"""

    def __init__(
        self,
        config: Dict[str, Any],
        stop_event: threading.Event,
        progress: Optional[Callable[[str], None]] = None,
        recognize: Optional[Callable[..., Any]] = None,
    ) -> None:
        """
        保存扫描参数。

        :param config: 规范化后的插件配置
        :param stop_event: 停止信号，置位后尽快结束扫描
        :param progress: 进度回调，用于在报告页展示当前处理对象
        :param recognize: 按标题识别媒体的回调，用于缺少 TMDB 身份的剧集
        """
        self._config = config
        self._stop_event = stop_event
        self._progress = progress or (lambda text: None)
        self._recognize = recognize
        self._tmdb = TmdbChain()

    def scan(self) -> Dict[str, Any]:
        """执行一次扫描并返回报告字典。"""
        started = time.time()
        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        series_count = 0
        cancelled = False

        services = self._services(errors)
        for server_name, service_info in services.items():
            if self._stop_event.is_set():
                cancelled = True
                break
            instance = service_info.instance
            libraries = instance.get_librarys() or []
            for library in libraries:
                if self._stop_event.is_set():
                    cancelled = True
                    break
                if library.type != MediaType.TV.value:
                    continue
                library_name = str(library.name or "未命名媒体库")
                if self._config["libraries"] and library_name not in self._config["libraries"]:
                    continue
                self._progress(f"{server_name} / {library_name}")
                try:
                    items = list(instance.get_items(parent=library.item_id, limit=-1))
                except Exception as err:  # noqa: BLE001 - 单个媒体库失败不影响其它库
                    logger.error(f"Emby 缺集扫描：读取媒体库 {library_name} 失败：{err}")
                    errors.append(f"{server_name} / {library_name}：读取条目失败（{err}）")
                    continue
                for item in items:
                    if self._stop_event.is_set():
                        cancelled = True
                        break
                    if not item or item.item_type != "Series":
                        continue
                    max_series = self._config["max_series"]
                    if max_series and series_count >= max_series:
                        errors.append(f"已达到单次扫描上限 {max_series} 部，剩余剧集留到下次扫描")
                        break
                    series_count += 1
                    self._progress(f"{server_name} / {item.title or item.item_id}")
                    try:
                        rows.extend(
                            self._series_rows(server_name, library_name, instance, item, errors)
                        )
                    except Exception as err:  # noqa: BLE001 - 单部剧集失败不影响整体
                        logger.error(f"Emby 缺集扫描：处理 {item.title} 失败：{err}")
                        errors.append(f"{item.title}：{err}")
                if cancelled or (self._config["max_series"] and series_count >= self._config["max_series"]):
                    break
            if cancelled or (self._config["max_series"] and series_count >= self._config["max_series"]):
                break

        rows.sort(key=lambda row: (row["title"], row["season"]))
        return {
            "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": round(time.time() - started, 1),
            "series": series_count,
            "rows": rows,
            "errors": errors,
            "cancelled": cancelled,
        }

    def _services(self, errors: List[str]) -> Dict[str, Any]:
        """获取已连接的目标媒体服务器实例。"""
        try:
            # MediaServerConf.type 使用小写标识（emby/jellyfin/...），"Emby" 只是显示名
            services = MediaServerHelper().get_services(
                type_filter="emby", name_filters=self._config["servers"] or None
            )
        except Exception as err:  # noqa: BLE001 - 配置缺失时给出可读错误
            logger.error(f"Emby 缺集扫描：获取媒体服务器失败：{err}")
            errors.append(f"获取媒体服务器失败（{err}）")
            return {}
        active: Dict[str, Any] = {}
        for name, service_info in (services or {}).items():
            try:
                if service_info.instance.is_inactive():
                    errors.append(f"{name}：未连接，已跳过")
                    continue
            except Exception as err:  # noqa: BLE001 - 连接状态异常按未连接处理
                errors.append(f"{name}：连接检查失败（{err}）")
                continue
            active[name] = service_info
        if not active:
            errors.append("没有可用的 Emby 媒体服务器，请检查媒体服务器配置与插件设置")
        return active

    def _series_rows(
        self,
        server_name: str,
        library_name: str,
        instance: Any,
        item: Any,
        errors: List[str],
    ) -> List[Dict[str, Any]]:
        """计算单部剧集各季的缺集行。"""
        tmdb_id = self._tmdb_id(item)
        if not tmdb_id:
            errors.append(f"{item.title}：未识别到 TMDB ID，已跳过")
            return []

        _, season_map = instance.get_tv_episodes(
            item_id=item.item_id,
            title=item.title,
            year=item.year,
            media_source=item.media_source,
            media_id=item.media_id,
        )
        season_map = season_map or {}
        seasons = self._tmdb.tmdb_seasons(tmdbid=int(tmdb_id)) or []
        deadline = date.today() - timedelta(days=self._config["air_buffer_days"])
        rows: List[Dict[str, Any]] = []
        # 剧集主海报在首次遇到季海报缺失时才识别，避免每部剧都多一次请求
        series_poster = ""
        series_poster_checked = False
        for season in seasons:
            if self._stop_event.is_set():
                break
            season_number = int(season.season_number or 0)
            if season_number == 0 and not self._config["include_specials"]:
                continue
            if self._config["only_existing_seasons"] and season_number not in season_map:
                continue
            episodes = self._tmdb.tmdb_episodes(tmdbid=int(tmdb_id), season=season_number) or []
            aired: List[int] = []
            for episode in episodes:
                air_date = parse_air_date(episode.air_date)
                if air_date is None or air_date > deadline:
                    continue
                episode_number = int(episode.episode_number or 0)
                if episode_number > 0:
                    aired.append(episode_number)
            if not aired:
                continue
            existing = {int(number) for number in (season_map.get(season_number) or []) if number}
            missing = sorted(set(aired) - existing)
            if not missing:
                continue
            season_poster = poster_url(getattr(season, "poster_path", None))
            if not season_poster and not series_poster_checked:
                # 季海报缺失时回退剧集主海报，同一部剧只识别一次
                series_poster = self._series_poster(tmdb_id)
                series_poster_checked = True
            rows.append(
                {
                    "server": server_name,
                    "library": library_name,
                    "title": str(item.title or ""),
                    "year": str(item.year or ""),
                    "media_source": MediaSource.TMDB.value,
                    "media_id": str(tmdb_id),
                    "season": season_number,
                    "missing": missing,
                    "aired": len(aired),
                    "existing": len(existing & set(aired)),
                    # 季海报优先，缺失时回退剧集主海报
                    "poster": season_poster or series_poster,
                }
            )
        return rows

    def _series_poster(self, tmdb_id: str) -> str:
        """读取剧集主海报，供季海报缺失时回退展示。"""
        if not self._recognize:
            return ""
        try:
            mediainfo = self._recognize(
                mtype=MediaType.TV,
                media_source=MediaSource.TMDB,
                media_id=str(tmdb_id),
            )
        except Exception as err:  # noqa: BLE001 - 海报缺失不影响缺集统计
            logger.warning(f"Emby 缺集扫描：读取剧集主海报失败：{err}")
            return ""
        poster = poster_url(getattr(mediainfo, "poster_path", None)) if mediainfo else ""
        # 识别结果使用 TMDB_IMAGE_URL 的大尺寸地址，统一收敛为列表用的 w300
        if poster.startswith("http") and "/t/p/" in poster:
            head, _, tail = poster.partition("/t/p/")
            _, sep, rest = tail.partition("/")
            if sep and rest:
                poster = f"{head}/t/p/w300/{rest}"
        return poster

    def _tmdb_id(self, item: Any) -> Optional[str]:
        """读取条目的 TMDB ID，缺失时按标题回退识别。"""
        source, media_id = resolve_media_identity(item)
        if source == MediaSource.TMDB and media_id:
            return str(media_id)
        if not self._recognize or not item.title:
            return None
        try:
            meta = MetaBase(title=str(item.title))
            meta.type = MediaType.TV
            meta.name = str(item.title)
            if item.year:
                meta.year = str(item.year)
            mediainfo = self._recognize(meta=meta, mtype=MediaType.TV)
            if not mediainfo:
                return None
            fallback_source, fallback_id = resolve_media_identity(media=mediainfo)
            if fallback_source == MediaSource.TMDB and fallback_id:
                return str(fallback_id)
        except Exception as err:  # noqa: BLE001 - 识别失败按无 TMDB ID 处理
            logger.warning(f"Emby 缺集扫描：{item.title} 回退识别失败：{err}")
        return None
