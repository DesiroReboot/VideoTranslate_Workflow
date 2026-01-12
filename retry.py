"""
智能重试机制
基于tenacity实现指数退避重试策略
"""

import time
from typing import Callable, Optional, Type, Tuple, Any
from functools import wraps
import random


class RetryError(Exception):
    """重试失败异常"""

    pass


def retry_with_exponential_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """指数退避重试装饰器

    Args:
        max_attempts: 最大重试次数
        initial_delay: 初始延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exponential_base: 指数退避基数
        jitter: 是否添加随机抖动（避免惊群效应）
        exceptions: 需要重试的异常类型
        on_retry: 重试回调函数

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        break

                    delay = min(
                        initial_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    if jitter:
                        delay = delay * (0.5 + random.random() * 0.5)

                    if on_retry:
                        on_retry(e, attempt + 1)

                    print(f"[重试] 第{attempt + 1}/{max_attempts}次重试，等待{delay:.1f}秒...")
                    time.sleep(delay)

            raise RetryError(
                f"重试{max_attempts}次后仍然失败: {last_exception}"
            ) from last_exception

        return wrapper

    return decorator


def retry_on_network_error(
    max_attempts: int = 5,
    initial_delay: float = 2.0,
    max_delay: float = 60.0,
):
    """网络错误重试装饰器

    Args:
        max_attempts: 最大重试次数
        initial_delay: 初始延迟时间（秒）
        max_delay: 最大延迟时间（秒）

    Returns:
        装饰器函数
    """
    return retry_with_exponential_backoff(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )


def retry_on_api_error(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
):
    """API错误重试装饰器

    Args:
        max_attempts: 最大重试次数
        initial_delay: 初始延迟时间（秒）
        max_delay: 最大延迟时间（秒）

    Returns:
        装饰器函数
    """
    return retry_with_exponential_backoff(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        jitter=True,
        exceptions=(Exception,),
    )


class RetryHandler:
    """重试处理器"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        """初始化重试处理器

        Args:
            max_attempts: 最大重试次数
            initial_delay: 初始延迟时间（秒）
            max_delay: 最大延迟时间（秒）
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay

    def execute_with_retry(
        self,
        func: Callable,
        *args,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        **kwargs
    ) -> Any:
        """执行函数并自动重试

        Args:
            func: 要执行的函数
            *args: 函数参数
            exceptions: 需要重试的异常类型
            on_retry: 重试回调函数
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果

        Raises:
            RetryError: 重试失败
        """
        last_exception = None

        for attempt in range(self.max_attempts):
            try:
                return func(*args, **kwargs)

            except exceptions as e:
                last_exception = e

                if attempt == self.max_attempts - 1:
                    break

                delay = min(
                    self.initial_delay * (2 ** attempt),
                    self.max_delay
                )

                if on_retry:
                    on_retry(e, attempt + 1)

                time.sleep(delay)

        raise RetryError(
            f"重试{self.max_attempts}次后仍然失败: {last_exception}"
        ) from last_exception


def create_retry_callback(context: str = "") -> Callable[[Exception, int], None]:
    """创建重试回调函数

    Args:
        context: 上下文信息

    Returns:
        回调函数
    """

    def callback(exception: Exception, attempt: int) -> None:
        error_msg = str(exception)

        if "API key" in error_msg.lower():
            print(f"[重试] API密钥错误，请检查配置")

        elif "timeout" in error_msg.lower():
            print(f"[重试] 请求超时")

        elif "connection" in error_msg.lower():
            print(f"[重试] 连接失败")

        else:
            if context:
                print(f"[重试] {context}失败，尝试第{attempt}次重试")
            else:
                print(f"[重试] 操作失败，尝试第{attempt}次重试")

    return callback
