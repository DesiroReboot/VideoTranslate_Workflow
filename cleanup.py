"""
临时文件清理
在任务中断或完成时自动清理临时文件
"""

import os
import signal
import atexit
from pathlib import Path
from typing import Optional, Set, List
import time


class TempCleanupManager:
    """临时文件清理管理器"""

    def __init__(self, temp_dir: Optional[Path] = None):
        """初始化临时文件清理管理器

        Args:
            temp_dir: 临时文件目录，默认为temp
        """
        if temp_dir is None:
            from config import TEMP_DIR
            temp_dir = TEMP_DIR

        self.temp_dir = Path(temp_dir)
        self.keep_files: Set[str] = set()
        self.registered_handlers = False

    def register_exit_handlers(self) -> None:
        """注册退出处理器"""
        if self.registered_handlers:
            return

        atexit.register(self.cleanup_on_exit)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._signal_handler)
            except Exception:
                pass

        self.registered_handlers = True

    def _signal_handler(self, signum, frame):
        """信号处理器"""
        print("\n[中断] 接收到中断信号，正在清理临时文件...")
        self.cleanup_temp_files()
        os._exit(1)

    def keep_file(self, file_path: str) -> None:
        """标记文件不被清理

        Args:
            file_path: 文件路径
        """
        self.keep_files.add(str(Path(file_path).resolve()))

    def unkeep_file(self, file_path: str) -> None:
        """取消文件保护

        Args:
            file_path: 文件路径
        """
        file_path = str(Path(file_path).resolve())
        if file_path in self.keep_files:
            self.keep_files.remove(file_path)

    def cleanup_temp_files(self) -> int:
        """清理临时文件

        Returns:
            删除的文件数量
        """
        if not self.temp_dir.exists():
            return 0

        deleted_count = 0

        for file_path in self.temp_dir.rglob("*"):
            if file_path.is_file():
                resolved_path = str(file_path.resolve())

                if resolved_path not in self.keep_files:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception:
                        pass
            elif file_path.is_dir():
                try:
                    if not any(file_path.iterdir()):
                        file_path.rmdir()
                except Exception:
                    pass

        return deleted_count

    def cleanup_on_exit(self) -> None:
        """退出时清理"""
        try:
            deleted_count = self.cleanup_temp_files()
            if deleted_count > 0:
                print(f"[清理] 删除了 {deleted_count} 个临时文件")
        except Exception:
            pass

    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """清理旧文件

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            删除的文件数量
        """
        if not self.temp_dir.exists():
            return 0

        current_time = time.time()
        deleted_count = 0

        for file_path in self.temp_dir.rglob("*"):
            if file_path.is_file():
                resolved_path = str(file_path.resolve())

                if resolved_path in self.keep_files:
                    continue

                try:
                    file_age_hours = (
                        current_time - file_path.stat().st_mtime
                    ) / 3600

                    if file_age_hours > max_age_hours:
                        file_path.unlink()
                        deleted_count += 1
                except Exception:
                    pass

        return deleted_count

    def get_temp_files_size(self) -> int:
        """获取临时文件总大小（字节）

        Returns:
            总大小
        """
        if not self.temp_dir.exists():
            return 0

        total_size = 0

        for file_path in self.temp_dir.rglob("*"):
            if file_path.is_file():
                try:
                    total_size += file_path.stat().st_size
                except Exception:
                    pass

        return total_size

    def list_temp_files(self) -> List[str]:
        """列出临时文件

        Returns:
            文件路径列表
        """
        if not self.temp_dir.exists():
            return []

        files = []

        for file_path in self.temp_dir.rglob("*"):
            if file_path.is_file():
                files.append(str(file_path))

        return files


def cleanup_temp_files(keep_video_path: Optional[str] = None) -> int:
    """清理临时文件（全局函数）

    Args:
        keep_video_path: 需要保留的输出视频路径

    Returns:
        删除的文件数量
    """
    from config import TEMP_DIR

    temp_dir = Path(TEMP_DIR)

    if not temp_dir.exists():
        return 0

    keep_files: Set[str] = set()

    if keep_video_path:
        keep_files.add(str(Path(keep_video_path).resolve()))

    deleted_count = 0

    for file_path in temp_dir.rglob("*"):
        if file_path.is_file():
            resolved_path = str(file_path.resolve())

            if resolved_path not in keep_files:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception:
                    pass
        elif file_path.is_dir():
            try:
                if not any(file_path.iterdir()):
                    file_path.rmdir()
            except Exception:
                pass

    return deleted_count


def setup_auto_cleanup(keep_video_path: Optional[str] = None) -> TempCleanupManager:
    """设置自动清理

    Args:
        keep_video_path: 需要保留的输出视频路径

    Returns:
        清理管理器
    """
    manager = TempCleanupManager()

    if keep_video_path:
        manager.keep_file(keep_video_path)

    manager.register_exit_handlers()

    return manager


def get_temp_files_info() -> dict:
    """获取临时文件信息

    Returns:
        包含文件信息的字典
    """
    from config import TEMP_DIR

    temp_dir = Path(TEMP_DIR)

    if not temp_dir.exists():
        return {
            "exists": False,
            "files": [],
            "total_size": 0,
            "file_count": 0,
        }

    files = []
    total_size = 0
    file_count = 0

    for file_path in temp_dir.rglob("*"):
        if file_path.is_file():
            try:
                file_size = file_path.stat().st_size
                file_mtime = file_path.stat().st_mtime

                files.append({
                    "path": str(file_path),
                    "size": file_size,
                    "mtime": file_mtime,
                    "mtime_readable": time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(file_mtime)
                    ),
                })

                total_size += file_size
                file_count += 1
            except Exception:
                pass

    return {
        "exists": True,
        "path": str(temp_dir),
        "files": files,
        "total_size": total_size,
        "total_size_mb": total_size / (1024 * 1024),
        "file_count": file_count,
    }
