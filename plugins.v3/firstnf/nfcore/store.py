"""任务持久化存储。

协议：JsonTaskStore —— 内存字典 + save/load。
宿主实现 HostDataStore 走插件基类 save_data/get_data；
独立实现 FileTaskStore 写 JSON 文件，供测试与宿主外运行。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from .state import FirstNFTask


class JsonTaskStore(Protocol):
    """任务存储协议。"""

    def load(self) -> Dict[str, FirstNFTask]:
        """读取全部任务。"""

    def save(self, tasks: Dict[str, FirstNFTask]) -> None:
        """全量保存任务（内部保证原子写）。"""


class MemoryTaskStore:
    """内存存储（测试与演示用）。"""

    def __init__(self) -> None:
        self._tasks: Dict[str, FirstNFTask] = {}
        self._lock = threading.Lock()

    def load(self) -> Dict[str, FirstNFTask]:
        """返回任务字典副本。"""
        with self._lock:
            return dict(self._tasks)

    def save(self, tasks: Dict[str, FirstNFTask]) -> None:
        """覆盖保存。"""
        with self._lock:
            self._tasks = dict(tasks)


class FileTaskStore:
    """JSON 文件存储（原子写：临时文件 + 替换）。"""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def load(self) -> Dict[str, FirstNFTask]:
        """从文件读取任务；文件不存在或损坏时返回空字典。"""
        with self._lock:
            if not self.path.exists():
                return {}
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
            tasks: Dict[str, FirstNFTask] = {}
            for key, data in (raw.get("tasks") or {}).items():
                tasks[key] = FirstNFTask.from_dict(data)
            return tasks

    def save(self, tasks: Dict[str, FirstNFTask]) -> None:
        """原子写入 JSON 文件。"""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"tasks": {k: t.to_dict() for k, t in tasks.items()}}
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)


class HostDataStore:
    """宿主存储：包装插件基类的 save_data/get_data。

    宿主侧 save_data/get_data 为同步方法（见官方 V3 插件开发指南 7.2/7.3）。
    为容忍不同实现，读写均做 try/except 并回退内存缓存。
    """

    def __init__(self, plugin: Any, key: str = "firstnf_tasks") -> None:
        self._plugin = plugin
        self._key = key
        self._cache: Dict[str, FirstNFTask] = {}
        self._lock = threading.Lock()

    def load(self) -> Dict[str, FirstNFTask]:
        """优先读宿主数据，失败回退内存缓存。"""
        with self._lock:
            try:
                raw = self._plugin.get_data(self._key)
                if isinstance(raw, str):
                    raw = json.loads(raw)
                if isinstance(raw, dict):
                    tasks = {
                        k: FirstNFTask.from_dict(v)
                        for k, v in (raw.get("tasks") or {}).items()
                    }
                    self._cache = tasks
                    return dict(tasks)
            except Exception:
                pass
            return dict(self._cache)

    def save(self, tasks: Dict[str, FirstNFTask]) -> None:
        """先更新缓存再尝试写宿主；写失败不影响运行（看门狗会重试）。"""
        with self._lock:
            self._cache = dict(tasks)
            payload = {"tasks": {k: t.to_dict() for k, t in tasks.items()}}
            try:
                self._plugin.save_data(self._key, payload)
            except Exception:
                pass


def active_tasks(tasks: Dict[str, FirstNFTask]) -> List[FirstNFTask]:
    """筛选仍处于活动状态的任务。"""
    return [task for task in tasks.values() if task.is_active]
