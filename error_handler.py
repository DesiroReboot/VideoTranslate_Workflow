"""
全局异常处理器
提供统一的异常捕获和友好错误提示
"""

import sys
import traceback
from typing import Optional, Callable, Any
from functools import wraps
from pathlib import Path
import time


class VideoTranslateError(Exception):
    """视频翻译系统基础异常"""

    pass


class NetworkError(VideoTranslateError):
    """网络相关异常"""

    pass


class APIError(VideoTranslateError):
    """API调用异常"""

    pass


class FileError(VideoTranslateError):
    """文件操作异常"""

    pass


class AudioProcessingError(VideoTranslateError):
    """音频处理异常"""

    pass


class ValidationError(VideoTranslateError):
    """参数验证异常"""

    pass


class ErrorHandler:
    """全局错误处理器"""

    def __init__(self, log_file: Optional[str] = None):
        """初始化错误处理器

        Args:
            log_file: 错误日志文件路径
        """
        self.log_file = log_file

    def log_error(
        self,
        error: Exception,
        context: Optional[str] = None,
        verbose: bool = False
    ) -> str:
        """记录错误到日志文件

        Args:
            error: 异常对象
            context: 错误上下文信息
            verbose: 是否输出详细堆栈信息

        Returns:
            错误消息
        """
        error_type = type(error).__name__
        error_msg = str(error)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {error_type}: {error_msg}\n"

        if context:
            log_entry += f"Context: {context}\n"

        if verbose:
            log_entry += f"Traceback:\n{traceback.format_exc()}"

        if self.log_file:
            try:
                log_path = Path(self.log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(log_entry + "\n")
            except Exception:
                pass

        return error_msg

    def handle_exception(
        self,
        error: Exception,
        context: Optional[str] = None,
        raise_on_error: bool = False,
        verbose: bool = False
    ) -> Optional[str]:
        """处理异常

        Args:
            error: 异常对象
            context: 错误上下文信息
            raise_on_error: 是否重新抛出异常
            verbose: 是否显示详细错误信息

        Returns:
            友好的错误消息
        """
        error_msg = self.log_error(error, context, verbose)

        if raise_on_error:
            raise

        return error_msg

    def get_user_friendly_message(self, error: Exception) -> str:
        """获取用户友好的错误消息

        Args:
            error: 异常对象

        Returns:
            友好的错误消息
        """
        error_type = type(error).__name__
        error_msg = str(error)

        error_messages = {
            "NetworkError": "网络连接失败，请检查网络连接后重试",
            "APIError": f"API调用失败: {error_msg}",
            "FileError": f"文件操作失败: {error_msg}",
            "AudioProcessingError": f"音频处理失败: {error_msg}",
            "ValidationError": f"参数验证失败: {error_msg}",
            "KeyboardInterrupt": "操作已取消",
            "ConnectionError": "连接失败，请检查网络连接",
            "TimeoutError": "操作超时，请稍后重试",
            "FileNotFoundError": f"文件不存在: {error_msg}",
            "PermissionError": f"权限不足: {error_msg}",
        }

        if error_type in error_messages:
            return error_messages[error_type]

        if "API key" in error_msg.lower():
            return "API密钥未配置或无效，请检查环境变量"

        if "DASHSCOPE_API_KEY" in error_msg:
            return "阿里云API密钥未配置，请设置 DASHSCOPE_API_KEY 环境变量"

        return f"处理失败: {error_msg}"


def handle_errors(
    context: Optional[str] = None,
    raise_on_error: bool = False,
    log_file: Optional[str] = None
):
    """错误处理装饰器

    Args:
        context: 错误上下文信息
        raise_on_error: 是否重新抛出异常
        log_file: 错误日志文件路径

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            handler = ErrorHandler(log_file=log_file)

            try:
                return func(*args, **kwargs)

            except KeyboardInterrupt:
                error = KeyboardInterrupt()
                friendly_msg = handler.get_user_friendly_message(error)
                print(f"\n[取消] {friendly_msg}")
                if raise_on_error:
                    raise
                return None

            except VideoTranslateError as e:
                handler.log_error(e, context)
                friendly_msg = handler.get_user_friendly_message(e)
                print(f"[错误] {friendly_msg}")
                if raise_on_error:
                    raise
                return None

            except Exception as e:
                handler.log_error(e, context, verbose=True)
                friendly_msg = handler.get_user_friendly_message(e)
                print(f"[错误] {friendly_msg}")
                if raise_on_error:
                    raise
                return None

        return wrapper

    return decorator


def setup_global_exception_handler(log_file: Optional[str] = None):
    """设置全局异常处理器

    Args:
        log_file: 错误日志文件路径
    """

    def handle_exception(
        exc_type: type,
        exc_value: Exception,
        exc_traceback: Any
    ):
        handler = ErrorHandler(log_file=log_file)

        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        handler.log_error(exc_value, verbose=True)
        friendly_msg = handler.get_user_friendly_message(exc_value)
        print(f"\n[严重错误] {friendly_msg}")
        print("详细的错误信息已记录到日志文件")

    sys.excepthook = handle_exception
