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


def setup_logger(log_level: int = logging.INFO,
                 log_file: Optional[str] = None,
                 console: bool = True,
                 retention_days: int = 30) -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        console: 是否输出到控制台
        retention_days: 日志保留天数
    
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

    # 添加控制台处理器
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
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
