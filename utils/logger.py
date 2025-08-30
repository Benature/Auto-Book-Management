# -*- coding: utf-8 -*-
"""
日志工具

提供日志记录功能。
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
import sys
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

# 定义颜色
COLOR = {
    "DEBUG": "\033[90m",     # 深灰色（更好的对比度）
    "INFO": "\033[94m",      # 亮蓝色
    "WARNING": "\033[93m",   # 亮黄色
    "ERROR": "\033[91m",     # 亮红色
    "CRITICAL": "\033[97m\033[41m",  # 白字红底
}

# 定义日志级别图标
ASCII_ICONS = {
    "DEBUG": "[D]",     # Debug
    "INFO": "[I]",      # Info
    "WARNING": "[W]",   # Warning
    "ERROR": "[E]",     # Error
    "CRITICAL": "[C]",  # Critical
}

EMOJI_ICONS = {
    "DEBUG": "🔍",     # 🔍 放大镜
    "INFO": "ℹ️",       # ℹ️ 信息
    "WARNING": "⚠️",   # ⚠️ 警告
    "ERROR": "❌",       # ❌ 错误
    "CRITICAL": "🛑",   # 🛑 紧急停车
}

RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    def __init__(self, fmt=None, datefmt=None, use_icons=True, icon_type='ascii'):
        super().__init__(fmt, datefmt)
        self.use_icons = use_icons
        self.icon_type = icon_type
        self.icons = ASCII_ICONS if icon_type == 'ascii' else EMOJI_ICONS

    def format(self, record):
        """格式化日志记录为彩色输出"""
        log_color = COLOR.get(record.levelname, RESET)
        
        # 先保存原始的levelname
        original_levelname = record.levelname
        
        # 如果启用图标，修改record的levelname
        if self.use_icons:
            icon = self.icons.get(record.levelname, "")
            if icon:
                record.levelname = f"{icon}{record.levelname}"
        
        # 格式化消息
        message = super().format(record)
        
        # 恢复原始的levelname
        record.levelname = original_levelname
        
        return f"{log_color}{message}{RESET}"


def generate_log_path(base_dir: str = "logs") -> str:
    """
    生成日志文件路径
    格式: logs/yyyymmdd/applog-yyyymmddhhmmss.log
    
    Args:
        base_dir: 日志基础目录
        
    Returns:
        str: 完整的日志文件路径
    """
    now = datetime.now()
    date_dir = now.strftime("%Y%m%d")
    log_filename = f"applog-{now.strftime('%Y%m%d%H%M%S')}.log"
    return os.path.join(base_dir, date_dir, log_filename)


def setup_logger(log_level: int = logging.DEBUG,
                 log_file: Optional[str] = None,
                 console: bool = True,
                 retention_days: int = 30,
                 use_icons: bool = True,
                 icon_type: str = 'ascii') -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        console: 是否输出到控制台
        retention_days: 日志保留天数
        use_icons: 是否使用图标
        icon_type: 图标类型 ('ascii' 或 'emoji')
    
    Returns:
        logger: 日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger("douban_zlib")
    logger.setLevel(log_level)
    logger.handlers = []  # 清除已有的处理器

    # 设置日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    
    # 设置彩色格式器（用于控制台）
    color_formatter = ColorFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        use_icons=use_icons,
        icon_type=icon_type
    )

    # 添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        # 使用 TimedRotatingFileHandler 进行日志轮转
        file_handler = TimedRotatingFileHandler(log_file,
                                                when="midnight",
                                                interval=1,
                                                backupCount=retention_days,
                                                encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # 添加控制台处理器（使用彩色格式）
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        # 检查是否支持颜色（TTY环境）
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            console_handler.setFormatter(color_formatter)
        else:
            console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        logger: 日志记录器
    """
    if name:
        return logging.getLogger(f"douban_zlib.{name}")
    return logging.getLogger("douban_zlib")


def log_exception(logger: logging.Logger,
                  e: Exception,
                  context: str = "") -> None:
    """
    记录异常信息
    
    Args:
        logger: 日志记录器
        e: 异常对象
        context: 上下文信息
    """
    if context:
        logger.error(f"{context}: {str(e)}")
    else:
        logger.error(str(e))
    logger.debug(f"异常详情: ", exc_info=True)
