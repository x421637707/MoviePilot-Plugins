import re
from typing import Any, List, Optional, Tuple

from app.plugins import _PluginBase
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.schemas import NotificationType, ServiceInfo
from app.schemas.event import ResourceDownloadEventData
from app.schemas.types import ChainEventType, EventType
from app.sdk.services import DownloaderHelper
from app.sdk.utilities import StringUtils

try:
    from app.application.directory import DirectoryHelper
except ImportError:  # pragma: no cover - 老版本兜底
    DirectoryHelper = None


class HRRedirect(_PluginBase):
    """
    H&R 下载助手：命中 H&R 规则的资源改走配置的下载目录，并整体覆盖下载器标签，可选通知。
    """

    # 插件名称
    plugin_name = "H&R助手自用版"
    # 插件描述
    plugin_desc = "命中 H&R（Hit & Run）规则的资源自动改走所选下载目录，并整体覆盖下载器标签、可选通知。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/redirect.png"
    # 插件版本
    plugin_version = "1.1.6"
    # 插件作者
    plugin_author = "x421637707"
    # 作者主页
    author_url = "https://github.com/jxxghp/MoviePilot-Plugins"
    # 插件配置项ID前缀
    plugin_config_prefix = "hrredirect_"
    # 加载顺序（须早于 downloadsitetag=2，保证先覆盖后追加站点标签）
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 1

    _enabled = False
    _notify = True
    _library_dir = ""
    _label = ""
    _sites = ""

    def __init__(self):
        """
        初始化基类设施（chain/plugindata 等）与 H&R 站点匹配正则缓存。
        """
        super().__init__()
        self._hr_sites = []
        self._hr_sites_pattern = None

    def init_plugin(self, config: dict = None):
        """
        读取插件配置并重建 H&R 站点匹配正则。
        """
        self._enabled = bool(config.get("enabled")) if config else False
        self._notify = bool(config.get("notify", True)) if config else True
        self._library_dir = (config.get("library_dir") or "").strip() if config else ""
        self._label = (config.get("label") or "").strip() if config else ""
        self._sites = (config.get("sites") or "").strip() if config else ""
        self._rebuild_sites_pattern()

    def _rebuild_sites_pattern(self):
        """
        将手动配置的站点名列表编译为整词正则，供 H&R 兜底判定复用。
        """
        self._hr_sites = [s.strip() for s in re.split(r"[,，、\s]+", self._sites) if s.strip()]
        if self._hr_sites:
            self._hr_sites_pattern = re.compile(
                "|".join(re.escape(site) for site in self._hr_sites), re.IGNORECASE
            )
        else:
            self._hr_sites_pattern = None

    def _is_hit(self, torrent_info: Any) -> bool:
        """
        判断种子是否命中 H&R 规则：优先系统识别的 hit_and_run 标记，其次手动站点列表兜底。
        """
        if torrent_info is None:
            return False
        if bool(getattr(torrent_info, "hit_and_run", False)):
            return True
        site_name = getattr(torrent_info, "site_name", None)
        if site_name and self._hr_sites_pattern:
            return bool(self._hr_sites_pattern.search(site_name))
        return False

    def _site_name(self, torrent_info: Any) -> str:
        """
        读取种子的站点名，供通知文案展示。
        """
        return getattr(torrent_info, "site_name", None) or "未知站点"

    def _resolve_download_path(self) -> Optional[str]:
        """
        解析配置的目录对应的下载路径。

        :return: 下载重定向路径；未配置或未匹配到含下载路径的目录时返回 None
        """
        if not self._library_dir or DirectoryHelper is None:
            return None
        try:
            for dir_info in DirectoryHelper().get_dirs() or []:
                if (getattr(dir_info, "name", "") or "").strip() != self._library_dir:
                    continue
                download_path = (getattr(dir_info, "download_path", "") or "").strip()
                if download_path:
                    return download_path
                logger.warn(f"[HRRedirect] 目录「{self._library_dir}」未设置下载路径，无法重定向")
                return None
            logger.warn(f"[HRRedirect] 未找到名为「{self._library_dir}」的目录配置，请检查目录设置")
        except Exception as err:
            logger.error(f"[HRRedirect] 解析下载目录失败：{str(err)}")
        return None

    @staticmethod
    def _option_path(option: Any) -> str:
        """
        从事件 options 中读取 save_path，兼容字符串与 dict 两种承载方式。
        """
        if not option:
            return ""
        if isinstance(option, dict):
            value = option.get("save_path")
        else:
            value = getattr(option, "save_path", None)
        return (value or "").strip() if isinstance(value, str) else ""

    @staticmethod
    def _set_option_path(option: Any, path: str):
        """
        将改写后的 save_path 写回事件 options，优先 dict 形式并尽量保留原对象。
        """
        if isinstance(option, dict):
            option["save_path"] = path
            return
        try:
            option["save_path"] = path
        except TypeError:
            # options 为不可变对象时降级为属性写入（由事件模型尝试持久化）
            try:
                setattr(option, "save_path", path)
            except Exception:
                pass

    @eventmanager.register(ChainEventType.ResourceDownload)
    def on_resource_download(self, event: Event):
        """
        下载提交前事件：命中 H&R 且配置了下载目录时，将下载重定向到该目录。
        """
        if not self._enabled or not event or not event.event_data:
            return
        try:
            data: ResourceDownloadEventData = event.event_data
            redirect_path = self._resolve_download_path()
            if not redirect_path:
                return
            if not self._is_hit(getattr(data.context, "torrent_info", None)):
                return
            existed = self._option_path(data.options)
            if existed and existed != redirect_path:
                logger.info(
                    f"[HRRedirect] {self._site_name(getattr(data.context, 'torrent_info', None))} "
                    f"H&R 资源已由其他组件指定下载目录 {existed}，保持不变"
                )
                return
            self._set_option_path(data.options, redirect_path)
            logger.info(
                f"[HRRedirect] H&R 资源下载目录已重定向：{redirect_path}"
                + (f"（原指定 {existed}）" if existed else "")
            )
        except Exception as err:
            logger.error(f"[HRRedirect] 处理 ResourceDownload 事件失败：{str(err)}")

    @staticmethod
    def _field(data: Any, key: str):
        """
        从事件数据中读取字段，兼容 dict 与 schema 对象两种承载方式。

        v3 的 DownloadAdded 事件实际发送 dict 载荷（history.py event_payload），
        不能按 schema 属性硬访问。
        """
        if isinstance(data, dict):
            return data.get(key)
        return getattr(data, key, None)

    @eventmanager.register(EventType.DownloadAdded)
    def on_download_added(self, event: Event):
        """
        下载任务落库后事件：对命中 H&R 的任务整体覆盖下载器标签，并按需发送通知。
        """
        if not self._enabled or not event or not event.event_data:
            return
        try:
            data = event.event_data
            hash_value = self._field(data, "hash")
            torrent_hash = hash_value.strip() if isinstance(hash_value, str) else (hash_value or "")
            if not torrent_hash:
                return
            torrent_info = getattr(self._field(data, "context"), "torrent_info", None)
            if not self._is_hit(torrent_info):
                return
            site_name = self._site_name(torrent_info)
            downloader_name = self._field(data, "downloader")
            applied = self._apply_tags(torrent_hash, downloader_name)
            if self._notify:
                site_name = site_name or "未知站点"
                download_path = self._resolve_download_path() or ""
                if applied:
                    text = (
                        f"🌐 站点：{site_name}\n"
                        f"📒 目录：{download_path or '（未配置）'}\n"
                        f"💾 大小：{StringUtils.str_filesize(getattr(torrent_info, 'size', 0) or 0)}\n"
                        f"🏷️ 标签：{self._label or '（空）'}\n"
                        f"📦 种子：{getattr(torrent_info, 'title', None) or '未知'}\n"
                        f"📝 描述：{getattr(torrent_info, 'description', None) or '（无）'}"
                    )
                else:
                    text = (
                        f"🌐 站点：{site_name}\n"
                        f"📒 目录：{download_path or '（未配置）'}\n"
                        f"📦 种子：{getattr(torrent_info, 'title', None) or '未知'}\n"
                        f"⚠️ 标签覆盖未执行：未找到下载器 {downloader_name or '（未知）'} 或该下载器不支持标签"
                    )
                title = "🎯 H&R 任务"
                page_url = (getattr(torrent_info, "page_url", None) or "").strip()
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title=title,
                    text=text,
                    link=page_url or None,
                )
        except Exception as err:
            logger.error(f"[HRRedirect] 处理 DownloadAdded 事件失败：{str(err)}")

    def _apply_tags(self, torrent_hash: str, downloader_name: Optional[str]) -> bool:
        """
        在指定下载器上整体覆盖任务标签；qBittorrent/Transmission 支持，其余跳过。
        """
        if not downloader_name:
            logger.warn("[HRRedirect] 事件缺少下载器名称，跳过标签覆盖")
            return False
        services: dict = DownloaderHelper().get_services(name_filters=[downloader_name]) or {}
        service: ServiceInfo = services.get(downloader_name)
        if not service:
            logger.warn(f"[HRRedirect] 未找到下载器 {downloader_name}，跳过标签覆盖")
            return False
        stype = (getattr(service, "type", "") or "").lower()
        try:
            if stype == "qbittorrent":
                service.instance.qbc.torrents_set_tags(
                    tags=[self._label] if self._label else [],
                    torrent_hashes=torrent_hash,
                )
            elif stype == "transmission":
                service.instance.trc.change_torrent(
                    ids=torrent_hash,
                    labels=[self._label] if self._label else [],
                )
            else:
                logger.info(f"[HRRedirect] 下载器 {downloader_name}（{stype}）不支持标签，跳过")
                return False
        except Exception as err:
            err_text = str(err)
            if stype == "qbittorrent" and ("404" in err_text or "409" in err_text or "Not Found" in err_text):
                logger.error(
                    f"[HRRedirect] 覆盖标签失败（{downloader_name}）：{err_text}"
                    "（提示：torrents_setTags 需要 qBittorrent 5.1 及以上版本）"
                )
            else:
                logger.error(f"[HRRedirect] 覆盖标签失败（{downloader_name}）：{err_text}")
            return False
        logger.info(f"[HRRedirect] 已覆盖任务 {torrent_hash} 标签为：{self._label or '（空）'}")
        return True

    def _download_dir_options(self) -> List[dict]:
        """
        构建表单可用的下载目录下拉选项。

        仅列出下载器监控（monitor_type=downloader）且设置下载路径的目录配置，
        选中值保存目录名称，运行时按名称反查下载路径。
        """
        options: List[dict] = [{"title": "（留空 - 不干预下载目录）", "value": ""}]
        if DirectoryHelper is None:
            return options
        try:
            for dir_info in DirectoryHelper().get_dirs() or []:
                if (getattr(dir_info, "monitor_type", "") or "") != "downloader":
                    continue
                name = (getattr(dir_info, "name", "") or "").strip()
                download_path = (getattr(dir_info, "download_path", "") or "").strip()
                if not name or not download_path:
                    continue
                options.append({
                    "title": f"{name}：{download_path}",
                    "value": name,
                })
        except Exception as err:
            logger.error(f"[HRRedirect] 获取下载目录选项失败：{str(err)}")
        return options

    def get_state(self) -> bool:
        """
        返回插件启用状态。
        """
        return self._enabled

    @staticmethod
    def get_command() -> Optional[dict]:
        """
        插件不注册任何命令。
        """
        pass

    def get_api(self) -> Optional[List[dict]]:
        """
        插件不提供额外 API。
        """
        pass

    def get_form(self) -> Tuple[List[dict], dict]:
        """
        构建插件配置表单：开关、下载目录下拉、标签、站点列表与通知开关。
        """
        site_tip = "站点名以逗号分隔，仅作自动识别失效时的兜底；留空表示只信系统 H&R 标记"
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "发送通知",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "label",
                                            "label": "H&R 标签",
                                            "placeholder": "如：HR",
                                            "hint": "下载后整体覆盖为该标签，留空则清空标签",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "library_dir",
                                            "label": "H&R 下载目录",
                                            "items": self._download_dir_options(),
                                            "hint": "命中 H&R 的资源将下载到所选目录；选项为目录设置中的下载目录",
                                            "persistent-hint": True,
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "sites",
                                            "label": "H&R 站点兜底列表",
                                            "placeholder": "站点1,站点2",
                                            "hint": site_tip,
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {
            "enabled": False,
            "notify": True,
            "library_dir": "",
            "label": "",
            "sites": "",
        }

    def get_page(self) -> Optional[List[dict]]:
        """
        插件不提供独立页面。
        """
        pass

    def stop_service(self, ret: Any = None):
        """
        停止插件服务，当前无后台任务需要清理。
        """
        pass

    def __update_config(self, model: dict):
        """
        保存表单配置并刷新运行时状态。
        """
        self.update_config(model)
        self.init_plugin(model)
