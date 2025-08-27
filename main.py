#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
豆瓣 Z-Library 同步工具

主程序入口，整合所有模块并提供命令行接口。
"""

import os
import sys
import argparse
import time
from pathlib import Path
import logging
import shutil
from typing import Dict, Any, List, Optional, Tuple
import yaml
import traceback
from datetime import datetime

# 导入项目模块
from config.config_manager import ConfigManager
from utils.logger import setup_logger, get_logger
from db.database import Database
from db.models import BookStatus, DoubanBook, DownloadRecord, SyncTask
from datetime import datetime
from scrapers.douban_scraper import DoubanScraper
from services.zlibrary_service import ZLibraryService
from services.calibre_service import CalibreService
from services.lark_service import LarkService
from scheduler.task_scheduler import TaskScheduler


class DoubanZLibrary:
    """豆瓣 Z-Library 同步工具主类"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化豆瓣 Z-Library 同步工具
        
        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        self.config_manager = ConfigManager(config_path)

        # 设置日志
        import logging
        log_config = self.config_manager.get_logging_config()
        log_file = log_config.get('file', 'logs/app.log')
        log_level = log_config.get('level', 'INFO')
        log_level_value = getattr(logging, log_level.upper(), logging.INFO)
        setup_logger(log_level_value, log_file)
        self.logger = get_logger("main")

        self.logger.info("初始化豆瓣 Z-Library 同步工具")

        # 初始化数据库
        db_url = self.config_manager.get_database_url()
        self.db = Database(db_url)

        # 检查数据库文件是否存在
        db_path = Path(db_url.replace("sqlite:///", "")).resolve()
        self.logger.info(f"最终数据库路径为: {db_path}")
        if not db_path.exists():
            self.logger.info("数据库文件不存在，正在创建...")
            self.db.init_db()

        # 初始化豆瓣爬虫
        douban_config = self.config_manager.get_douban_config()
        zlib_config = self.config_manager.get_zlibrary_config()
        self.douban_scraper = DoubanScraper(
            cookie=douban_config.get('cookie'),
            user_id=douban_config.get('user_id'),
            max_pages=douban_config.get('max_pages'),
            proxy=zlib_config.get('proxy_list', [None])[0])

        # 初始化 Z-Library 服务
        zlib_config = self.config_manager.get_zlibrary_config()
        self.zlibrary_service = ZLibraryService(
            email=zlib_config.get('username'),
            password=zlib_config.get('password'),
            format_priority=zlib_config.get('format_priority'),
            proxy_list=zlib_config.get('proxy_list'),
            download_dir=zlib_config.get('download_dir', 'data/downloads'))

        # 初始化 Calibre 服务
        calibre_config = self.config_manager.get_calibre_config()
        self.calibre_service = CalibreService(
            server_url=calibre_config.get('content_server_url'),
            username=calibre_config.get('username'),
            password=calibre_config.get('password'),
            match_threshold=calibre_config.get('match_threshold', 0.6))

        # 初始化飞书通知服务
        lark_config = self.config_manager.get_lark_config()
        if lark_config.get('enabled',
                           False) and lark_config.get('webhook_url'):
            self.lark_service = LarkService(
                webhook_url=lark_config.get('webhook_url', ''),
                secret=lark_config.get('secret', None))
        else:
            self.lark_service = None

        # 初始化任务调度器
        self.scheduler = TaskScheduler()

        # 系统配置
        self.system_config = self.config_manager.get_system_config()

        self.logger.info("豆瓣 Z-Library 同步工具初始化完成")

    def setup_scheduler(self) -> None:
        """
        设置任务调度器
        """
        self.logger.info("设置任务调度器")

        # 添加同步任务
        self.scheduler.add_task(name="douban_sync",
                                func=self.sync_douban_books,
                                notify=True)

        # 设置调度计划
        schedule_config = self.config_manager.get_schedule_config()
        schedule_type = schedule_config.get('type', 'daily')

        if schedule_type == 'daily':
            self.scheduler.schedule_task(name="douban_sync",
                                         schedule_type="daily",
                                         at=schedule_config.get('at', '02:00'))
        elif schedule_type == 'weekly':
            self.scheduler.schedule_task(
                name="douban_sync",
                schedule_type="weekly",
                day=schedule_config.get('day', 0),  # 默认周一
                at=schedule_config.get('at', '02:00'))
        elif schedule_type == 'interval':
            hours = schedule_config.get('hours', 0)
            minutes = schedule_config.get('minutes', 0)

            if hours > 0:
                self.scheduler.schedule_task(name="douban_sync",
                                             schedule_type="interval",
                                             hours=hours)
            elif minutes > 0:
                self.scheduler.schedule_task(name="douban_sync",
                                             schedule_type="interval",
                                             minutes=minutes)
            else:
                self.logger.warning("无效的间隔设置，使用默认值: 每天 02:00")
                self.scheduler.schedule_task(name="douban_sync",
                                             schedule_type="daily",
                                             at="02:00")
        else:
            self.logger.warning(f"无效的调度类型: {schedule_type}，使用默认值: 每天 02:00")
            self.scheduler.schedule_task(name="douban_sync",
                                         schedule_type="daily",
                                         at="02:00")

        # 启动调度器
        self.scheduler.start()
        self.logger.info("任务调度器设置完成并启动")

    def fetch_douban_books(self) -> List[Dict[str, Any]]:
        """
        获取豆瓣想读书单
        
        Returns:
            List[Dict[str, Any]]: 书籍信息列表
        """
        self.logger.info("开始获取豆瓣想读书单")

        try:
            # 获取想读书单
            books = self.douban_scraper.get_wish_list()
            self.logger.info(f"成功获取豆瓣想读书单，共 {len(books)} 本书")
            return books

        except Exception as e:
            self.logger.error(f"获取豆瓣想读书单失败: {str(e)}")
            traceback.print_exc()
            return []

    def process_book(
            self,
            book: Dict[str, Any],
            book_id: int = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        处理单本书籍：下载并上传到 Calibre
        
        Args:
            book: 书籍信息
            book_id: 书籍在数据库中的ID（可选）
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (是否成功, 文件路径, 错误信息)
        """
        book_title = book.get('title', '未知')
        book_author = book.get('author', '未知')
        book_isbn = book.get('isbn', '')

        self.logger.info(f"处理书籍: {book_title} - {book_author}")

        # 检查 Calibre 中是否已存在
        existing_book = self.calibre_service.find_best_match(
            title=book_title, author=book_author, isbn=book_isbn)

        if existing_book:
            self.logger.info(f"书籍已存在于 Calibre: {book_title}")
            if book_id:
                self.db.update_book_status(book_id, BookStatus.MATCHED)
            return True, None, None

        # 从 Z-Library 下载
        try:
            # 更新状态为搜索中
            if book_id:
                with self.db.session_scope() as session:
                    book_obj = session.query(DoubanBook).filter(
                        DoubanBook.id == book_id).first()
                    if book_obj:
                        book_obj.status = BookStatus.SEARCHING

            # 搜索并下载书籍
            download_result = self.zlibrary_service.search_and_download(
                title=book_title, author=book_author, isbn=book_isbn)

            if not download_result or not download_result.get('success'):
                error_msg = f"从 Z-Library 下载失败: {download_result.get('error') if download_result else '未找到资源'}"
                self.logger.error(error_msg)
                if book_id:
                    with self.db.session_scope() as session:
                        book_obj = session.query(DoubanBook).filter(
                            DoubanBook.id == book_id).first()
                        if book_obj:
                            book_obj.status = BookStatus.SEARCH_NOT_FOUND
                return False, None, error_msg

            # 更新状态为下载中
            if book_id:
                with self.db.session_scope() as session:
                    book_obj = session.query(DoubanBook).filter(
                        DoubanBook.id == book_id).first()
                    if book_obj:
                        book_obj.status = BookStatus.DOWNLOADING

            file_path = download_result['file_path']
            self.logger.info(f"从 Z-Library 下载成功: {file_path}")

            # 更新状态为已下载
            if book_id:
                with self.db.session_scope() as session:
                    book_obj = session.query(DoubanBook).filter(
                        DoubanBook.id == book_id).first()
                    if book_obj:
                        book_obj.status = BookStatus.DOWNLOADED

            # 更新状态为上传中
            if book_id:
                with self.db.session_scope() as session:
                    book_obj = session.query(DoubanBook).filter(
                        DoubanBook.id == book_id).first()
                    if book_obj:
                        book_obj.status = BookStatus.UPLOADING

            # 上传到 Calibre
            book_id_calibre = self.calibre_service.upload_book(
                file_path=file_path,
                metadata={
                    'title': book_title,
                    'author': book_author,
                    'isbn': book_isbn
                })

            if book_id_calibre:
                self.logger.info(
                    f"上传到 Calibre 成功: {book_title}, ID: {book_id_calibre}")
                if book_id:
                    with self.db.session_scope() as session:
                        book_obj = session.query(DoubanBook).filter(
                            DoubanBook.id == book_id).first()
                        if book_obj:
                            book_obj.status = BookStatus.UPLOADED
            else:
                self.logger.warning(f"上传到 Calibre 失败: {book_title}")

            return True, file_path, None

        except Exception as e:
            error_msg = f"处理书籍失败: {str(e)}"
            self.logger.error(error_msg)
            traceback.print_exc()
            if book_id:
                with self.db.session_scope() as session:
                    book_obj = session.query(DoubanBook).filter(
                        DoubanBook.id == book_id).first()
                    if book_obj:
                        book_obj.status = BookStatus.SEARCH_NOT_FOUND
            return False, None, error_msg

    def sync_douban_books(self, notify: bool = False) -> Dict[str, Any]:
        """
        同步豆瓣想读书单到 Z-Library 和 Calibre
        
        Args:
            notify: 是否发送通知
            
        Returns:
            Dict[str, Any]: 同步结果
        """
        self.logger.info("开始同步豆瓣想读书单")

        # 获取豆瓣想读书单
        books = self.douban_scraper.get_wish_list()
        if not books:
            self.logger.warning("未获取到豆瓣想读书单")
            return

        # 创建同步任务
        sync_task_id = self.db.create_sync_task()

        # 检查并添加新书籍到数据库
        new_books_count = 0
        existing_books_count = 0
        with self.db.session_scope() as session:
            for book in books:
                # 通过豆瓣URL、ISBN或标题和作者组合查找已存在的书籍
                existing_book = session.query(DoubanBook).filter(
                    (DoubanBook.douban_url == book['douban_url'])
                    | ((DoubanBook.isbn != None)
                       & (DoubanBook.isbn == book.get('isbn')))
                    | ((DoubanBook.title == book['title'])
                       & (DoubanBook.author == book['author']))).first()

                if not existing_book:
                    new_book = DoubanBook(
                        title=book['title'],
                        author=book['author'],
                        isbn=book.get('isbn'),
                        douban_id=book['douban_id'],
                        douban_url=book['douban_url'],
                        cover_url=book.get('cover_url'),
                        publisher=book.get('publisher'),
                        publish_date=book.get('publish_date'),
                        status=BookStatus.NEW)
                    session.add(new_book)
                    new_books_count += 1
                    self.logger.info(f"添加新书: {book['title']}")
                else:
                    existing_books_count += 1
                    self.logger.info(f"书籍已存在: {book['title']}")

            self.logger.info(
                f"本次同步: 新增 {new_books_count} 本书，已存在 {existing_books_count} 本书")

        # 获取状态为 NEW 的书籍的详细信息
        with self.db.session_scope() as session:
            new_books = session.query(DoubanBook).filter(
                DoubanBook.status == BookStatus.NEW).all()
            self.logger.info(f"发现 {len(new_books)} 本新书，开始获取详细信息")
            for book in new_books:
                book_detail = self.douban_scraper.get_book_detail(
                    book.douban_url)
                if book_detail:
                    book.isbn = book_detail.get('isbn', book.isbn)
                    book.original_title = book_detail.get('original_title')
                    book.subtitle = book_detail.get('subtitle')
                    book.summary = book_detail.get('summary')
                    book.status = BookStatus.WITH_DETAIL
                    self.logger.info(f"获取书籍详细信息成功: {book.title}")

            # 获取状态为 WITH_DETAIL 的书籍
            books_to_search = session.query(DoubanBook).filter(
                DoubanBook.status == BookStatus.WITH_DETAIL).all()

        if not books:
            self.logger.warning("未获取到豆瓣想读书单，同步任务终止")
            self.db.update_sync_task(
                sync_task_id, {
                    'status': 'failed',
                    'total_books': 0,
                    'success_count': 0,
                    'failed_count': 0,
                    'error_message': '未获取到豆瓣想读书单'
                })
            return {
                'success': False,
                'total': 0,
                'success_count': 0,
                'failed_count': 0,
                'details': []
            }

        # 更新同步任务信息
        self.db.update_sync_task(sync_task_id, {
            'status': 'running',
            'total_books': len(books_to_search)
        })

        # 处理每本书
        success_count = 0
        failed_count = 0
        details = []

        for book in books_to_search:
            # 获取书籍信息
            book_isbn = book.isbn
            book_title = book.title
            book_author = book.author

            with self.db.session_scope() as session:
                # 如果书籍已下载成功，跳过
                if book.status == BookStatus.DOWNLOADED:
                    self.logger.info(f"书籍已存在且已下载: {book_title}")
                    success_count += 1
                    details.append({
                        'title': book_title,
                        'author': book_author,
                        'isbn': book_isbn,
                        'status': 'skipped',
                        'message': '书籍已存在且已下载'
                    })
                    continue

                # 处理书籍
                success, file_path, error_msg = self.process_book(
                    {
                        'title': book_title,
                        'author': book_author,
                        'isbn': book_isbn,
                        'douban_id': book.douban_id,
                        'douban_url': book.douban_url,
                        'cover_url': book.cover_url,
                        'publisher': book.publisher,
                        'publish_date': book.publish_date
                    }, book.id)

                # 更新书籍状态
                if success:
                    # 状态已在 process_book 中更新为 DOWNLOADED 或 UPLOADED
                    existing_book.last_check = datetime.now()

                    if file_path:
                        # 创建下载记录
                        download_record = DownloadRecord(
                            book_id=existing_book.id,
                            file_path=file_path,
                            file_format=Path(file_path).suffix[1:]
                            if file_path else '',
                            source='zlibrary',
                            sync_task_id=sync_task_id)
                        session.add(download_record)

                    success_count += 1
                    details.append({
                        'title': book_title,
                        'author': book_author,
                        'isbn': book_isbn,
                        'status': 'success',
                        'file_path': file_path
                    })

                    # 发送通知
                    if notify and self.lark_service:
                        self.lark_service.send_book_notification(
                            book_info={
                                'title': book_title,
                                'author': book_author,
                                'isbn': book_isbn
                            },
                            download_status=True)
                else:
                    existing_book.status = BookStatus.SEARCH_NOT_FOUND
                    existing_book.last_check = datetime.now()
                    existing_book.error_message = error_msg

                    failed_count += 1
                    details.append({
                        'title': book_title,
                        'author': book_author,
                        'isbn': book_isbn,
                        'status': 'failed',
                        'message': error_msg
                    })

                    # 发送通知
                    if notify and self.lark_service:
                        self.lark_service.send_book_notification(
                            book_info={
                                'title': book_title,
                                'author': book_author,
                                'isbn': book_isbn
                            },
                            download_status=False,
                            error_message=error_msg)

        # 更新同步任务信息
        self.db.update_sync_task(
            sync_task_id, {
                'status': 'completed',
                'success_count': success_count,
                'failed_count': failed_count,
                'completed_at': datetime.now()
            })

        # 发送同步摘要通知
        if notify and self.lark_service:
            self.lark_service.send_sync_summary(total=len(books_to_search),
                                                success=success_count,
                                                failed=failed_count,
                                                details=details)

        self.logger.info(
            f"同步完成: 总计 {len(books_to_search)} 本，成功 {success_count} 本，失败 {failed_count} 本"
        )

        return {
            'success': True,
            'total': len(books),
            'success_count': success_count,
            'failed_count': failed_count,
            'details': details
        }

    def run_daemon(self) -> None:
        """
        以守护进程模式运行
        """
        self.logger.info("以守护进程模式启动")

        # 设置任务调度器
        self.setup_scheduler()

        try:
            # 保持程序运行
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("接收到终止信号，正在停止服务...")
            self.scheduler.stop()
            self.logger.info("服务已停止")
        except Exception as e:
            self.logger.error(f"运行异常: {str(e)}")
            traceback.print_exc()
            self.scheduler.stop()

    def run_once(self) -> Dict[str, Any]:
        """
        执行一次同步
        
        Returns:
            Dict[str, Any]: 同步结果
        """
        self.logger.info("执行一次同步任务")
        return self.sync_douban_books(notify=True)

    def cleanup(self) -> None:
        """
        清理临时文件
        """
        self.logger.info("清理临时文件")

        temp_dir = self.system_config.get('temp_dir', 'data/temp')
        if os.path.exists(temp_dir):
            try:
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                self.logger.info(f"临时目录已清理: {temp_dir}")
            except Exception as e:
                self.logger.error(f"清理临时文件失败: {str(e)}")
        else:
            self.logger.info(f"临时目录不存在: {temp_dir}")


def main():
    """
    主函数
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="豆瓣 Z-Library 同步工具")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("-d",
                        "--daemon",
                        action="store_true",
                        help="以守护进程模式运行")
    parser.add_argument("-o",
                        "--once",
                        action="store_true",
                        default=True,
                        help="执行一次同步后退出")
    parser.add_argument("--cleanup", action="store_true", help="清理临时文件")

    args = parser.parse_args()

    # 检查配置文件是否存在
    if not os.path.exists(args.config):
        print(f"错误: 配置文件不存在: {args.config}")
        print(f"请复制 config.yaml.example 为 {args.config} 并进行配置")
        return 1

    # 创建应用实例
    app = DoubanZLibrary(args.config)

    # 根据命令行参数执行相应操作
    if args.cleanup:
        app.cleanup()

    if args.once:
        app.run_once()
    elif args.daemon:
        app.run_daemon()
    else:
        # 默认执行一次同步
        app.run_once()

    return 0


if __name__ == "__main__":
    sys.exit(main())
