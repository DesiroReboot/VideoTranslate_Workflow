"""
任务检查点管理
支持保存和恢复任务进度，实现断点续传
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum
import time


class TaskStage(Enum):
    """任务阶段枚举"""

    PREPARE_VIDEO = "prepare_video"
    EXTRACT_AUDIO = "extract_audio"
    SPEECH_TO_TEXT = "speech_to_text"
    TRANSLATE_TEXT = "translate_text"
    TEXT_TO_SPEECH = "text_to_speech"
    REPLACE_AUDIO = "replace_audio"
    COMPLETED = "completed"


@dataclass
class CheckpointData:
    """检查点数据"""

    task_id: str
    url_or_path: str
    target_language: str
    source_language: str
    translation_style: str
    current_stage: TaskStage
    stage_data: Dict[str, Any]
    timestamp: float
    completed_stages: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data["current_stage"] = self.current_stage.value
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        """从字典创建"""
        data = data.copy()
        data["current_stage"] = TaskStage(data["current_stage"])
        return cls(**data)


class CheckpointManager:
    """检查点管理器"""

    def __init__(self, checkpoint_dir: Optional[Path] = None):
        """初始化检查点管理器

        Args:
            checkpoint_dir: 检查点目录，默认为temp/checkpoints
        """
        if checkpoint_dir is None:
            from config import TEMP_DIR
            checkpoint_dir = TEMP_DIR / "checkpoints"

        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.current_task_id: Optional[str] = None

    def generate_task_id(self, url_or_path: str) -> str:
        """生成任务ID

        Args:
            url_or_path: URL或路径

        Returns:
            任务ID
        """
        import hashlib

        task_str = url_or_path + str(time.time())
        return hashlib.md5(task_str.encode()).hexdigest()[:16]

    def get_checkpoint_file(self, task_id: str) -> Path:
        """获取检查点文件路径

        Args:
            task_id: 任务ID

        Returns:
            检查点文件路径
        """
        return self.checkpoint_dir / f"{task_id}.json"

    def save_checkpoint(self, checkpoint: CheckpointData) -> None:
        """保存检查点

        Args:
            checkpoint: 检查点数据
        """
        checkpoint_file = self.get_checkpoint_file(checkpoint.task_id)

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)

        self.current_task_id = checkpoint.task_id

    def load_checkpoint(self, task_id: str) -> Optional[CheckpointData]:
        """加载检查点

        Args:
            task_id: 任务ID

        Returns:
            检查点数据，如果不存在则返回None
        """
        checkpoint_file = self.get_checkpoint_file(task_id)

        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return CheckpointData.from_dict(data)

    def delete_checkpoint(self, task_id: str) -> None:
        """删除检查点

        Args:
            task_id: 任务ID
        """
        checkpoint_file = self.get_checkpoint_file(task_id)

        if checkpoint_file.exists():
            checkpoint_file.unlink()

        if self.current_task_id == task_id:
            self.current_task_id = None

    def create_checkpoint(
        self,
        url_or_path: str,
        target_language: str,
        source_language: str = "auto",
        translation_style: str = "auto",
        task_id: Optional[str] = None,
    ) -> CheckpointData:
        """创建新检查点

        Args:
            url_or_path: URL或路径
            target_language: 目标语言
            source_language: 源语言
            translation_style: 翻译风格
            task_id: 任务ID，如果为None则自动生成

        Returns:
            检查点数据
        """
        if task_id is None:
            task_id = self.generate_task_id(url_or_path)

        checkpoint = CheckpointData(
            task_id=task_id,
            url_or_path=url_or_path,
            target_language=target_language,
            source_language=source_language,
            translation_style=translation_style,
            current_stage=TaskStage.PREPARE_VIDEO,
            stage_data={},
            timestamp=time.time(),
            completed_stages=[],
        )

        self.save_checkpoint(checkpoint)
        return checkpoint

    def update_stage(
        self,
        task_id: str,
        stage: TaskStage,
        stage_data: Optional[Dict[str, Any]] = None,
        mark_completed: bool = True,
    ) -> CheckpointData:
        """更新任务阶段

        Args:
            task_id: 任务ID
            stage: 新阶段
            stage_data: 阶段数据
            mark_completed: 是否标记当前阶段为已完成

        Returns:
            更新后的检查点数据
        """
        checkpoint = self.load_checkpoint(task_id)

        if checkpoint is None:
            raise ValueError(f"检查点不存在: {task_id}")

        checkpoint.current_stage = stage

        if stage_data:
            checkpoint.stage_data[stage.value] = stage_data

        if mark_completed and stage.value not in checkpoint.completed_stages:
            checkpoint.completed_stages.append(stage.value)

        checkpoint.timestamp = time.time()

        self.save_checkpoint(checkpoint)
        return checkpoint

    def complete_task(self, task_id: str, final_data: Dict[str, Any]) -> CheckpointData:
        """完成任务

        Args:
            task_id: 任务ID
            final_data: 最终数据

        Returns:
            更新后的检查点数据
        """
        checkpoint = self.load_checkpoint(task_id)

        if checkpoint is None:
            raise ValueError(f"检查点不存在: {task_id}")

        checkpoint.current_stage = TaskStage.COMPLETED
        checkpoint.stage_data["final"] = final_data
        checkpoint.timestamp = time.time()

        self.save_checkpoint(checkpoint)
        return checkpoint

    def get_stage_data(self, task_id: str, stage: TaskStage) -> Optional[Dict[str, Any]]:
        """获取阶段数据

        Args:
            task_id: 任务ID
            stage: 阶段

        Returns:
            阶段数据，如果不存在则返回None
        """
        checkpoint = self.load_checkpoint(task_id)

        if checkpoint is None:
            return None

        return checkpoint.stage_data.get(stage.value)

    def list_checkpoints(self) -> List[CheckpointData]:
        """列出所有检查点

        Returns:
            检查点列表
        """
        checkpoints = []

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                checkpoints.append(CheckpointData.from_dict(data))
            except Exception:
                pass

        checkpoints.sort(key=lambda x: x.timestamp, reverse=True)
        return checkpoints

    def clean_old_checkpoints(self, max_age_hours: int = 24) -> int:
        """清理旧检查点

        Args:
            max_age_hours: 最大保留时间（小时）

        Returns:
            删除的检查点数量
        """
        current_time = time.time()
        deleted_count = 0

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                file_age_hours = (
                    current_time - checkpoint_file.stat().st_mtime
                ) / 3600

                if file_age_hours > max_age_hours:
                    checkpoint_file.unlink()
                    deleted_count += 1
            except Exception:
                pass

        return deleted_count
