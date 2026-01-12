"""
翻译进度显示模块
使用tqdm显示翻译流程的实时进度
"""

import time
from tqdm import tqdm
from typing import Optional, Callable
from contextlib import contextmanager


class TranslationProgress:
    """翻译进度显示器"""

    def __init__(self, verbose: bool = False):
        """初始化进度显示器

        Args:
            verbose: 是否显示详细输出
        """
        self.verbose = verbose
        self.progress_bars = {}
        self.current_stage = None
        self.total_stages = 6

    def _get_stage_name(self, stage: int) -> str:
        """获取阶段名称

        Args:
            stage: 阶段编号

        Returns:
            阶段名称
        """
        stage_names = {
            1: "准备视频文件",
            2: "提取原始音频",
            3: "语音识别(ASR)",
            4: "文本翻译",
            5: "语音合成(TTS)",
            6: "合成最终视频"
        }
        return stage_names.get(stage, f"阶段{stage}")

    def _create_stage_pbar(self, stage: int, total: int, desc: Optional[str] = None) -> tqdm:
        """创建阶段进度条

        Args:
            stage: 阶段编号
            total: 总步数
            desc: 进度条描述

        Returns:
            tqdm进度条对象
        """
        if desc is None:
            desc = self._get_stage_name(stage)

        pbar = tqdm(
            total=total,
            desc=f"[{stage}/{self.total_stages}] {desc}",
            disable=not self.verbose,
            leave=True,
            ncols=100
        )
        return pbar

    @contextmanager
    def stage(self, stage: int, desc: Optional[str] = None):
        """上下文管理器，用于管理阶段进度

        Args:
            stage: 阶段编号
            desc: 阶段描述

        Yields:
            更新进度的函数
        """
        self.current_stage = stage
        pbar = None

        try:
            if self.verbose:
                pbar = self._create_stage_pbar(stage, 100, desc)

            def update_progress(progress: int):
                """更新进度

                Args:
                    progress: 进度百分比 (0-100)
                """
                if pbar:
                    pbar.update(progress - pbar.n)

            yield update_progress

        finally:
            if pbar:
                pbar.close()

    def update_stage_progress(self, stage: int, progress: int, desc: Optional[str] = None):
        """更新指定阶段的进度

        Args:
            stage: 阶段编号
            progress: 进度百分比 (0-100)
            desc: 进度条描述
        """
        if stage not in self.progress_bars:
            if self.verbose:
                self.progress_bars[stage] = self._create_stage_pbar(stage, 100, desc)
                self.progress_bars[stage].update(progress)
        elif self.verbose:
            self.progress_bars[stage].update(progress - self.progress_bars[stage].n)

    def close_stage(self, stage: int):
        """关闭指定阶段的进度条

        Args:
            stage: 阶段编号
        """
        if stage in self.progress_bars and self.verbose:
            self.progress_bars[stage].close()
            del self.progress_bars[stage]

    def print_message(self, message: str, verbose_only: bool = False):
        """打印消息

        Args:
            message: 消息内容
            verbose_only: 是否仅在verbose模式下显示
        """
        if verbose_only and not self.verbose:
            return
        print(message)

    def print_error(self, message: str):
        """打印错误消息

        Args:
            message: 错误消息内容
        """
        print(f"\n✗ 错误: {message}")

    def print_success(self, message: str):
        """打印成功消息

        Args:
            message: 成功消息内容
        """
        print(f"✓ {message}")

    def print_warning(self, message: str):
        """打印警告消息

        Args:
            message: 警告消息内容
        """
        print(f"[警告] {message}")

    def print_stage_header(self, stage: int, message: str):
        """打印阶段标题

        Args:
            stage: 阶段编号
            message: 消息内容
        """
        print(f"\n[步骤 {stage}/{self.total_stages}] {message}")


def download_progress_callback(progress: TranslationProgress, stage: int = 1):
    """下载进度回调函数

    Args:
        progress: 进度显示器
        stage: 阶段编号
    """
    def callback(downloaded_bytes: int, total_bytes: int):
        if total_bytes > 0:
            progress_pct = int((downloaded_bytes / total_bytes) * 100)
            progress.update_stage_progress(stage, progress_pct)
    return callback


def asr_progress_callback(progress: TranslationProgress, stage: int = 3):
    """ASR进度回调函数

    Args:
        progress: 进度显示器
        stage: 阶段编号
    """
    def callback(processed_seconds: float, total_seconds: float):
        if total_seconds > 0:
            progress_pct = int((processed_seconds / total_seconds) * 100)
            progress.update_stage_progress(stage, progress_pct)
    return callback


def translation_progress_callback(progress: TranslationProgress, stage: int = 4):
    """翻译进度回调函数

    Args:
        progress: 进度显示器
        stage: 阶段编号
    """
    def callback(translated_chars: int, total_chars: int):
        if total_chars > 0:
            progress_pct = int((translated_chars / total_chars) * 100)
            progress.update_stage_progress(stage, progress_pct)
    return callback


def tts_progress_callback(progress: TranslationProgress, stage: int = 5):
    """TTS进度回调函数

    Args:
        progress: 进度显示器
        stage: 阶段编号
    """
    def callback(synthesized_chars: int, total_chars: int):
        if total_chars > 0:
            progress_pct = int((synthesized_chars / total_chars) * 100)
            progress.update_stage_progress(stage, progress_pct)
    return callback


def video_processing_progress_callback(progress: TranslationProgress, stage: int = 6):
    """视频处理进度回调函数

    Args:
        progress: 进度显示器
        stage: 阶段编号
    """
    def callback(processed_frames: int, total_frames: int):
        if total_frames > 0:
            progress_pct = int((processed_frames / total_frames) * 100)
            progress.update_stage_progress(stage, progress_pct)
    return callback
