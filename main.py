#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
豆瓣 Z-Library 同步工具

使用Pipeline架构实现分阶段处理的书籍同步工具。
"""

import argparse
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# 导入版本信息
from __version__ import __version__, get_version_info
# 导入项目模块
from config.config_manager import ConfigManager
from core.error_handler import ErrorHandler
from core.pipeline import PipelineManager
# 导入新架构组件
from core.state_manager import BookStateManager
from core.task_scheduler import ScheduledTask, TaskPriority, TaskScheduler
from db.database import Database
from db.models import BookStatus, DoubanBook
# 导入服务
from scrapers.douban_scraper import DoubanAccessDeniedException, DoubanScraper
from services.calibre_service import CalibreService
from services.lark_service import LarkService
from services.zlibrary_service import ZLibraryService
# 导入处理阶段
from stages.data_collection_stage import DataCollectionStage
from stages.download_stage import DownloadStage
from stages.search_stage import SearchStage
from stages.upload_stage import UploadStage
from utils.logger import get_logger, setup_logger


class DoubanZLibraryCalibrer:
    """豆瓣 Z-Library 同步工具主类"""

    def __init__(self, config_path: str = "config.yaml", debug_mode: bool = False):
        """
        初始化豆瓣 Z-Library 同步工具
        
        Args:
            config_path: 配置文件路径
            debug_mode: 调试模式，启用单线程pipeline
        """
        # 加载配置
        self.config_manager = ConfigManager(config_path)
        self.debug_mode = debug_mode
        
        # 设置日志
        self._setup_logging()
        self.logger = get_logger("main")
        self.logger.info(f"初始化豆瓣 Z-Library 同步工具 v{__version__}")
        
        # 初始化数据库
        self._init_database()
        
        # 初始化服务
        self._init_services()
        
        # 初始化核心组件
        self._init_core_components()
        
        # 初始化处理阶段
        self._init_stages()
        
        # 为任务调度器注册Pipeline处理器
        self._register_task_handlers()
        
        # 设置错误处理
        self._setup_error_handling()
        
        # 状态跟踪
        self._running = False
        self._shutdown_event = threading.Event()
        
        self.logger.info("豆瓣 Z-Library 同步工具初始化完成")
    
    def _setup_logging(self):
        """设置日志"""
        from utils.logger import generate_log_path
        log_config = self.config_manager.get_logging_config()
        
        if 'file' in log_config and log_config['file'] != 'logs/app.log':
            log_file = log_config['file']
        else:
            log_file = generate_log_path()
        
        import logging
        log_level = log_config.get('level', 'INFO')
        log_level_value = getattr(logging, log_level.upper(), logging.INFO)
        setup_logger(log_level_value, log_file)
    
    def _init_database(self):
        """初始化数据库"""
        self.db = Database(self.config_manager)
        
        # 检查数据库文件是否存在
        db_path = Path(self.db.db_url.replace("sqlite:///", "")).resolve()
        self.logger.info(f"数据库路径: {db_path}")
        
        if not db_path.exists():
            self.logger.info("数据库文件不存在，正在创建...")
            self.db.init_db()
    
    def _init_core_components(self):
        """初始化核心组件"""
        # 任务调度器 - 先创建，将传递给状态管理器
        max_concurrent_tasks = 1 if self.debug_mode else 10
        self.task_scheduler = TaskScheduler(
            state_manager=None,  # 稍后设置
            max_concurrent_tasks=max_concurrent_tasks
        )
        
        # 状态管理器 - 传递task_scheduler引用
        self.state_manager = BookStateManager(
            session_factory=self.db.session_factory,
            lark_service=self.lark_service,
            task_scheduler=self.task_scheduler
        )
        
        # 设置task_scheduler的state_manager引用
        self.task_scheduler.state_manager = self.state_manager
        
        # Pipeline管理器
        max_workers = 1 if self.debug_mode else 4
        self.pipeline_manager = PipelineManager(
            self.state_manager,
            max_workers=max_workers
        )
        
        if self.debug_mode:
            self.logger.info("调试模式已启用：使用单线程pipeline")
            self.logger.info(f"调试模式：限制并发任务数为 {max_concurrent_tasks}")
        
        
        # 错误处理器
        self.error_handler = ErrorHandler(self.state_manager)
    
    def _init_services(self):
        """初始化服务"""
        # 豆瓣爬虫
        douban_config = self.config_manager.get_douban_config()
        zlib_config = self.config_manager.get_zlibrary_config()
        
        self.douban_scraper = DoubanScraper(
            cookie=douban_config.get('cookie'),
            user_id=douban_config.get('user_id'),
            max_pages=douban_config.get('max_pages'),
            proxy=zlib_config.get('proxy_list', [None])[0],
            min_delay=douban_config.get('min_delay', 1.0),
            max_delay=douban_config.get('max_delay', 3.0)
        )
        
        # Z-Library服务
        self.zlibrary_service = ZLibraryService(
            email=zlib_config.get('username'),
            password=zlib_config.get('password'),
            proxy_list=zlib_config.get('proxy_list'),
            format_priority=zlib_config.get('format_priority'),
            download_dir=zlib_config.get('download_dir', 'data/downloads')
        )
        
        # Calibre服务
        calibre_config = self.config_manager.get_calibre_config()
        self.calibre_service = CalibreService(
            server_url=calibre_config.get('content_server_url'),
            username=calibre_config.get('username'),
            password=calibre_config.get('password'),
            match_threshold=calibre_config.get('match_threshold', 0.6)
        )
        
        # 飞书通知服务
        lark_config = self.config_manager.get_lark_config()
        if lark_config.get('enabled', False) and lark_config.get('webhook_url'):
            self.lark_service = LarkService(
                webhook_url=lark_config.get('webhook_url', ''),
                secret=lark_config.get('secret', None)
            )
        else:
            self.lark_service = None
    
    def _init_stages(self):
        """初始化处理阶段"""
        # 数据收集阶段
        data_collection_stage = DataCollectionStage(
            self.state_manager, self.douban_scraper
        )
        self.pipeline_manager.register_stage(data_collection_stage)
        
        # 搜索阶段
        zlib_config = self.config_manager.get_zlibrary_config()
        search_stage = SearchStage(
            self.state_manager, self.zlibrary_service,
            min_match_score=zlib_config.get('min_match_score', 0.6)
        )
        self.pipeline_manager.register_stage(search_stage)
        
        # 下载阶段
        download_stage = DownloadStage(
            self.state_manager, self.zlibrary_service,
            download_dir=zlib_config.get('download_dir', 'data/downloads')
        )
        self.pipeline_manager.register_stage(download_stage)
        
        # 上传阶段
        upload_stage = UploadStage(
            self.state_manager, self.calibre_service
        )
        self.pipeline_manager.register_stage(upload_stage)
    
    def _register_task_handlers(self):
        """为任务调度器注册Pipeline处理器"""
        def create_handler(stage_name: str):
            """创建阶段处理器包装函数"""
            def handler(task):
                """处理器函数，用于TaskScheduler调用"""
                stage = self.pipeline_manager.stages.get(stage_name)
                if not stage:
                    self.logger.error(f"找不到处理阶段: {stage_name}")
                    return False
                
                # 在持久的会话中执行处理
                with self.state_manager.get_session() as session:
                    book = session.get(DoubanBook, task.book_id)
                    if not book:
                        self.logger.error(f"找不到书籍: {task.book_id}")
                        return False
                    
                    # 执行阶段处理（这将在会话中进行）
                    success = stage.execute(book)
                    
                    # 确保book对象的修改被提交
                    if success and session.is_modified(book):
                        # 会话会在上下文管理器结束时自动提交
                        pass
                    
                    return success
            return handler
        
        # 注册各个阶段的处理器
        for stage_name in ["data_collection", "search", "download", "upload"]:
            handler = create_handler(stage_name)
            self.task_scheduler.register_handler(stage_name, handler)
        
        self.logger.info("已注册Pipeline处理器到TaskScheduler")
    
    def _setup_error_handling(self):
        """设置错误处理"""
        # 注册错误回调
        if self.lark_service:
            def auth_error_callback(data):
                """认证错误回调"""
                self.lark_service.send_403_error_notification(
                    data['error'],
                    f"阶段: {data['stage']}"
                )
            
            self.error_handler.register_error_callback('auth_forbidden', auth_error_callback)
            self.error_handler.register_error_callback('auth_login', auth_error_callback)
    
    def sync_douban_books(self, notify: bool = False) -> Dict[str, Any]:
        """
        同步豆瓣想读书单
        
        Args:
            notify: 是否发送通知
            
        Returns:
            Dict[str, Any]: 同步结果
        """
        self.logger.info("开始同步豆瓣想读书单")
        
        try:
            # 获取豆瓣想读书单
            books = self.douban_scraper.get_wish_list()
            
            if not books:
                self.logger.warning("未获取到豆瓣想读书单")
                return {
                    'success': False,
                    'total': 0,
                    'message': '未获取到豆瓣想读书单'
                }
            
            # 添加新书籍到数据库
            new_books_count = self._add_new_books_to_database(books)
            
            # 为新书籍调度Pipeline任务
            scheduled_count = self._schedule_pipeline_tasks()
            
            self.logger.info(
                f"同步完成: 新增 {new_books_count} 本书，调度 {scheduled_count} 个Pipeline任务"
            )
            
            # 发送通知
            if notify and self.lark_service:
                self.lark_service.send_sync_summary(
                    total=len(books),
                    success=new_books_count,
                    failed=0,
                    details=[]
                )
            
            return {
                'success': True,
                'total': len(books),
                'new_books': new_books_count,
                'scheduled_tasks': scheduled_count
            }
            
        except DoubanAccessDeniedException as e:
            self.logger.error(f"豆瓣访问被拒绝: {e.message}")
            if self.lark_service:
                self.lark_service.send_403_error_notification(e.message, "豆瓣想读书单页面")
            
            return {
                'success': False,
                'error': '豆瓣访问被拒绝',
                'message': str(e)
            }
        except Exception as e:
            self.logger.error(f"同步豆瓣书单失败: {str(e)}")
            return {
                'success': False,
                'error': '同步失败',
                'message': str(e)
            }
    
    def _add_new_books_to_database(self, books) -> int:
        """添加新书籍到数据库"""
        new_books_count = 0
        
        with self.db.session_scope() as session:
            for book in books:
                # 检查是否已存在
                existing_book = session.query(DoubanBook).filter(
                    (DoubanBook.douban_url == book['douban_url']) |
                    (DoubanBook.douban_id == book['douban_id'])
                ).first()
                
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
                        status=BookStatus.NEW
                    )
                    session.add(new_book)
                    new_books_count += 1
                    self.logger.info(f"添加新书: {book['title']}")
        
        return new_books_count
    
    def _schedule_pipeline_tasks(self) -> int:
        """调度Pipeline任务"""
        scheduled_count = 0
        
        # 先获取书籍IDs，避免会话绑定问题
        book_ids = []
        with self.db.session_scope() as session:
            # 获取状态为NEW的书籍ID
            new_books = session.query(DoubanBook.id).filter(
                DoubanBook.status == BookStatus.NEW
            ).all()
            book_ids = [book_id[0] for book_id in new_books]
        
        # 在会话外调度任务
        for book_id in book_ids:
            # 为每本书调度完整的Pipeline
            self.task_scheduler.schedule_book_pipeline(
                book_id=book_id,
                start_stage="data_collection"
            )
            scheduled_count += 1
        
        return scheduled_count
    
    def start_pipeline(self):
        """启动Pipeline处理"""
        if self._running:
            self.logger.warning("Pipeline已在运行中")
            return
        
        self.logger.info("启动Pipeline处理系统")
        self._running = True
        self._shutdown_event.clear()
        
        # 启动任务调度器（使用TaskScheduler统一管理任务）
        self.task_scheduler.start()
        
        # 不启动Pipeline管理器，避免与TaskScheduler冲突
        # self.pipeline_manager.start()
        
        self.logger.info("Pipeline处理系统已启动")
    
    def stop_pipeline(self):
        """停止Pipeline处理"""
        if not self._running:
            return
        
        self.logger.info("正在停止Pipeline处理系统...")
        self._running = False
        self._shutdown_event.set()
        
        # 停止任务调度器
        self.task_scheduler.stop()
        
        # Pipeline管理器没有启动，无需停止
        # self.pipeline_manager.stop()
        
        self.logger.info("Pipeline处理系统已停止")
    
    def run_once(self) -> Dict[str, Any]:
        """执行一次同步"""
        self.logger.info("执行一次同步任务")
        
        # 同步豆瓣书单
        sync_result = self.sync_douban_books(notify=True)
        
        # 如果豆瓣403错误，则跳过豆瓣同步，但继续处理现有书籍
        if not sync_result['success'] and sync_result.get('error') != '豆瓣访问被拒绝':
            return sync_result
        
        # 如果是豆瓣403错误，记录信息但继续处理
        if not sync_result['success'] and sync_result.get('error') == '豆瓣访问被拒绝':
            self.logger.warning("豆瓣403错误，跳过豆瓣同步，继续处理现有书籍进行Z-Library搜索")
        
        # 检查数据库中是否有待处理的书籍
        pending_books = self._get_pending_books_for_processing()
        if not pending_books:
            self.logger.info("没有待处理的书籍")
            return sync_result
        
        # 在debug模式下限制处理的书籍数量
        if self.debug_mode and len(pending_books) > 3:
            pending_books = pending_books[:3]
            self.logger.info(f"调试模式：限制处理书籍数量为 {len(pending_books)} 本")
        
        self.logger.info(f"发现 {len(pending_books)} 本待处理书籍，开始Pipeline处理")
        
        # 为待处理的书籍调度任务
        self._schedule_pipeline_tasks_for_books(pending_books)
        
        # 启动Pipeline处理
        self.start_pipeline()
        
        # 等待Pipeline处理完成
        self._wait_for_pipeline_completion()
        
        # 停止Pipeline
        self.stop_pipeline()
        
        return sync_result
    
    def run_daemon(self):
        """以守护进程模式运行"""
        self.logger.info("以守护进程模式启动")
        
        # 启动Pipeline系统
        self.start_pipeline()
        
        try:
            # 定期执行同步任务
            self._daemon_loop()
        except KeyboardInterrupt:
            self.logger.info("接收到终止信号，正在停止服务...")
        except Exception as e:
            self.logger.error(f"守护进程异常: {str(e)}")
        finally:
            self.stop_pipeline()
            self.logger.info("服务已停止")
    
    def _daemon_loop(self):
        """守护进程主循环"""
        # 获取调度配置
        schedule_config = self.config_manager.get_schedule_config()
        interval_hours = 24  # 默认每24小时执行一次
        
        if schedule_config.get('type') == 'interval':
            interval_hours = schedule_config.get('hours', 24)
        
        last_sync_time = datetime.now()
        
        while not self._shutdown_event.is_set():
            try:
                current_time = datetime.now()
                
                # 检查是否需要同步
                if (current_time - last_sync_time).total_seconds() >= interval_hours * 3600:
                    self.logger.info("开始定时同步")
                    sync_result = self.sync_douban_books(notify=True)
                    
                    if sync_result['success']:
                        last_sync_time = current_time
                    
                # 休眠1分钟后再检查
                if self._shutdown_event.wait(60):
                    break
                    
            except Exception as e:
                self.logger.error(f"守护进程循环异常: {str(e)}")
                time.sleep(60)
    
    def _wait_for_pipeline_completion(self, max_wait_minutes: int = 60):
        """等待Pipeline处理完成"""
        self.logger.info(f"等待Pipeline处理完成 (最大等待 {max_wait_minutes} 分钟)")
        
        start_time = datetime.now()
        
        while not self._shutdown_event.is_set():
            # 检查是否有活跃任务
            # 使用状态管理器获取书籍统计，因为pipeline_manager没有运行
            pipeline_status = {
                'running': False,
                'active_tasks': 0,
                'max_workers': 4,
                'registered_stages': ['data_collection', 'search', 'download', 'upload'],
                'book_statistics': self.state_manager.get_status_statistics()
            }
            scheduler_status = self.task_scheduler.get_status()
            
            active_tasks = (
                pipeline_status['active_tasks'] + 
                scheduler_status['active_tasks'] +
                scheduler_status['queue_size']
            )
            
            if active_tasks == 0:
                self.logger.info("Pipeline处理完成")
                break
            
            # 检查是否超时
            elapsed = datetime.now() - start_time
            if elapsed.total_seconds() > max_wait_minutes * 60:
                self.logger.warning(f"Pipeline处理超时，仍有 {active_tasks} 个活跃任务")
                break
            
            # 每30秒报告一次状态
            self.logger.info(f"Pipeline处理中，活跃任务: {active_tasks}")
            if self._shutdown_event.wait(30):
                break
    
    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        with self.db.session_scope() as session:
            status = {
                'running': self._running,
                'pipeline': pipeline_status,
                'scheduler': self.task_scheduler.get_status() if hasattr(self, 'task_scheduler') else {},
                'book_statistics': self.state_manager.get_status_statistics() if hasattr(self, 'state_manager') else {},
                'error_statistics': self.error_handler.get_error_statistics() if hasattr(self, 'error_handler') else {}
            }
        
        return status
    
    def cleanup(self):
        """清理临时文件"""
        self.logger.info("清理临时文件")
        
        system_config = self.config_manager.get_system_config()
        temp_dir = system_config.get('temp_dir', 'data/temp')
        
        if os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir)
                self.logger.info(f"临时目录已清理: {temp_dir}")
            except Exception as e:
                self.logger.error(f"清理临时文件失败: {str(e)}")
        else:
            self.logger.info(f"临时目录不存在: {temp_dir}")


    def _get_pending_books_for_processing(self) -> List[Dict[str, Any]]:
        """
        获取待处理的书籍列表
        优先处理可以直接进行下一阶段的书籍
        
        Returns:
            List[Dict[str, Any]]: 待处理的书籍信息列表 (包含id和status)
        """
        with self.db.session_scope() as session:
            # 获取各个阶段可以处理的书籍
            pending_books = []
            
            # 1. NEW状态的书籍 -> data_collection阶段
            new_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.NEW
            ).all()
            for book_id, status, title in new_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            # 2. DETAIL_COMPLETE状态的书籍 -> search阶段
            detail_complete_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.DETAIL_COMPLETE
            ).all()
            for book_id, status, title in detail_complete_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            # 3. SEARCH_QUEUED状态的书籍 -> search阶段
            search_queued_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.SEARCH_QUEUED
            ).all()
            for book_id, status, title in search_queued_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            # 4. SEARCH_COMPLETE状态的书籍 -> download阶段
            search_complete_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.SEARCH_COMPLETE
            ).all()
            for book_id, status, title in search_complete_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            # 5. DOWNLOAD_QUEUED状态的书籍 -> download阶段
            download_queued_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.DOWNLOAD_QUEUED
            ).all()
            for book_id, status, title in download_queued_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            # 6. DOWNLOAD_COMPLETE状态的书籍 -> upload阶段
            download_complete_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.DOWNLOAD_COMPLETE
            ).all()
            for book_id, status, title in download_complete_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            # 7. UPLOAD_QUEUED状态的书籍 -> upload阶段
            upload_queued_books = session.query(DoubanBook.id, DoubanBook.status, DoubanBook.title).filter(
                DoubanBook.status == BookStatus.UPLOAD_QUEUED
            ).all()
            for book_id, status, title in upload_queued_books:
                pending_books.append({'id': book_id, 'status': status, 'title': title})
            
            return pending_books
    
    def _schedule_pipeline_tasks_for_books(self, books: List[Dict[str, Any]]) -> int:
        """
        为书籍列表调度Pipeline任务
        
        Args:
            books: 书籍信息列表 (包含id和status)
            
        Returns:
            int: 调度的任务数量
        """
        scheduled_count = 0
        
        for book_info in books:
            book_id = book_info['id']
            status = book_info['status']
            title = book_info.get('title', f'书籍ID{book_id}')
            
            # 根据书籍状态确定起始阶段
            if status == BookStatus.NEW:
                stages = ['data_collection', 'search', 'download', 'upload']
            elif status == BookStatus.DETAIL_COMPLETE:
                stages = ['search', 'download', 'upload']
            elif status == BookStatus.SEARCH_QUEUED:
                stages = ['search', 'download', 'upload']
            elif status == BookStatus.SEARCH_COMPLETE:
                stages = ['download', 'upload']
            elif status == BookStatus.DOWNLOAD_QUEUED:
                stages = ['download', 'upload']
            elif status == BookStatus.DOWNLOAD_COMPLETE:
                stages = ['upload']
            elif status == BookStatus.UPLOAD_QUEUED:
                stages = ['upload']
            else:
                continue  # 跳过不需要处理的状态
            
            # 为每个阶段调度任务
            for stage in stages:
                task_id = self.task_scheduler.schedule_task(
                    book_id=book_id,
                    stage=stage,
                    priority=TaskPriority.NORMAL
                )
                self.logger.debug(f"调度任务: 书籍ID {book_id}, 阶段 {stage}, 任务ID {task_id}")
                scheduled_count += 1
                
        self.logger.info(f"为 {len(books)} 本书调度了 {scheduled_count} 个Pipeline任务")
        return scheduled_count


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="豆瓣 Z-Library 同步工具")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("-d", "--daemon", action="store_true", help="以守护进程模式运行")
    parser.add_argument("-o", "--once", action="store_true", default=True, help="执行一次同步后退出")
    parser.add_argument("--cleanup", action="store_true", help="清理临时文件")
    parser.add_argument("--status", action="store_true", help="显示系统状态")
    parser.add_argument("--debug", action="store_true", help="调试模式：单线程运行pipeline")
    parser.add_argument("-v", "--version", action="version", version=f"豆瓣 Z-Library 同步工具 v{__version__}")
    
    args = parser.parse_args()
    
    # 检查配置文件
    if not os.path.exists(args.config):
        print(f"错误: 配置文件不存在: {args.config}")
        print(f"请复制 config.yaml.example 为 {args.config} 并进行配置")
        return 1
    
    # 创建应用实例
    try:
        app = DoubanZLibraryCalibrer(args.config, debug_mode=args.debug)
        
        # 执行相应操作
        if args.cleanup:
            app.cleanup()
            return 0
        
        if args.status:
            status = app.get_status()
            import json
            print(json.dumps(status, indent=2, ensure_ascii=False, default=str))
            return 0
        
        if args.daemon:
            app.run_daemon()
        elif args.once:
            result = app.run_once()
            if not result['success']:
                print(f"同步失败: {result.get('message', 'Unknown error')}")
                return 1
        
        return 0
        
    except Exception as e:
        print(f"应用启动失败: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())