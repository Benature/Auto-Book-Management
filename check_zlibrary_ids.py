#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中Z-Library书籍的ID字段
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging

from config.config_manager import ConfigManager
from db.database import Database
from db.models import ZLibraryBook
from utils.logger import get_logger, setup_logger


def check_zlibrary_ids():
    """检查数据库中的Z-Library ID字段"""
    
    logger = setup_logger(
        log_level=logging.DEBUG,
        console=True,
        log_file=None,
        use_icons=True,
        icon_type='ascii'
    )
    
    try:
        config_manager = ConfigManager('config.yaml')
        db = Database(config_manager)
        
        with db.session_scope() as session:
            # 查找有下载链接的书籍
            books = session.query(ZLibraryBook).filter(
                ZLibraryBook.download_url != '',
                ZLibraryBook.download_url.isnot(None)
            ).limit(3).all()
            
            logger.info(f"找到 {len(books)} 本有下载链接的书籍")
            
            for i, book in enumerate(books, 1):
                logger.info(f"\n=== 书籍 {i} ===")
                logger.info(f"ID: {book.id}")
                logger.info(f"ZLibrary ID: '{book.zlibrary_id}'")
                logger.info(f"标题: {book.title[:50]}...")
                logger.info(f"下载URL: {book.download_url}")
                
                # 检查字段是否为空或None
                if not book.zlibrary_id:
                    logger.warning("⚠️  ZLibrary ID 为空!")
                    
                if not book.id:
                    logger.warning("⚠️  主键ID 为空!")
                    
    except Exception as e:
        logger.error(f"检查失败: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_zlibrary_ids()