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
        log_config = self.config_manager.get_log_config()
        log_dir = log_config.get('log_dir', 'logs')
        log_level = log_config.get('log_level', 'INFO')
        setup_logger(log_dir, log_level)
        self.logger = get_logger("main")
        
        self.logger.info("初始化豆瓣 Z-Library 同步工具")
        
        # 初始化数据库
        db_config = self.config_manager.get_db_config()
        self.db = Database(db_config)
        
        # 初始化豆瓣爬虫
        douban_config = self.config_manager.get_douban_config()
        self.douban_scraper = DoubanScraper(
            cookies=douban_config.get('cookies', {}),
            user_id=douban_config.get('user_id', ''),
            max_books=douban_config.get('max_books', 100),
            request_delay=douban_config.get('request_delay', 2.0)
        )
        
        # 初始化 Z-Library 服务
        zlib_config = self.config_manager.get_zlibrary_config()
        self.zlibrary_service = ZLibraryService(
            email=zlib_config.get('email', ''),
            password=zlib_config.get('password', ''),
            download_dir=zlib_config.get('download_dir', 'data/downloads'),
            preferred_formats=zlib_config.get('preferred_formats', ['epub', 'mobi', 'pdf'])
        )
        
        # 初始化 Calibre 服务
        calibre_config = self.config_manager.get_calibre_config()
        self.calibre_service = CalibreService(
            server_url=calibre_config.get('server_url', ''),
            username=calibre_config.get('username', ''),
            password=calibre_config.get('password', ''),
            match_threshold=calibre_config.get('match_threshold', 0.6)
        )
        
        # 初始化飞书通知服务
        lark_config = self.config_manager.get_lark_config()
        if lark_config.get('enabled', False) and lark_config.get('webhook_url'):
            self.lark_service = LarkService(
                webhook_url=lark_config.get('webhook_url', ''),
                secret=lark_config.get('secret', None)
            )
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
        self.scheduler.add_task(
            name="douban_sync",
            func=self.sync_douban_books,
            notify=True
        )
        
        # 设置调度计划
        schedule_config = self.config_manager.get_schedule_config()
        schedule_type = schedule_config.get('type', 'daily')
        
        if schedule_type == 'daily':
            self.scheduler.schedule_task(
                name="douban_sync",
                schedule_type="daily",
                at=schedule_config.get('at', '02:00')
            )
        elif schedule_type == 'weekly':
            self.scheduler.schedule_task(
                name="douban_sync",
                schedule_type="weekly",
                day=schedule_config.get('day', 0),  # 默认周一
                at=schedule_config.get('at', '02:00')
            )
        elif schedule_type == 'interval':
            hours = schedule_config.get('hours', 0)
            minutes = schedule_config.get('minutes', 0)
            
            if hours > 0:
                self.scheduler.schedule_task(
                    name="douban_sync",
                    schedule_type="interval",
                    hours=hours
                )
            elif minutes > 0:
                self.scheduler.schedule_task(
                    name="douban_sync",
                    schedule_type="interval",
                    minutes=minutes
                )
            else:
                self.logger.warning("无效的间隔设置，使用默认值: 每天 02:00")
                self.scheduler.schedule_task(
                    name="douban_sync",
                    schedule_type="daily",
                    at="02:00"
                )
        else:
            self.logger.warning(f"无效的调度类型: {schedule_type}，使用默认值: 每天 02:00")
            self.scheduler.schedule_task(
                name="douban_sync",
                schedule_type="daily",
                at="02:00"
            )
        
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
            # 测试豆瓣连接
            if not self.douban_scraper.test_connection():
                self.logger.error("豆瓣连接测试失败，请检查网络和 Cookie 设置")
                return []
            
            # 获取想读书单
            books = self.douban_scraper.get_wish_list()
            self.logger.info(f"成功获取豆瓣想读书单，共 {len(books)} 本书")
            return books
            
        except Exception as e:
            self.logger.error(f"获取豆瓣想读书单失败: {str(e)}")
            traceback.print_exc()
            return []
    
    def process_book(self, book: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        处理单本书籍：下载并上传到 Calibre
        
        Args:
            book: 书籍信息
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (是否成功, 文件路径, 错误信息)
        """
        book_title = book.get('title', '未知')
        book_author = book.get('author', '未知')
        book_isbn = book.get('isbn', '')
        
        self.logger.info(f"处理书籍: {book_title} - {book_author}")
        
        # 检查 Calibre 中是否已存在
        if self.calibre_service.test_connection():
            existing_book = self.calibre_service.find_best_match(
                title=book_title,
                author=book_author,
                isbn=book_isbn
            )
            
            if existing_book:
                self.logger.info(f"书籍已存在于 Calibre: {book_title}")
                return True, None, None
        
        # 从 Z-Library 下载
        try:
            # 测试 Z-Library 连接
            if not self.zlibrary_service.test_connection():
                error_msg = "Z-Library 连接测试失败，请检查网络和账号设置"
                self.logger.error(error_msg)
                return False, None, error_msg
            
            # 搜索并下载书籍
            download_result = self.zlibrary_service.search_and_download(
                title=book_title,
                author=book_author,
                isbn=book_isbn
            )
            
            if not download_result['success']:
                error_msg = f"从 Z-Library 下载失败: {download_result['error']}"
                self.logger.error(error_msg)
                return False, None, error_msg
            
            file_path = download_result['file_path']
            self.logger.info(f"从 Z-Library 下载成功: {file_path}")
            
            # 上传到 Calibre
            if self.calibre_service.test_connection():
                book_id = self.calibre_service.upload_book(
                    file_path=file_path,
                    metadata={
                        'title': book_title,
                        'author': book_author,
                        'isbn': book_isbn
                    }
                )
                
                if book_id:
                    self.logger.info(f"上传到 Calibre 成功: {book_title}, ID: {book_id}")
                else:
                    self.logger.warning(f"上传到 Calibre 失败: {book_title}")
            
            return True, file_path, None
            
        except Exception as e:
            error_msg = f"处理书籍失败: {str(e)}"
            self.logger.error(error_msg)
            traceback.print_exc()
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
        
        # 创建同步任务记录
        sync_task = self.db.create_sync_task()
        
        # 获取豆瓣想读书单
        books = self.fetch_douban_books()
        
        if not books:
            self.logger.warning("未获取到豆瓣想读书单，同步任务终止")
            self.db.update_sync_task(sync_task.id, {
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
        self.db.update_sync_task(sync_task.id, {
            'status': 'running',
            'total_books': len(books)
        })
        
        # 处理每本书
        success_count = 0
        failed_count = 0
        details = []
        
        for book in books:
            # 检查数据库中是否已存在
            book_isbn = book.get('isbn', '')
            book_title = book.get('title', '未知')
            book_author = book.get('author', '未知')
            
            existing_book = None
            if book_isbn:
                existing_book = self.db.get_book_by_isbn(book_isbn)
            
            if not existing_book:
                existing_book = self.db.get_book_by_title_author(book_title, book_author)
            
            # 如果书籍已存在且已下载成功，跳过
            if existing_book and existing_book.status == BookStatus.DOWNLOADED:
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
            
            # 如果书籍不存在，创建记录
            if not existing_book:
                existing_book = self.db.create_book({
                    'title': book_title,
                    'author': book_author,
                    'isbn': book_isbn,
                    'douban_id': book.get('douban_id', ''),
                    'douban_url': book.get('url', ''),
                    'cover_url': book.get('cover_url', ''),
                    'publisher': book.get('publisher', ''),
                    'publish_date': book.get('publish_date', ''),
                    'status': BookStatus.PENDING
                })
            
            # 处理书籍
            success, file_path, error_msg = self.process_book(book)
            
            # 更新书籍状态
            if success:
                self.db.update_book(existing_book.id, {
                    'status': BookStatus.DOWNLOADED,
                    'last_check': datetime.now()
                })
                
                if file_path:
                    # 创建下载记录
                    self.db.create_download_record({
                        'book_id': existing_book.id,
                        'file_path': file_path,
                        'file_format': Path(file_path).suffix[1:] if file_path else '',
                        'source': 'zlibrary',
                        'sync_task_id': sync_task.id
                    })
                
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
                        download_status=True
                    )
            else:
                self.db.update_book(existing_book.id, {
                    'status': BookStatus.FAILED,
                    'last_check': datetime.now(),
                    'error_message': error_msg
                })
                
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
                        error_message=error_msg
                    )
        
        # 更新同步任务信息
        self.db.update_sync_task(sync_task.id, {
            'status': 'completed',
            'success_count': success_count,
            'failed_count': failed_count,
            'completed_at': datetime.now()
        })
        
        # 发送同步摘要通知
        if notify and self.lark_service:
            self.lark_service.send_sync_summary(
                total=len(books),
                success=success_count,
                failed=failed_count,
                details=details
            )
        
        self.logger.info(f"同步完成: 总计 {len(books)} 本，成功 {success_count} 本，失败 {failed_count} 本")
        
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
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径"
    )
    parser.add_argument(
        "-d", "--daemon",
        action="store_true",
        help="以守护进程模式运行"
    )
    parser.add_argument(
        "-o", "--once",
        action="store_true",
        help="执行一次同步后退出"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="清理临时文件"
    )
    
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