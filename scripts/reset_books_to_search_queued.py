# -*- coding: utf-8 -*-
"""
重置书籍状态脚本

将书籍状态撤回到 SEARCH_QUEUED，方便测试搜索功能。
"""

import sys
from pathlib import Path

from sqlalchemy.orm import sessionmaker

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from config.config_manager import ConfigManager
from core.state_manager import BookStateManager
from db.database import Database
from db.models import BookStatus, DoubanBook, DownloadQueue, ZLibraryBook
from utils.logger import get_logger

logger = get_logger("reset_books")


def reset_books_to_search_queued(limit: int = 10, specific_ids: list = None, force: bool = False):
    """
    重置书籍状态到SEARCH_QUEUED
    
    Args:
        limit: 重置的书籍数量限制
        specific_ids: 指定要重置的书籍ID列表
    """
    print(f"=== 重置书籍状态到SEARCH_QUEUED ===")

    config_path = Path(__file__).parent / "config.yaml"
    config_manager = ConfigManager(str(config_path))
    db = Database(config_manager)
    state_manager = BookStateManager(db)

    reset_count = 0

    with db.session_scope() as session:
        # 构建查询条件
        query = session.query(DoubanBook)

        if specific_ids:
            # 重置指定ID的书籍
            query = query.filter(DoubanBook.id.in_(specific_ids))
            print(f"重置指定ID的书籍: {specific_ids}")
        else:
            # 重置各种完成状态的书籍回到搜索队列
            target_statuses = [
                BookStatus.SEARCH_ACTIVE, BookStatus.SEARCH_COMPLETE,
                BookStatus.SEARCH_NO_RESULTS, BookStatus.DOWNLOAD_QUEUED,
                BookStatus.DOWNLOAD_COMPLETE, BookStatus.DOWNLOAD_FAILED,
                BookStatus.UPLOAD_QUEUED, BookStatus.UPLOAD_COMPLETE,
                BookStatus.UPLOAD_FAILED, BookStatus.COMPLETED,
                BookStatus.FAILED_PERMANENT
            ]
            query = query.filter(DoubanBook.status.in_(target_statuses))
            print(f"重置状态包括: {[status.value for status in target_statuses]}")

        books = query.limit(limit).all()

        if not books:
            print("没有找到需要重置的书籍")
            return 0

        print(f"找到 {len(books)} 本书籍需要重置")

        for book in books:
            old_status = book.status

            if force:
                # 强制重置：直接修改数据库，绕过状态转换验证
                book.status = BookStatus.SEARCH_QUEUED
                print(f"  强制重置: {book.title} - {old_status.value} → {BookStatus.SEARCH_QUEUED.value}")
                reset_count += 1
            else:
                # 使用状态转换验证
                success = state_manager.transition_status(
                    book.id, BookStatus.SEARCH_QUEUED,
                    f"手动重置状态：从{old_status.value}重置为测试搜索功能")
                
                if success:
                    reset_count += 1
                    print(f"  {reset_count}. {book.title} - {old_status.value} → {BookStatus.SEARCH_QUEUED.value}")
                else:
                    print(f"  ✗ 跳过: {book.title} - {old_status.value} (不允许的状态转换)")
                    print(f"    提示: 使用强制模式可以绕过状态验证")

        # 可选：清理相关的搜索结果和下载队列，重新开始
        if input("\n是否清理相关的Z-Library搜索结果和下载队列？(y/N): ").lower() == 'y':
            cleanup_count = cleanup_related_data(session,
                                                 [book.id for book in books])
            print(f"清理了 {cleanup_count} 条相关数据")

    print(f"\n成功重置 {reset_count} 本书籍的状态")
    return reset_count


def cleanup_related_data(session, book_ids: list) -> int:
    """
    清理相关的搜索结果和下载队列数据
    
    Args:
        session: 数据库会话
        book_ids: 书籍ID列表
        
    Returns:
        int: 清理的记录数量
    """
    cleanup_count = 0

    # 获取豆瓣ID列表
    douban_books = session.query(DoubanBook).filter(
        DoubanBook.id.in_(book_ids)).all()
    douban_ids = [book.douban_id for book in douban_books]

    # 清理下载队列
    download_queue_items = session.query(DownloadQueue).filter(
        DownloadQueue.douban_book_id.in_(book_ids)).all()
    for item in download_queue_items:
        session.delete(item)
        cleanup_count += 1

    # 清理Z-Library搜索结果
    zlibrary_books = session.query(ZLibraryBook).filter(
        ZLibraryBook.douban_id.in_(douban_ids)).all()
    for book in zlibrary_books:
        session.delete(book)
        cleanup_count += 1

    return cleanup_count


def show_book_status_statistics():
    """显示书籍状态统计"""
    print(f"\n=== 当前书籍状态统计 ===")

    config_path = Path(__file__).parent / "config.yaml"
    config_manager = ConfigManager(str(config_path))
    db = Database(config_manager)

    with db.session_scope() as session:
        # 统计各状态的书籍数量
        status_counts = {}
        for status in BookStatus:
            count = session.query(DoubanBook).filter(
                DoubanBook.status == status).count()
            if count > 0:
                status_counts[status.value] = count

        # 按数量排序显示
        for status, count in sorted(status_counts.items(),
                                    key=lambda x: x[1],
                                    reverse=True):
            print(f"  {status}: {count}本")

        total = sum(status_counts.values())
        print(f"\n  总计: {total}本")


def main():
    """主函数"""
    try:
        # 显示当前状态统计
        show_book_status_statistics()

        print("\n选择操作：")
        print("1. 重置指定数量的书籍到SEARCH_QUEUED（遵循状态转换规则）")
        print("2. 强制重置指定数量的书籍到SEARCH_QUEUED（绕过验证）")
        print("3. 重置指定ID的书籍到SEARCH_QUEUED（遵循状态转换规则）")
        print("4. 强制重置指定ID的书籍到SEARCH_QUEUED（绕过验证）")
        print("5. 仅显示统计信息")

        choice = input("\n请选择操作 (1-5): ").strip()

        if choice == "1":
            limit = int(input("请输入要重置的书籍数量 (默认10): ") or "10")
            reset_books_to_search_queued(limit=limit, force=False)

        elif choice == "2":
            limit = int(input("请输入要重置的书籍数量 (默认10): ") or "10")
            reset_books_to_search_queued(limit=limit, force=True)

        elif choice == "3":
            ids_input = input("请输入书籍ID，用逗号分隔: ").strip()
            if ids_input:
                specific_ids = [int(id.strip()) for id in ids_input.split(",")]
                reset_books_to_search_queued(specific_ids=specific_ids, force=False)
            else:
                print("未输入有效的书籍ID")

        elif choice == "4":
            ids_input = input("请输入书籍ID，用逗号分隔: ").strip()
            if ids_input:
                specific_ids = [int(id.strip()) for id in ids_input.split(",")]
                reset_books_to_search_queued(specific_ids=specific_ids, force=True)
            else:
                print("未输入有效的书籍ID")

        elif choice == "5":
            print("统计信息已显示")

        else:
            print("无效的选择")

        # 显示重置后的统计
        if choice in ["1", "2", "3", "4"]:
            show_book_status_statistics()

    except Exception as e:
        logger.error(f"重置失败: {str(e)}")
        print(f"重置失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
