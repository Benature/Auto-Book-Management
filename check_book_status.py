#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库中书籍的状态分布
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db.database import Database
from db.models import DoubanBook, BookStatus
from config.config_manager import ConfigManager
from utils.logger import get_logger

def check_book_status():
    """检查书籍状态分布"""
    logger = get_logger("check_book_status")
    
    try:
        config_manager = ConfigManager('config.yaml')
        db = Database(config_manager)
        
        with db.session_scope() as session:
            # 统计各状态的书籍数量
            status_counts = {}
            for status in BookStatus:
                count = session.query(DoubanBook).filter(DoubanBook.status == status).count()
                if count > 0:
                    status_counts[status.value] = count
            
            print("书籍状态分布:")
            for status, count in status_counts.items():
                print(f"  {status}: {count}")
            
            # 查找前几本书看状态
            books = session.query(DoubanBook).limit(5).all()
            print("\n前5本书的状态:")
            for book in books:
                print(f"  {book.id}: {book.title} - {book.status.value}")
                
    except Exception as e:
        logger.error(f"检查失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_book_status()