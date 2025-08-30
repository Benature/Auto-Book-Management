# -*- coding: utf-8 -*-
"""
调试状态重置脚本

用于调试状态转换问题。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from config.config_manager import ConfigManager
from db.database import Database
from db.models import DoubanBook, BookStatus
from utils.logger import get_logger

logger = get_logger("debug_reset")


def debug_status_reset():
    """调试状态重置"""
    print("=== 调试状态重置 ===")
    
    config_path = Path(__file__).parent / "config.yaml"
    config_manager = ConfigManager(str(config_path))
    db = Database(config_manager)
    
    # 方法1：直接在数据库层面重置，绕过state_manager
    with db.session_scope() as session:
        # 找一些需要重置的书籍
        books = session.query(DoubanBook).filter(
            DoubanBook.status.in_([
                BookStatus.SEARCH_COMPLETE,
                BookStatus.SEARCH_NO_RESULTS,
                BookStatus.DOWNLOAD_COMPLETE,
                BookStatus.COMPLETED
            ])
        ).limit(5).all()
        
        if not books:
            print("没有找到需要重置的书籍")
            return
        
        print(f"找到 {len(books)} 本书籍需要重置")
        
        for i, book in enumerate(books, 1):
            old_status = book.status
            print(f"\n{i}. 处理书籍: {book.title}")
            print(f"   当前状态: {old_status.value}")
            
            # 直接修改status字段
            book.status = BookStatus.SEARCH_QUEUED
            print(f"   设置新状态: {BookStatus.SEARCH_QUEUED.value}")
            
            # 手动提交这一本书的更改
            try:
                session.commit()
                print(f"   ✓ 状态更新成功")
                
                # 立即查询验证
                session.refresh(book)
                current_status = book.status
                print(f"   验证结果: {current_status.value}")
                
                if current_status == BookStatus.SEARCH_QUEUED:
                    print(f"   ✓ 状态重置成功")
                else:
                    print(f"   ✗ 状态重置失败，仍为: {current_status.value}")
                    
            except Exception as e:
                session.rollback()
                print(f"   ✗ 状态更新失败: {e}")
    
    print("\n=== 重置完成，验证最终状态 ===")
    
    # 最终验证
    with db.session_scope() as session:
        search_queued_books = session.query(DoubanBook).filter(
            DoubanBook.status == BookStatus.SEARCH_QUEUED
        ).count()
        print(f"SEARCH_QUEUED状态的书籍数量: {search_queued_books}")


def simple_status_check():
    """简单的状态检查"""
    print("=== 当前状态统计 ===")
    
    config_path = Path(__file__).parent / "config.yaml"
    config_manager = ConfigManager(str(config_path))
    db = Database(config_manager)
    
    with db.session_scope() as session:
        # 统计各状态的书籍数量
        for status in BookStatus:
            count = session.query(DoubanBook).filter(
                DoubanBook.status == status
            ).count()
            if count > 0:
                print(f"  {status.value}: {count}本")


if __name__ == "__main__":
    try:
        print("选择操作：")
        print("1. 调试状态重置")
        print("2. 仅显示状态统计")
        
        choice = input("\n请选择操作 (1-2): ").strip()
        
        if choice == "1":
            debug_status_reset()
        elif choice == "2":
            simple_status_check()
        else:
            print("无效选择")
            
    except Exception as e:
        logger.error(f"调试失败: {str(e)}")
        print(f"调试失败: {str(e)}")
        import traceback
        traceback.print_exc()