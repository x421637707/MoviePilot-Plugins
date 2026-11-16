"""Emby 缺集扫描：展示已挂载媒体库的剧集缺集，并提供搜索与订阅补全入口。"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel, Field

from app.chain.subscribe import SubscribeChain
from app.db.oper.subscribe import SubscribeOper
from app.schemas import Response
from app.schemas.types import MediaSource, MediaType, MessageType
from app.sdk import scheduler as scheduler_sdk
from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase
from app.sdk.services import MediaServerHelper

from .page import build_summary_text, row_key
from .scanner import DEFAULT_CONFIG, MissingEpisodeScanner, normalize_config

# 一次性扫描任务 ID
SCAN_JOB_ID = "scan"
# 报告文件保存在插件数据目录中
REPORT_FILE = "report.json"


class ScanTriggerData(BaseModel):
    """触发扫描接口的业务数据。"""

    queued: bool = Field(description="是否已加入执行队列")


class SubscribeRequest(BaseModel):
    """订阅接口的请求体。"""

    title: str = Field(description="剧名")
    year: Optional[str] = Field(default=None, description="年份")
    season: Optional[int] = Field(default=None, description="季号")
    media_source: Optional[str] = Field(default=None, description="媒体数据源")
    media_id: Optional[str] = Field(default=None, description="数据源原生 ID")


class SubscribeData(BaseModel):
    """订阅接口的业务数据。"""

    subscribe_id: Optional[int] = Field(default=None, description="新增订阅 ID")
    message: str = Field(default="", description="订阅结果说明")


class ReportView(BaseModel):
    """报告查询接口的业务数据。"""

    running: bool = Field(description="是否正在扫描")
    progress: str = Field(default="", description="当前扫描进度")
    report: Optional[Dict[str, Any]] = Field(default=None, description="最近一次扫描报告")
    ignored_keys: List[str] = Field(default_factory=list, description="已忽略条目键列表")
    subscribed_keys: List[str] = Field(default_factory=list, description="已订阅条目键列表")


class IgnoreRequest(BaseModel):
    """忽略接口的请求体。"""

    key: str = Field(description="条目键，格式 {media_id}:{season}")
    title: Optional[str] = Field(default=None, description="剧名，仅用于日志")
    season: Optional[int] = Field(default=None, description="季号，仅用于日志")
    remove: bool = Field(default=False, description="True 表示取消忽略")


class IgnoreData(BaseModel):
    """忽略接口的业务数据。"""

    ignored: List[str] = Field(default_factory=list, description="当前忽略键列表")


class OptionsData(BaseModel):
    """配置选项查询接口的业务数据。"""

    servers: List[str] = Field(default_factory=list, description="已启用的 Emby 服务器名称")
    libraries: List[str] = Field(default_factory=list, description="电视剧媒体库名称")


class EmbyMissingEpisodes(_PluginBase):
    """Emby 缺集扫描插件主类：管理配置、定时与手动扫描、报告页和补全接口。"""

    plugin_name = "Emby 缺集扫描"
    plugin_desc = "扫描已挂载 Emby 媒体库的剧集缺集，报告页可直接搜索或按季订阅补全。"
    plugin_icon = "Emby_A.png"
    plugin_version = "2.0.2"
    plugin_label = "媒体库,Emby,检查"
    plugin_author = "x421637707"
    plugin_config_prefix = "embymissingepisodes_"
    plugin_order = 61
    auth_level = 1

    _enabled = False
    _config: Dict[str, Any]
    _stop_event: Optional[threading.Event] = None
    _scan_lock: Optional[threading.Lock] = None
    _progress = ""

    def __init__(self) -> None:
        """初始化宿主能力，并为实例准备独立的默认配置副本。"""
        super().__init__()
        self._config = normalize_config(None)

    def init_plugin(self, config: Optional[dict] = None) -> None:
        """读取配置并重建运行状态；勾选立即扫描时加入一次性任务。"""
        self.stop_service()
        self._config = normalize_config(config or {})
        self._enabled = self._config["enabled"]
        self._stop_event = threading.Event()
        self._scan_lock = threading.Lock()
        self._progress = ""
        if self._config["onlyonce"]:
            self._config["onlyonce"] = False
            self.update_config(dict(self._config))
            if self._enabled:
                self._queue_scan()
            else:
                logger.warning("Emby 缺集扫描：插件未启用，已忽略立即扫描")

    def get_state(self) -> bool:
        """返回插件是否启用。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """注册报告页与配置页使用的接口。"""
        return [
            {
                "path": "/scan",
                "endpoint": self.api_scan,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即扫描",
                "response_model": Response[ScanTriggerData],
            },
            {
                "path": "/subscribe",
                "endpoint": self.api_subscribe,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "按季添加订阅",
                "response_model": Response[SubscribeData],
            },
            {
                "path": "/report",
                "endpoint": self.api_report,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询缺集报告",
                "response_model": Response[ReportView],
            },
            {
                "path": "/ignore",
                "endpoint": self.api_ignore,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "忽略或取消忽略条目",
                "response_model": Response[IgnoreData],
            },
            {
                "path": "/options",
                "endpoint": self.api_options,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "查询 Emby 服务器与电视剧库名称",
                "response_model": Response[OptionsData],
            },
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """插件启用且配置了 cron 时注册定时扫描。"""
        if not self._enabled or not self._config.get("cron"):
            return []
        try:
            trigger = CronTrigger.from_crontab(self._config["cron"])
        except ValueError as err:
            logger.error(f"Emby 缺集扫描：cron 表达式无效：{err}")
            return []
        return [
            {
                "id": f"{self.__class__.__name__}.Scan",
                "name": "Emby 缺集扫描",
                "trigger": trigger,
                "func": self.run_scan,
                "kwargs": {},
            }
        ]

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """声明插件使用 Vue 联邦组件渲染页面。"""
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """Vue 联邦模式下返回默认配置，表单由远程 Config 组件渲染。"""
        return [], dict(DEFAULT_CONFIG)

    def get_page(self) -> List[dict]:
        """Vue 联邦模式下详情页由远程 Page 组件渲染。"""
        return []

    def stop_service(self) -> None:
        """通知正在执行的扫描尽快结束，并取消尚未执行的一次性扫描。"""
        if self._stop_event is not None:
            self._stop_event.set()
        try:
            scheduler_sdk.remove_plugin_once_job(self.__class__.__name__, SCAN_JOB_ID)
        except Exception as err:  # noqa: BLE001 - 调度器未运行时不影响停止
            logger.debug(f"Emby 缺集扫描：取消一次性扫描失败：{err}")

    # ------------------------------------------------------------------
    # 接口
    # ------------------------------------------------------------------

    def api_scan(self) -> Response[ScanTriggerData]:
        """加入一次性扫描任务。"""
        if not self._enabled:
            return Response(
                success=False,
                message="请先启用插件",
                data=ScanTriggerData(queued=False),
            )
        if self._is_running():
            return Response(
                success=False,
                message="已有扫描正在进行",
                data=ScanTriggerData(queued=False),
            )
        queued = self._queue_scan()
        return Response(
            success=queued,
            message="已开始扫描，稍后重新打开本页查看结果" if queued else "调度器未运行，无法开始扫描",
            data=ScanTriggerData(queued=queued),
        )

    def api_subscribe(self, payload: SubscribeRequest) -> Response[SubscribeData]:
        """按季为报告中的剧集添加订阅。"""
        title = str(payload.title or "").strip()
        if not title:
            return Response(
                success=False,
                message="剧名不能为空",
                data=SubscribeData(message="剧名不能为空"),
            )
        media_source: Optional[MediaSource] = None
        if payload.media_source:
            try:
                media_source = MediaSource(payload.media_source)
            except ValueError:
                return Response(
                    success=False,
                    message="媒体数据源无效",
                    data=SubscribeData(message="媒体数据源无效"),
                )
        media_id = str(payload.media_id or "").strip() or None
        if bool(media_source) != bool(media_id):
            return Response(
                success=False,
                message="媒体数据源与 ID 需要成对提供",
                data=SubscribeData(message="媒体数据源与 ID 需要成对提供"),
            )
        try:
            subscribe_id, message = SubscribeChain().add(
                title=title,
                year=str(payload.year or ""),
                mtype=MediaType.TV,
                season=payload.season,
                media_source=media_source,
                media_id=media_id,
                exist_ok=True,
            )
        except Exception as err:  # noqa: BLE001 - 订阅失败需要回传可读原因
            logger.error(f"Emby 缺集扫描：订阅 {title} 失败：{err}")
            return Response(
                success=False,
                message=f"订阅失败：{err}",
                data=SubscribeData(message=str(err)),
            )
        success = bool(subscribe_id)
        return Response(
            success=success,
            message=message or ("订阅成功" if success else "订阅未完成"),
            data=SubscribeData(subscribe_id=subscribe_id, message=message or ""),
        )

    def api_report(self) -> Response[ReportView]:
        """返回最近一次缺集报告，附已忽略与已订阅分组键。"""
        return Response(
            success=True,
            data=ReportView(
                running=self._is_running(),
                progress=self._progress,
                report=self._load_report(),
                ignored_keys=self._config.get("ignored") or [],
                subscribed_keys=self._subscribed_keys(),
            ),
        )

    def api_ignore(self, payload: IgnoreRequest) -> Response[IgnoreData]:
        """把条目键加入或移出忽略列表。"""
        key = str(payload.key or "").strip()
        if not key or ":" not in key:
            return Response(success=False, message="条目键无效", data=IgnoreData())
        keys = [k for k in self._config.get("ignored") or [] if k != key]
        title = str(payload.title or "条目")
        season = payload.season
        if payload.remove:
            message = f"已取消忽略：{title}"
            if season is not None:
                message += f" S{int(season):02d}"
        else:
            keys.append(key)
            message = f"已忽略：{title}"
            if season is not None:
                message += f" S{int(season):02d}，后续扫描不再展示"
        self._config["ignored"] = keys
        self.update_config(dict(self._config))
        return Response(success=True, message=message, data=IgnoreData(ignored=keys))

    def api_options(self) -> Response[OptionsData]:
        """返回已启用的 Emby 服务器名称及其电视剧库名称，供配置页下拉选择。"""
        servers, libraries = self._server_and_library_names()
        return Response(success=True, data=OptionsData(servers=servers, libraries=libraries))

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def run_scan(self) -> None:
        """执行一次完整扫描；同一实例同时只运行一个扫描，被中断的扫描不覆盖已有报告。"""
        lock = self._scan_lock
        stop_event = self._stop_event
        if lock is None or stop_event is None:
            return
        if not lock.acquire(blocking=False):
            logger.info("Emby 缺集扫描：已有扫描正在进行，跳过本次触发")
            return
        try:
            stop_event.clear()
            scanner = MissingEpisodeScanner(
                self._config,
                stop_event,
                progress=self._set_progress,
                recognize=self.chain.recognize_media,
            )
            logger.info("Emby 缺集扫描：开始扫描")
            report = scanner.scan()
            if report.get("cancelled"):
                logger.info("Emby 缺集扫描：扫描被停止，保留上一次报告")
                return
            self._save_report(report)
            logger.info(
                f"Emby 缺集扫描：扫描完成，{report.get('series')} 部剧，"
                f"{len(report.get('rows') or [])} 条缺集，耗时 {report.get('duration')} 秒"
            )
            if self._config["notify"]:
                self.post_message(
                    mtype=MessageType.Plugin,
                    title="【Emby 缺集扫描】扫描完成",
                    text=build_summary_text(report, self._config.get("ignored") or []),
                )
        except Exception as err:  # noqa: BLE001 - 后台任务需记录异常而不是静默退出
            logger.error(f"Emby 缺集扫描：扫描失败：{err}", exc_info=True)
        finally:
            self._progress = ""
            lock.release()

    def _queue_scan(self) -> bool:
        """把扫描交给宿主调度器执行一次。"""
        queued = scheduler_sdk.add_plugin_once_job(
            self.__class__.__name__,
            SCAN_JOB_ID,
            self.run_scan,
            "Emby 缺集扫描",
            delay_seconds=3,
        )
        if not queued:
            logger.warning("Emby 缺集扫描：调度器未运行，无法加入扫描任务")
        return bool(queued)

    def _is_running(self) -> bool:
        """判断当前是否有扫描正在执行。"""
        lock = self._scan_lock
        if lock is None:
            return False
        if lock.acquire(blocking=False):
            lock.release()
            return False
        return True

    def _set_progress(self, text: str) -> None:
        """记录当前扫描进度。"""
        self._progress = str(text or "")

    def _subscribed_keys(self) -> List[str]:
        """按报告行查询订阅状态，返回已订阅条目键列表。"""
        report = self._load_report()
        rows = list((report or {}).get("rows") or [])
        if not rows:
            return []
        keys: List[str] = []
        identities: Dict[str, str] = {}
        for row in rows:
            media_id = str(row.get("media_id") or "").strip()
            if media_id and str(row.get("media_source") or "") == MediaSource.TMDB.value:
                identities[media_id] = f"{media_id}:{int(row.get('season') or 0)}"
        for media_id in set(identities):
            try:
                subs = SubscribeOper().list_by_media_identity(
                    media_source=MediaSource.TMDB, media_id=media_id
                )
            except Exception as err:  # noqa: BLE001 - 查询失败按未订阅处理
                logger.warning(f"Emby 缺集扫描：查询 {media_id} 订阅状态失败：{err}")
                continue
            if not subs:
                continue
            seasons = {
                int(sub.season)
                for sub in subs
                if getattr(sub, "season", None) is not None
            }
            for row_key_value in (
                f"{media_id}:{season}" for season in seasons
            ):
                if row_key_value in identities.values():
                    keys.append(row_key_value)
            # 季号字段为空的整剧订阅视为全部季已订阅
            if any(getattr(sub, "season", None) is None for sub in subs):
                for value in identities.values():
                    if value.startswith(f"{media_id}:") and value not in keys:
                        keys.append(value)
        return keys

    def _server_and_library_names(self) -> Tuple[List[str], List[str]]:
        """返回已启用的 Emby 服务器名称及其电视剧媒体库名称，用于配置页选择。"""
        try:
            services = MediaServerHelper().get_services(type_filter="emby")
        except Exception as err:  # noqa: BLE001 - 配置读取失败时返回空列表
            logger.warning(f"Emby 缺集扫描：读取媒体服务器配置失败：{err}")
            return [], []
        servers: List[str] = []
        libraries: List[str] = []
        for name, service_info in (services or {}).items():
            servers.append(str(name))
            instance = getattr(service_info, "instance", None)
            if instance is None:
                continue
            try:
                for library in instance.get_librarys() or []:
                    if library.type == MediaType.TV.value:
                        libraries.append(str(library.name))
            except Exception as err:  # noqa: BLE001 - 单个服务器失败不影响其余
                logger.warning(f"Emby 缺集扫描：读取 {name} 媒体库失败：{err}")
        return sorted(set(servers)), sorted(set(libraries))

    # ------------------------------------------------------------------
    # 报告存储
    # ------------------------------------------------------------------

    def _report_path(self) -> Path:
        """返回报告文件路径。"""
        return Path(self.get_data_path()) / REPORT_FILE

    def _load_report(self) -> Optional[Dict[str, Any]]:
        """读取最近一次扫描报告，文件缺失或损坏时返回 None。"""
        path = self._report_path()
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except Exception as err:  # noqa: BLE001 - 损坏的报告按无数据处理
            logger.warning(f"Emby 缺集扫描：读取报告失败：{err}")
            return None

    def _save_report(self, report: Dict[str, Any]) -> None:
        """写入扫描报告。"""
        path = self._report_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = dict(report)
            payload["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception as err:  # noqa: BLE001 - 保存失败需要记录但不影响扫描结果
            logger.error(f"Emby 缺集扫描：保存报告失败：{err}")
