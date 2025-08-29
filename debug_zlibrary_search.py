#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试 Z-Library 搜索结果结构
"""

import logging
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import setup_logger, get_logger
from services.zlibrary_service import ZLibraryService

def debug_zlibrary_search():
    """调试 Z-Library 搜索结果结构"""
    
    # 设置日志为DEBUG级别
    setup_logger(logging.DEBUG, "debug_zlibrary_search.log")
    logger = get_logger("debug")
    
    logger.info("=" * 60)
    logger.info("开始调试 Z-Library 搜索结果结构")
    logger.info("=" * 60)
    
    try:
        # 创建Z-Library服务
        zlib_service = ZLibraryService(
            email="test@example.com",
            password="testpassword",
            format_priority=['epub', 'mobi', 'pdf'],
            proxy_list=[],  # 空列表，不使用代理
            download_dir="test_downloads",
            max_retries=1,
            min_delay=0.1,
            max_delay=0.2
        )
        
        # 测试搜索
        logger.info("开始测试搜索...")
        test_title = "Python"
        test_author = "Mark Lutz"
        
        try:
            results = zlib_service.search_books(title=test_title, author=test_author)
            
            if results:
                logger.info(f"搜索返回了 {len(results)} 个结果")
                for i, result in enumerate(results[:3], 1):
                    logger.info(f"结果 {i}: {result}")
            else:
                logger.warning("搜索未返回任何结果")
                
        except Exception as e:
            logger.error(f"搜索过程中发生错误: {str(e)}", exc_info=True)
            
    except ImportError as e:
        logger.error(f"导入模块失败: {str(e)}")
    except Exception as e:
        logger.error(f"初始化过程中发生错误: {str(e)}", exc_info=True)
    
    logger.info("=" * 60)
    logger.info("调试完成")
    logger.info("=" * 60)

if __name__ == "__main__":
    debug_zlibrary_search()