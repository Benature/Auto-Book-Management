# -*- coding: utf-8 -*-
"""
Pipeline架构核心

实现分阶段的书籍处理流程。
"""

import abc
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from sqlalchemy.orm import Session

from core.state_manager import BookStateManager
from db.models import BookStatus, DoubanBook, ProcessingTask
from utils.logger import get_logger


class ProcessingError(Exception):
    """处理错误基类"""

    def __init__(self,
                 message: str,
                 error_type: str = "system",
                 retryable: bool = True):
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


class NetworkError(ProcessingError):
    """网络错误"""

    def __init__(self, message: str):
        super().__init__(message, "network", retryable=True)


class AuthError(ProcessingError):
    """认证错误"""

    def __init__(self, message: str):
        super().__init__(message, "auth", retryable=False)


class ResourceNotFoundError(ProcessingError):
    """资源未找到错误"""

    def __init__(self, message: str):
        super().__init__(message, "not_found", retryable=False)


class DownloadLimitExhaustedError(ProcessingError):
    """下载限制耗尽错误"""

    def __init__(self, message: str, reset_time: str = None):
        super().__init__(message, "download_limit", retryable=False)
        self.reset_time = reset_time


class BaseStage(abc.ABC):
    """处理阶段基类"""

    def __init__(self, name: str, state_manager: BookStateManager):
        """
        初始化处理阶段
        
        Args:
            name: 阶段名称
            state_manager: 状态管理器
        """
        self.name = name
        self.state_manager = state_manager
        self.logger = get_logger(f"pipeline.{name}")
        self._stop_event = threading.Event()

    @abc.abstractmethod
    def can_process(self, book: DoubanBook) -> bool:
        """
        检查是否可以处理该书籍
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否可以处理
        """
        return True  # 默认允许

    @abc.abstractmethod
    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        pass

    @abc.abstractmethod
    def get_next_status(self, success: bool) -> BookStatus:
        """
        获取处理完成后的下一状态
        
        Args:
            success: 处理是否成功
            
        Returns:
            BookStatus: 下一状态
        """
        pass

    def execute(self, book: DoubanBook) -> bool:
        """
        执行处理逻辑，包含状态管理
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        start_time = datetime.now()

        try:
            self.logger.info(f"开始处理书籍: {book.title} (ID: {book.id})")

            # 重新获取book的最新状态确保一致性
            # 添加小延迟确保状态更新完全提交
            import time
            time.sleep(0.1)
            
            with self.state_manager.get_session() as session:
                fresh_book = session.query(DoubanBook).get(book.id)
                if fresh_book:
                    book.status = fresh_book.status
                    book.updated_at = fresh_book.updated_at
                    self.logger.debug(f"刷新书籍状态: {book.title}, 状态: {book.status}")
                    
                    # 如果状态不是预期的，再次强制刷新
                    session.expire_all()  # 强制从数据库重新加载
                    session.refresh(fresh_book)
                    if fresh_book.status != book.status:
                        book.status = fresh_book.status
                        book.updated_at = fresh_book.updated_at
                        self.logger.info(f"强制刷新后书籍状态: {book.title}, 状态: {book.status}")

            # 检查是否可以处理
            if not self.can_process(book):
                error_msg = f"无法处理书籍: {book.title}, 状态: {book.status.value}"
                self.logger.warning(error_msg)
                # 对于状态不匹配错误，不应该重试，而是直接跳过
                raise ProcessingError(error_msg, "status_mismatch", retryable=False)

            # 处理状态转换逻辑（仅在特定情况下需要预转换）
            if self.name == "search" and book.status == BookStatus.DETAIL_COMPLETE:
                # 搜索阶段：DETAIL_COMPLETE -> SEARCH_QUEUED -> SEARCH_ACTIVE
                self.state_manager.transition_status(book.id, BookStatus.SEARCH_QUEUED,
                                                     "准备开始搜索")
                book.status = BookStatus.SEARCH_QUEUED  # 同步本地状态
            
            # 设置为active状态
            active_status = self._get_active_status()
            if active_status:
                self.state_manager.transition_status(book.id, active_status,
                                                     f"开始{self.name}阶段处理")

            # 执行实际处理
            success = self.process(book)

            # 计算处理时间
            processing_time = (datetime.now() - start_time).total_seconds()

            # 更新状态
            next_status = self.get_next_status(success)
            change_reason = f"{self.name}阶段{'成功' if success else '失败'}"

            self.state_manager.transition_status(
                book.id,
                next_status,
                change_reason,
                processing_time=processing_time)

            self.logger.info(
                f"处理完成: {book.title}, 成功: {success}, "
                f"耗时: {processing_time:.2f}秒, 下一状态: {next_status.value}")

            return success

        except DownloadLimitExhaustedError as e:
            # 下载限制耗尽错误，不改变状态，直接返回
            self.logger.warning(f"下载限制耗尽，保持书籍在原状态: {book.title}, 重置时间: {e.reset_time}")
            # 不更改状态，让书籍保持在download_queued
            raise  # 重新抛出，让PipelineManager处理
            
        except ProcessingError as e:
            processing_time = (datetime.now() - start_time).total_seconds()

            # 根据错误类型决定下一状态
            if e.retryable:
                next_status = self._get_retry_status()
            else:
                next_status = BookStatus.FAILED_PERMANENT

            self.state_manager.transition_status(
                book.id,
                next_status,
                f"{self.name}阶段出错: {e.error_type}",
                error_message=str(e),
                processing_time=processing_time)

            self.logger.error(f"处理出错: {book.title}, 错误: {str(e)}")
            return False

        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()

            self.state_manager.transition_status(
                book.id,
                BookStatus.FAILED_PERMANENT,
                f"{self.name}阶段异常",
                error_message=str(e),
                processing_time=processing_time)

            self.logger.error(f"处理异常: {book.title}, 异常: {str(e)}")
            return False

    def _get_active_status(self) -> Optional[BookStatus]:
        """获取对应的active状态"""
        active_mapping = {
            'data_collection': BookStatus.DETAIL_FETCHING,
            'search': BookStatus.SEARCH_ACTIVE,
            'download': BookStatus.DOWNLOAD_ACTIVE,
            'upload': BookStatus.UPLOAD_ACTIVE
        }
        return active_mapping.get(self.name)

    def _get_retry_status(self) -> BookStatus:
        """获取重试时的状态"""
        retry_mapping = {
            'data_collection': BookStatus.NEW,
            'search': BookStatus.SEARCH_QUEUED,
            'download': BookStatus.DOWNLOAD_QUEUED,
            'upload': BookStatus.UPLOAD_QUEUED
        }
        return retry_mapping.get(self.name, BookStatus.FAILED_PERMANENT)

    def stop(self):
        """停止处理"""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        """检查是否已停止"""
        return self._stop_event.is_set()


class PipelineManager:
    """Pipeline管理器"""

    def __init__(self, state_manager: BookStateManager, max_workers: int = 4):
        """
        初始化Pipeline管理器
        
        Args:
            state_manager: 状态管理器实例
            max_workers: 最大工作线程数
        """
        self.state_manager = state_manager
        self.max_workers = max_workers
        self.logger = get_logger("pipeline_manager")

        # 注册的处理阶段
        self.stages: Dict[str, BaseStage] = {}

        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = False
        self._stop_event = threading.Event()

        # 活跃任务追踪
        self._active_tasks: Dict[int, Future] = {}
        self._task_lock = threading.Lock()
        
        # 阶段暂停状态
        self._paused_stages: Dict[str, str] = {}  # stage_name -> pause_reason

    def register_stage(self, stage: BaseStage):
        """
        注册处理阶段
        
        Args:
            stage: 处理阶段实例
        """
        self.stages[stage.name] = stage
        self.logger.info(f"注册处理阶段: {stage.name}")

    def start(self):
        """启动Pipeline"""
        if self._running:
            self.logger.warning("Pipeline已经在运行中")
            return

        self._running = True
        self._stop_event.clear()
        self.logger.info("Pipeline已启动")

        # 启动主处理循环
        self._main_loop()

    def stop(self):
        """停止Pipeline"""
        if not self._running:
            return

        self.logger.info("正在停止Pipeline...")
        self._running = False
        self._stop_event.set()

        # 停止所有阶段
        for stage in self.stages.values():
            stage.stop()

        # 等待所有活跃任务完成
        with self._task_lock:
            for future in self._active_tasks.values():
                future.cancel()
            self._active_tasks.clear()

        # 关闭线程池
        self.executor.shutdown(wait=True)
        self.logger.info("Pipeline已停止")

    def _main_loop(self):
        """主处理循环"""
        while self._running and not self._stop_event.is_set():
            try:
                # 处理各个阶段
                for stage_name, stage in self.stages.items():
                    if self._stop_event.is_set():
                        break

                    self._process_stage(stage_name, stage)

                # 清理完成的任务
                self._cleanup_completed_tasks()

                # 短暂休息
                time.sleep(1)

            except Exception as e:
                self.logger.error(f"主处理循环异常: {str(e)}")
                time.sleep(5)  # 出错时稍长时间休息

    def _process_stage(self, stage_name: str, stage: BaseStage):
        """
        处理单个阶段
        
        Args:
            stage_name: 阶段名称
            stage: 阶段实例
        """
        try:
            # 检查阶段是否被暂停
            if stage_name in self._paused_stages:
                pause_reason = self._paused_stages[stage_name]
                self.logger.debug(f"阶段 {stage_name} 已暂停: {pause_reason}")
                return
            
            # 阶段名到状态阶段的映射
            stage_mapping = {
                'data_collection': 'data_collection',
                'search': 'search',
                'download': 'download',
                'upload': 'upload'
            }

            stage_key = stage_mapping.get(stage_name, stage_name)

            # 获取该阶段可处理的书籍
            books = self.state_manager.get_books_by_stage(stage_key, limit=10)

            if not books:
                return

            self.logger.debug(f"阶段 {stage_name} 找到 {len(books)} 本待处理书籍")

            # 收集可处理的书籍ID，避免会话绑定问题
            processable_book_ids = []
            for book in books:
                if stage.can_process(book):
                    processable_book_ids.append((book.id, book.title))

            if not processable_book_ids:
                return

            # 检查是否还有可用的工作线程
            active_count = len(
                [f for f in self._active_tasks.values() if not f.done()])
            available_slots = self.max_workers - active_count

            if available_slots <= 0:
                return

            # 提交任务到线程池
            for book_id, book_title in processable_book_ids[:available_slots]:
                if self._stop_event.is_set():
                    break

                # 使用包装函数，在独立会话中执行阶段处理
                future = self.executor.submit(self._execute_stage_with_session,
                                              stage, book_id)

                with self._task_lock:
                    self._active_tasks[book_id] = future

                self.logger.debug(f"提交任务: 书籍 {book_title} 到阶段 {stage_name}")

        except Exception as e:
            self.logger.error(f"处理阶段 {stage_name} 时出错: {str(e)}")

    def _execute_stage_with_session(self, stage: BaseStage,
                                    book_id: int) -> bool:
        """
        在独立会话中执行阶段处理
        
        Args:
            stage: 处理阶段
            book_id: 书籍ID
            
        Returns:
            bool: 处理是否成功
        """
        try:
            # 在独立会话中获取书籍并执行处理
            with self.state_manager.get_session() as session:
                book = session.query(DoubanBook).get(book_id)
                if not book:
                    self.logger.error(f"找不到书籍: {book_id}")
                    return False

                # 执行阶段处理
                return stage.execute(book)
                
        except DownloadLimitExhaustedError as e:
            # 下载限制耗尽，暂停整个下载阶段
            self.logger.warning(f"下载限制耗尽，暂停下载阶段: {e.reset_time}")
            self._paused_stages[stage.name] = f"下载限制耗尽，重置时间: {e.reset_time}"
            return False
            
        except Exception as e:
            self.logger.error(f"执行阶段处理失败: {str(e)}")
            return False

    def _cleanup_completed_tasks(self):
        """清理已完成的任务"""
        with self._task_lock:
            completed_ids = [
                book_id for book_id, future in self._active_tasks.items()
                if future.done()
            ]

            for book_id in completed_ids:
                del self._active_tasks[book_id]

    def get_status(self) -> Dict[str, Any]:
        """
        获取Pipeline状态
        
        Returns:
            Dict[str, Any]: 状态信息
        """
        status = {
            'running': self._running,
            'active_tasks': len(self._active_tasks),
            'max_workers': self.max_workers,
            'registered_stages': list(self.stages.keys()),
            'book_statistics': self.state_manager.get_status_statistics()
        }

        return status

    def reset_stuck_tasks(self, timeout_minutes: int = 30) -> int:
        """
        重置卡住的任务
        
        Args:
            timeout_minutes: 超时时间（分钟）
            
        Returns:
            int: 重置的任务数量
        """
        return self.state_manager.reset_stuck_statuses(timeout_minutes)
    
    def resume_stage(self, stage_name: str):
        """
        恢复被暂停的阶段
        
        Args:
            stage_name: 阶段名称
        """
        if stage_name in self._paused_stages:
            pause_reason = self._paused_stages.pop(stage_name)
            self.logger.info(f"恢复阶段 {stage_name}，原暂停原因: {pause_reason}")
    
    def get_paused_stages(self) -> Dict[str, str]:
        """
        获取所有暂停的阶段
        
        Returns:
            Dict[str, str]: 暂停的阶段及其原因
        """
        return self._paused_stages.copy()
