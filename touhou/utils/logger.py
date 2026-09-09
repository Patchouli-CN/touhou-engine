"""日志工具 桥接标准 logging 到 Loguru"""

# GensokyoAI\utils\logging.py

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging as std_logging
import os
import sys
from pathlib import Path

import loguru
from loguru import logger

# 默认关闭完整堆栈，避免日志被异常 traceback 刷屏；可通过环境变量开启
_LOGURU_FULL_TRACEBACK = os.environ.get("LOGURU_FULL_TRACEBACK", "0").lower() in (
    "1",
    "true",
    "yes",
)

# 默认抑制部分底层库的低级别日志，避免污染终端/文件
_SUPPRESSED_LOW_LEVEL_LOGGERS = {"httpcore", "asyncio", "aiohttp"}

# 第三方框架的命名空间：WARNING 以下一律丢弃
_SUPPRESSED_THIRD_PARTY_LOGGERS = {"nonebot", "uvicorn", "websockets"}


def _third_party_noise_filter(record) -> bool:
    """Loguru sink 过滤器：第三方框架只保留 WARNING 及以上，自家日志不受限。"""
    name = (record["name"] or "").split(".")[0]
    if name in _SUPPRESSED_THIRD_PARTY_LOGGERS:
        return bool(record["level"].no >= logger.level("WARNING").no)
    return True


# 移除默认配置
logger.remove()

# 保存 handler IDs 以便后续管理
_handlers: dict[str, int | None] = {"console": None, "file": None}


class LoguruHandler(std_logging.Handler):
    def emit(self, record: std_logging.LogRecord):
        # 抑制 httpcore/asyncio/aiohttp.access 等库的 DEBUG/INFO 日志
        if (
            record.name.split(".")[0] in _SUPPRESSED_LOW_LEVEL_LOGGERS
            and record.levelno < std_logging.WARNING
        ):
            return

        # 关闭 uvicorn 关闭级联噪音
        if record.name.split(".")[0] == "uvicorn":
            exc_type = record.exc_info[0] if record.exc_info else None
            if exc_type is not None and issubclass(
                exc_type, (KeyboardInterrupt, asyncio.CancelledError)
            ):
                return
            message = record.getMessage()
            if message.startswith("Traceback") and (
                "KeyboardInterrupt" in message
                or "asyncio.exceptions.CancelledError" in message
            ):
                return

        # 把其他库的 DEBUG 降级为我们的 TRACE
        level: str | int
        if record.levelno == std_logging.DEBUG:
            level = "TRACE"
        else:
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (
            depth == 0 or frame.f_code.co_filename == std_logging.__file__
        ):
            frame = frame.f_back
            depth += 1

        exc = (
            record.exc_info
            if _LOGURU_FULL_TRACEBACK or record.levelno >= std_logging.ERROR
            else False
        )

        logger.opt(depth=depth, exception=exc, colors=False).bind(
            module=record.name.split(".")[0].upper()
        ).log(level, "{}", record.getMessage())


class LoggerManager:
    """模块级 Logger 管理器

    通过 bind(module=...) 为每个模块创建带前缀的 logger，
    内部缓存已创建的实例，避免重复 bind。
    """

    _cache: dict[str, loguru.Logger] = {}

    @staticmethod
    def get_logger(module_name: str):
        """获取带模块前缀的 logger

        Args:
            module_name: 模块名称，如 "BRAIN", "SECURITY", "PAYMENT"

        Returns:
            绑定了 module 字段的 loguru logger 实例

        Example:
            >>> brain = LoggerManager.get_logger("BRAIN")
            >>> brain.critical("service cannot start, exit")
            [ MainThread  ] | 22:47:15 | BRAIN            | CRITICAL | service cannot start, exit
        """
        if module_name not in LoggerManager._cache:
            LoggerManager._cache[module_name] = logger.bind(module=module_name)
        return LoggerManager._cache[module_name]


def setup_logging(
    log_level: str = "INFO",
    log_console: bool = True,
    log_file: str | Path | None = None,
    log_format: str | None = None,
    log_format_console: str | None = None,
    intercept_standard_logging: bool = True,
) -> None:
    """配置日志系统

    Args:
        log_level: 日志级别 (TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_console: 是否输出到控制台
        log_file: 日志文件路径
        log_format: 文件日志格式
        log_format_console: 控制台日志格式
        intercept_standard_logging: 是否拦截标准 logging 库的日志
    """
    global _handlers

    # 移除现有 handlers
    if _handlers["console"] is not None:
        with contextlib.suppress(ValueError):
            logger.remove(_handlers["console"])
        _handlers["console"] = None
    if _handlers["file"] is not None:
        with contextlib.suppress(ValueError):
            logger.remove(_handlers["file"])
        _handlers["file"] = None

    # 默认格式 —— 带模块前缀
    if log_format is None:
        log_format = (
            "[ {thread.name:^12} ] | {time:HH:mm:ss} | "
            "{extra[module]:<16} | {level:<8} | {message}"
        )

    if log_format_console is None:
        log_format_console = (
            "<level>"
            "[ {thread.name:^12} ] | {time:HH:mm:ss} | "
            "{extra[module]:<16} | {level:<8} | {message}"
            "</level>"
        )

    # 添加控制台 handler
    if log_console:
        _handlers["console"] = logger.add(
            sys.stderr,
            format=log_format_console,
            level=log_level,
            colorize=True,
            filter=_third_party_noise_filter,
        )

    # 添加文件 handler
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        _handlers["file"] = logger.add(
            str(log_file),
            format=log_format,
            level=log_level,
            rotation="10 MB",
            compression="zip",
            backtrace=_LOGURU_FULL_TRACEBACK,
            diagnose=_LOGURU_FULL_TRACEBACK,
            enqueue=True,
            filter=_third_party_noise_filter,
        )

    # 拦截标准 logging
    if intercept_standard_logging:
        root_logger = std_logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.addHandler(LoguruHandler())
        root_logger.setLevel(std_logging.DEBUG)


# 为了兼容性，保留原有的 logger 导出
__all__ = [
    "logger",
    "setup_logging",
    "LoguruHandler",
    "LoggerManager",
]


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("测试 1: 模块级 Logger")
    print("=" * 60)

    setup_logging(log_level="TRACE", log_console=True)

    brain = LoggerManager.get_logger("BRAIN")
    security = LoggerManager.get_logger("SECURITY")
    payment = LoggerManager.get_logger("PAYMENT")

    brain.trace("initializing neural network")
    brain.debug("loading model weights")
    security.info("user login success")
    payment.warning("payment retry, attempt=2")
    brain.error("model inference failed")
    brain.critical("service cannot start, exit")

    print("\n" + "=" * 60)
    print("测试 2: 缓存验证（同一模块返回同一实例）")
    print("=" * 60)

    brain2 = LoggerManager.get_logger("BRAIN")
    print(f"brain is brain2: {brain is brain2}")  # True

    print("\n" + "=" * 60)
    print("测试 3: 标准 logging 桥接")
    print("=" * 60)

    std_logging.info("这是标准 logging 的 INFO 日志")
    std_logging.warning("这是标准 logging 的 WARNING 日志")
