# -*- coding: utf-8 -*-
"""
任务调度器

管理不同阶段的任务队列和调度。
"""

import heapq
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from core.error_handler import ErrorClassifier
from core.state_manager import BookStateManager
from db.models import BookStatus, DoubanBook, ProcessingTask
from utils.logger import get_logger


class TaskStatus(Enum):
    """任务状态"""
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass(eq=False)
class ScheduledTask:
    """调度任务"""
    id: int
    book_id: int
    stage: str
    priority: int
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3
    next_run_time: datetime = field(default_factory=datetime.now)
    task_data: Optional[Dict[str, Any]] = None

    def __lt__(self, other):
        """用于优先队列排序"""
        # 先按next_run_time排序，再按优先级（高优先级在前），最后按创建时间
        if self.next_run_time != other.next_run_time:
            return self.next_run_time < other.next_run_time
        if self.priority != other.priority:
            return self.priority > other.priority  # 高优先级在前
        return self.created_at < other.created_at

    def __eq__(self, other):
        """相等性比较"""
        return isinstance(other, ScheduledTask) and self.id == other.id

    def __hash__(self):
        """哈希方法，使对象可以作为字典键"""
        return hash(self.id)


class TaskScheduler:
    """任务调度器"""

    def __init__(self,
                 state_manager: BookStateManager,
                 max_concurrent_tasks: int = 10):
        """
        初始化任务调度器
        
        Args:
            state_manager: 状态管理器
            max_concurrent_tasks: 最大并发任务数
        """
        self.state_manager = state_manager
        self.max_concurrent_tasks = max_concurrent_tasks
        self.logger = get_logger("task_scheduler")

        # 任务队列 - 使用优先队列
        self._task_queue: List[ScheduledTask] = []
        self._queue_lock = threading.Lock()

        # 活跃任务追踪
        self._active_tasks: Dict[int, ScheduledTask] = {}
        self._active_lock = threading.Lock()

        # 调度器状态
        self._running = False
        self._stop_event = threading.Event()
        self._scheduler_thread: Optional[threading.Thread] = None

        # 注册的任务处理器
        self._task_handlers: Dict[str, Callable] = {}

        # 统计信息
        self._stats = {
            'total_scheduled': 0,
            'total_completed': 0,
            'total_failed': 0,
            'total_retries': 0
        }

        # 清理相关
        self._last_cleanup = datetime.now()
        self._cleanup_interval = timedelta(hours=12)  # 每小时清理一次

    def register_handler(self, stage: str, handler: Callable[[ScheduledTask],
                                                             bool]):
        """
        注册任务处理器
        
        Args:
            stage: 处理阶段名称
            handler: 处理器函数，返回True表示成功
        """
        self._task_handlers[stage] = handler
        self.logger.info(f"注册任务处理器: {stage}")

    def schedule_task(self,
                      book_id: int,
                      stage: str,
                      priority: TaskPriority = TaskPriority.NORMAL,
                      delay_seconds: int = 0,
                      task_data: Optional[Dict[str, Any]] = None,
                      max_retries: int = 3) -> int:
        """
        调度任务
        
        Args:
            book_id: 书籍ID
            stage: 处理阶段
            priority: 任务优先级
            delay_seconds: 延迟秒数
            task_data: 任务数据
            max_retries: 最大重试次数
            
        Returns:
            int: 任务ID
        """
        try:
            # 检查书籍状态是否适合调度该阶段的任务
            if not self._can_schedule_for_stage(book_id, stage):
                raise ValueError(f"书籍ID {book_id} 的当前状态不适合调度 {stage} 阶段任务")

            # 计算运行时间
            run_time = datetime.now() + timedelta(seconds=delay_seconds)

            # 创建数据库记录
            with self.state_manager.get_session() as session:
                db_task = ProcessingTask(book_id=book_id,
                                         stage=stage,
                                         status=TaskStatus.QUEUED.value,
                                         priority=priority.value,
                                         max_retries=max_retries,
                                         task_data=task_data)

                session.add(db_task)
                session.flush()  # 获取ID但不提交
                task_id = db_task.id

            # 创建调度任务
            scheduled_task = ScheduledTask(id=task_id,
                                           book_id=book_id,
                                           stage=stage,
                                           priority=priority.value,
                                           created_at=datetime.now(),
                                           max_retries=max_retries,
                                           next_run_time=run_time,
                                           task_data=task_data)

            # 添加到队列
            with self._queue_lock:
                heapq.heappush(self._task_queue, scheduled_task)

            self._stats['total_scheduled'] += 1
            self.logger.info(
                f"调度任务: 书籍ID {book_id}, 阶段 {stage}, 优先级 {priority.name}, "
                f"任务ID {task_id}")

            return task_id

        except Exception as e:
            self.logger.error(f"调度任务失败: {str(e)}")
            raise

    def schedule_book_pipeline(self,
                               book_id: int,
                               start_stage: str = "data_collection"):
        """
        为书籍调度完整的pipeline
        
        Args:
            book_id: 书籍ID
            start_stage: 起始阶段
        """
        stages = ["data_collection", "search", "download", "upload"]
        start_index = stages.index(start_stage) if start_stage in stages else 0

        # 只调度当前阶段，后续阶段由state_manager在状态转换时调度
        self.schedule_task(book_id=book_id,
                           stage=start_stage,
                           priority=TaskPriority.NORMAL,
                           delay_seconds=0)

    def start(self):
        """启动调度器"""
        if self._running:
            self.logger.warning("调度器已经在运行中")
            return

        self._running = True
        self._stop_event.clear()

        # 启动调度器线程
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop,
                                                  daemon=True)
        self._scheduler_thread.start()

        self.logger.info("任务调度器已启动")

    def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self.logger.info("正在停止任务调度器...")
        self._running = False
        self._stop_event.set()

        # 等待调度器线程结束
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=10)

        # 取消所有排队的任务
        with self._queue_lock:
            for task in self._task_queue:
                self._update_task_status(task.id, TaskStatus.CANCELLED)
            self._task_queue.clear()

        # 清理活跃任务
        with self._active_lock:
            self._active_tasks.clear()

        self.logger.info("任务调度器已停止")

    def _scheduler_loop(self):
        """调度器主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                current_time = datetime.now()
                tasks_to_run = []

                # 获取可执行的任务
                with self._queue_lock:
                    while (self._task_queue and
                           self._task_queue[0].next_run_time <= current_time):
                        task = heapq.heappop(self._task_queue)
                        tasks_to_run.append(task)

                # 检查并发限制
                with self._active_lock:
                    available_slots = self.max_concurrent_tasks - len(
                        self._active_tasks)
                    if available_slots <= 0:
                        # 如果没有可用槽位，将任务重新放回队列
                        with self._queue_lock:
                            for task in tasks_to_run:
                                heapq.heappush(self._task_queue, task)
                        tasks_to_run.clear()

                # 执行任务
                for task in tasks_to_run[:available_slots]:
                    if self._stop_event.is_set():
                        break

                    self._execute_task(task)

                # 清理已完成的活跃任务
                self._cleanup_completed_tasks()

                # 定期清理数据库中的历史任务记录
                if current_time - self._last_cleanup >= self._cleanup_interval:
                    self._cleanup_database_tasks()
                    self._last_cleanup = current_time

                # 短暂休息
                time.sleep(1)

            except Exception as e:
                self.logger.error(f"调度器循环异常: {str(e)}")
                time.sleep(5)

    def _execute_task(self, task: ScheduledTask):
        """
        执行任务
        
        Args:
            task: 要执行的任务
        """
        try:
            # 检查任务处理器是否存在
            if task.stage not in self._task_handlers:
                self.logger.error(f"未找到处理器: {task.stage}")
                self._update_task_status(task.id,
                                         TaskStatus.FAILED,
                                         error_message=f"未找到处理器: {task.stage}")
                return

            # 在执行前再次检查书籍状态是否适合当前阶段
            if not self._can_schedule_for_stage(task.book_id, task.stage):
                self.logger.warning(
                    f"任务执行前状态检查失败，取消任务: ID {task.id}, 书籍ID {task.book_id}, 阶段 {task.stage}"
                )
                self._update_task_status(task.id,
                                         TaskStatus.CANCELLED,
                                         error_message=f"书籍状态不匹配阶段要求")
                return

            # 将任务添加到活跃任务列表
            with self._active_lock:
                self._active_tasks[task.id] = task

            # 更新任务状态为活跃
            self._update_task_status(task.id, TaskStatus.ACTIVE)

            self.logger.info(
                f"开始执行任务: ID {task.id}, 书籍ID {task.book_id}, 阶段 {task.stage}, "
                f"重试次数: {task.retry_count}/{task.max_retries}, 执行时间: {datetime.now().isoformat()}"
            )

            # 在线程中执行任务处理器
            def run_handler():
                try:
                    handler = self._task_handlers[task.stage]
                    success = handler(task)

                    if success:
                        self._update_task_status(task.id, TaskStatus.COMPLETED)
                        self._stats['total_completed'] += 1
                        self.logger.info(f"任务执行成功: ID {task.id}")
                    else:
                        self._handle_task_failure(task)

                except Exception as e:
                    import traceback
                    error_details = f"异常类型: {type(e).__name__}, 错误: {str(e)}"
                    self.logger.error(
                        f"任务执行异常 - ID: {task.id}, 书籍ID: {task.book_id}, 阶段: {task.stage}"
                    )
                    self.logger.error(f"异常详情: {error_details}")
                    self.logger.error(f"异常堆栈:\n{traceback.format_exc()}")
                    self._handle_task_failure(task, str(e), e)
                finally:
                    # 从活跃任务列表移除
                    with self._active_lock:
                        if task.id in self._active_tasks:
                            del self._active_tasks[task.id]

            # 启动处理线程
            handler_thread = threading.Thread(target=run_handler, daemon=True)
            handler_thread.start()

        except Exception as e:
            self.logger.error(f"执行任务失败: ID {task.id}, 错误: {str(e)}")
            self._update_task_status(task.id,
                                     TaskStatus.FAILED,
                                     error_message=str(e))

    def _handle_task_failure(self,
                             task: ScheduledTask,
                             error_message: str = "",
                             exception: Exception = None):
        """
        处理任务失败
        
        Args:
            task: 失败的任务
            error_message: 错误信息
            exception: 异常对象
        """
        # 检查是否为非重试性错误
        if exception:
            from core.pipeline import DownloadLimitExhaustedError
            
            # 特殊处理下载次数不足错误
            if isinstance(exception, DownloadLimitExhaustedError):
                self.logger.warning(
                    f"检测到下载次数不足错误，暂停下载相关任务: 任务ID {task.id}")
                self._update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    error_message=f"下载次数不足，已回退状态: {error_message}")
                self._stats['total_failed'] += 1
                
                # 暂停所有下载阶段的任务调度
                self._pause_download_tasks()
                
                self.logger.info(
                    f"下载次数不足，任务已暂停: ID {task.id}, 状态已回退到搜索完成"
                )
                return
            
            error_info = ErrorClassifier.classify_error(exception)
            if not error_info.retryable:
                self.logger.warning(
                    f"检测到非重试性错误: {error_info.error_type}, 任务ID {task.id}")
                self._update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    error_message=f"非重试性错误: {error_message}")
                self._stats['total_failed'] += 1
                self.logger.error(
                    f"任务最终失败 (非重试性错误): ID {task.id}, 错误类型: {error_info.error_type}"
                )
                return

        task.retry_count += 1
        self._stats['total_retries'] += 1

        if task.retry_count <= task.max_retries:
            # 检查是否为状态不匹配错误，使用更短的重试间隔
            is_status_mismatch = (("status_mismatch" in error_message)
                                  or ("状态" in error_message and
                                      ("SEARCH_QUEUED" in error_message
                                       or "DOWNLOAD_QUEUED" in error_message
                                       or "UPLOAD_QUEUED" in error_message)))

            if is_status_mismatch and task.retry_count <= 2:
                # 状态不匹配错误使用更短的重试间隔（5-15秒）
                delay_seconds = 5 + (task.retry_count * 5)
                self.logger.info(f"检测到状态不匹配错误，使用短间隔重试: {delay_seconds}秒")
            else:
                # 其他错误使用指数退避策略
                delay_seconds = min(300,
                                    30 * (2**(task.retry_count - 1)))  # 最大5分钟

            task.next_run_time = datetime.now() + timedelta(
                seconds=delay_seconds)

            # 重新加入队列
            with self._queue_lock:
                heapq.heappush(self._task_queue, task)

            self._update_task_status(
                task.id,
                TaskStatus.QUEUED,
                error_message=
                f"重试 {task.retry_count}/{task.max_retries}: {error_message}")

            self.logger.warning(
                f"任务失败，将在 {delay_seconds} 秒后重试: ID {task.id}, 书籍ID {task.book_id}, "
                f"阶段 {task.stage}, 重试次数 {task.retry_count}/{task.max_retries}")
            if error_message:
                self.logger.warning(f"任务 {task.id} 失败原因: {error_message}")
        else:
            # 超过最大重试次数
            self._update_task_status(task.id,
                                     TaskStatus.FAILED,
                                     error_message=error_message)
            self._stats['total_failed'] += 1
            self.logger.error(
                f"任务最终失败: ID {task.id}, 书籍ID {task.book_id}, 阶段 {task.stage}, "
                f"已达到最大重试次数 {task.max_retries}")
            if error_message:
                self.logger.error(f"最终失败原因: {error_message}")

    def _update_task_status(self,
                            task_id: int,
                            status: TaskStatus,
                            error_message: str = ""):
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态
            error_message: 错误信息
        """
        try:
            with self.state_manager.get_session() as session:
                task = session.get(ProcessingTask, task_id)
                if task:
                    task.status = status.value
                    task.updated_at = datetime.now()

                    if status == TaskStatus.ACTIVE:
                        task.started_at = datetime.now()
                    elif status in [
                            TaskStatus.COMPLETED, TaskStatus.FAILED,
                            TaskStatus.CANCELLED
                    ]:
                        task.completed_at = datetime.now()

                    if error_message:
                        task.error_message = error_message
        except Exception as e:
            self.logger.error(f"更新任务状态失败: {str(e)}")

    def _cleanup_completed_tasks(self):
        """清理内存中已完成的活跃任务"""
        with self._active_lock:
            completed_tasks = [
                task_id for task_id, task in self._active_tasks.items()
                if hasattr(task, '_completed') and task._completed
            ]

            for task_id in completed_tasks:
                del self._active_tasks[task_id]

    def _cleanup_database_tasks(self):
        """清理数据库中的历史任务记录"""
        try:
            # 清理超过2小时的已完成任务记录，失败任务保留24小时
            cutoff_time_completed = datetime.now() - timedelta(hours=2)
            cutoff_time_failed = datetime.now() - timedelta(hours=24)

            with self.state_manager.get_session() as session:
                # 清理已完成和已取消的任务
                deleted_completed = session.query(ProcessingTask).filter(
                    ProcessingTask.status.in_([
                        TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value
                    ]), ProcessingTask.updated_at
                    < cutoff_time_completed).delete()

                # 清理长时间失败的任务
                deleted_failed = session.query(ProcessingTask).filter(
                    ProcessingTask.status == TaskStatus.FAILED.value,
                    ProcessingTask.updated_at < cutoff_time_failed,
                    ProcessingTask.retry_count
                    >= ProcessingTask.max_retries).delete()

                total_deleted = deleted_completed + deleted_failed
                if total_deleted > 0:
                    self.logger.info(
                        f"清理了 {total_deleted} 个历史任务记录 (完成: {deleted_completed}, 失败: {deleted_failed})"
                    )

        except Exception as e:
            self.logger.error(f"清理数据库任务记录失败: {str(e)}")

    def cleanup_all_completed_tasks(self) -> int:
        """
        手动清理所有已完成和已取消的任务记录
        
        Returns:
            int: 清理的记录数量
        """
        try:
            with self.state_manager.get_session() as session:
                deleted_count = session.query(ProcessingTask).filter(
                    ProcessingTask.status.in_([
                        TaskStatus.COMPLETED.value, TaskStatus.CANCELLED.value
                    ])).delete()

                self.logger.info(f"手动清理了 {deleted_count} 个已完成的任务记录")
                return deleted_count

        except Exception as e:
            self.logger.error(f"手动清理任务记录失败: {str(e)}")
            return 0

    def get_status(self) -> Dict[str, Any]:
        """
        获取调度器状态
        
        Returns:
            Dict[str, Any]: 状态信息
        """
        with self._queue_lock:
            queue_size = len(self._task_queue)

        with self._active_lock:
            active_count = len(self._active_tasks)

        return {
            'running': self._running,
            'queue_size': queue_size,
            'active_tasks': active_count,
            'max_concurrent_tasks': self.max_concurrent_tasks,
            'registered_handlers': list(self._task_handlers.keys()),
            'statistics': self._stats.copy()
        }

    def cancel_task(self, task_id: int) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消
        """
        try:
            # 尝试从队列中移除
            with self._queue_lock:
                self._task_queue = [
                    t for t in self._task_queue if t.id != task_id
                ]
                heapq.heapify(self._task_queue)

            # 更新数据库状态
            self._update_task_status(task_id, TaskStatus.CANCELLED)

            self.logger.info(f"任务已取消: ID {task_id}")
            return True

        except Exception as e:
            self.logger.error(f"取消任务失败: {str(e)}")
            return False

    def get_pending_tasks(self,
                          stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取待处理任务列表
        
        Args:
            stage: 过滤的阶段名称（可选）
            
        Returns:
            List[Dict[str, Any]]: 待处理任务列表
        """
        with self._queue_lock:
            tasks = []
            for task in self._task_queue:
                if stage is None or task.stage == stage:
                    tasks.append({
                        'id':
                        task.id,
                        'book_id':
                        task.book_id,
                        'stage':
                        task.stage,
                        'priority':
                        task.priority,
                        'retry_count':
                        task.retry_count,
                        'next_run_time':
                        task.next_run_time.isoformat(),
                        'created_at':
                        task.created_at.isoformat()
                    })

            # 按下次运行时间排序
            tasks.sort(key=lambda x: x['next_run_time'])
            return tasks

    def _can_schedule_for_stage(self, book_id: int, stage: str) -> bool:
        """
        检查书籍状态是否适合调度该阶段的任务
        
        Args:
            book_id: 书籍ID
            stage: 处理阶段名称
            
        Returns:
            bool: 是否可以调度
        """
        try:
            with self.state_manager.get_session() as session:
                book = session.get(DoubanBook, book_id)
                if not book:
                    self.logger.warning(f"书籍不存在: ID {book_id}")
                    return False

                current_status = book.status

                # 定义各阶段可以接受的状态（包括active状态，因为处理器可能需要处理正在进行的任务）
                stage_acceptable_statuses = {
                    'data_collection':
                    {BookStatus.NEW, BookStatus.DETAIL_FETCHING},
                    'search': {
                        BookStatus.DETAIL_COMPLETE, BookStatus.SEARCH_QUEUED,
                        BookStatus.SEARCH_ACTIVE
                    },
                    'download':
                    {BookStatus.DOWNLOAD_QUEUED, BookStatus.DOWNLOAD_ACTIVE},
                    'upload': {
                        BookStatus.DOWNLOAD_COMPLETE, BookStatus.UPLOAD_QUEUED,
                        BookStatus.UPLOAD_ACTIVE
                    }
                }

                acceptable_statuses = stage_acceptable_statuses.get(
                    stage, set())
                is_acceptable = current_status in acceptable_statuses

                self.logger.debug(
                    f"检查调度条件: 书籍ID {book_id}, 当前状态: {current_status.value}, "
                    f"阶段: {stage}, 可接受状态: {[s.value for s in acceptable_statuses]}, "
                    f"可调度: {is_acceptable}")

                if not is_acceptable:
                    self.logger.warning(
                        f"书籍状态不适合调度 {stage} 阶段: "
                        f"书籍ID {book_id}, 当前状态 {current_status.value}")

                return is_acceptable

        except Exception as e:
            self.logger.error(
                f"检查调度条件失败: 书籍ID {book_id}, 阶段 {stage}, 错误: {str(e)}")
            return False

    def _pause_download_tasks(self):
        """
        暂停所有下载阶段的任务调度
        
        将队列中所有下载阶段的任务状态设置为取消，避免继续消耗下载次数
        """
        try:
            paused_count = 0
            
            with self._queue_lock:
                # 找出所有下载阶段的任务
                download_tasks = [task for task in self._task_queue if task.stage == 'download']
                
                # 从队列中移除这些任务
                self._task_queue = [task for task in self._task_queue if task.stage != 'download']
                heapq.heapify(self._task_queue)
                
                # 将这些任务标记为已取消
                for task in download_tasks:
                    self._update_task_status(
                        task.id, 
                        TaskStatus.CANCELLED,
                        error_message="下载次数不足，任务已暂停"
                    )
                    paused_count += 1
                    
            self.logger.info(f"已暂停 {paused_count} 个下载阶段任务")
                    
        except Exception as e:
            self.logger.error(f"暂停下载任务失败: {str(e)}")

    def resume_download_tasks_when_limit_restored(self):
        """
        当下载次数恢复时，恢复下载任务调度
        
        重新为状态为SEARCH_COMPLETE的书籍创建下载任务
        """
        try:
            resumed_count = 0
            
            with self.state_manager.get_session() as session:
                # 查找所有SEARCH_COMPLETE状态的书籍
                books_ready_for_download = session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.SEARCH_COMPLETE
                ).all()
                
                self.logger.info(f"找到 {len(books_ready_for_download)} 本准备下载的书籍")
                
                for book in books_ready_for_download:
                    # 为这些书籍创建下载任务
                    if self.schedule_task(book.id, 'download', TaskPriority.NORMAL):
                        resumed_count += 1
                        
            self.logger.info(f"已恢复 {resumed_count} 个下载任务")
            return resumed_count
            
        except Exception as e:
            self.logger.error(f"恢复下载任务失败: {str(e)}")
            return 0
