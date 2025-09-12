# -*- coding: utf-8 -*-
"""
状态管理器

统一管理书籍状态转换和验证。
"""

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from db.models import BookStatus, BookStatusHistory, DoubanBook
from utils.logger import get_logger


class BookStateManager:
    """书籍状态管理器"""

    # 定义允许的状态转换路径
    VALID_TRANSITIONS: Dict[BookStatus, Set[BookStatus]] = {
        # 数据收集阶段
        BookStatus.NEW: {
            BookStatus.DETAIL_FETCHING, BookStatus.DETAIL_COMPLETE, BookStatus.SKIPPED_EXISTS,
            BookStatus.FAILED_PERMANENT
        },
        BookStatus.DETAIL_FETCHING: {
            BookStatus.DETAIL_COMPLETE,
            BookStatus.FAILED_PERMANENT,
            BookStatus.NEW  # 重试时回退
        },
        BookStatus.DETAIL_COMPLETE: {
            BookStatus.SEARCH_QUEUED, BookStatus.SKIPPED_EXISTS,
            BookStatus.FAILED_PERMANENT
        },

        # 搜索阶段
        BookStatus.SEARCH_QUEUED: {
            BookStatus.SEARCH_ACTIVE, BookStatus.SKIPPED_EXISTS,
            BookStatus.FAILED_PERMANENT
        },
        BookStatus.SEARCH_ACTIVE: {
            BookStatus.SEARCH_COMPLETE,
            BookStatus.SEARCH_NO_RESULTS,
            BookStatus.SKIPPED_EXISTS,  # Calibre中已存在
            BookStatus.FAILED_PERMANENT,
            BookStatus.SEARCH_QUEUED  # 重试时回退
        },
        BookStatus.SEARCH_COMPLETE:
        {BookStatus.DOWNLOAD_QUEUED, BookStatus.FAILED_PERMANENT},
        BookStatus.SEARCH_NO_RESULTS: {
            BookStatus.SEARCH_QUEUED,  # 重试
            BookStatus.FAILED_PERMANENT
        },

        # 下载阶段
        BookStatus.DOWNLOAD_QUEUED:
        {BookStatus.DOWNLOAD_ACTIVE, BookStatus.FAILED_PERMANENT},
        BookStatus.DOWNLOAD_ACTIVE: {
            BookStatus.DOWNLOAD_COMPLETE,
            BookStatus.DOWNLOAD_FAILED,
            BookStatus.FAILED_PERMANENT,
            BookStatus.DOWNLOAD_QUEUED  # 重试时回退
        },
        BookStatus.DOWNLOAD_COMPLETE: {
            BookStatus.UPLOAD_QUEUED,
            BookStatus.COMPLETED,  # 如果不需要上传
            BookStatus.FAILED_PERMANENT
        },
        BookStatus.DOWNLOAD_FAILED: {
            BookStatus.DOWNLOAD_QUEUED,  # 重试
            BookStatus.FAILED_PERMANENT
        },

        # 上传阶段
        BookStatus.UPLOAD_QUEUED:
        {BookStatus.UPLOAD_ACTIVE, BookStatus.FAILED_PERMANENT},
        BookStatus.UPLOAD_ACTIVE: {
            BookStatus.UPLOAD_COMPLETE,
            BookStatus.UPLOAD_FAILED,
            BookStatus.FAILED_PERMANENT,
            BookStatus.UPLOAD_QUEUED  # 重试时回退
        },
        BookStatus.UPLOAD_COMPLETE: {BookStatus.COMPLETED},
        BookStatus.UPLOAD_FAILED: {
            BookStatus.UPLOAD_QUEUED,  # 重试
            BookStatus.FAILED_PERMANENT
        },

        # 终态 - 通常不允许转换，但可能需要重新处理
        BookStatus.COMPLETED: set(),  # 完成状态不允许转换
        BookStatus.SKIPPED_EXISTS: set(),  # 跳过状态不允许转换
        BookStatus.FAILED_PERMANENT: {
            # 允许从永久失败状态重新开始
            BookStatus.NEW,
            BookStatus.SEARCH_QUEUED,
            BookStatus.DOWNLOAD_QUEUED,
            BookStatus.UPLOAD_QUEUED
        }
    }

    # 定义各阶段的状态
    STAGE_STATES = {
        'data_collection': {
            BookStatus.NEW, BookStatus.DETAIL_FETCHING,
            BookStatus.DETAIL_COMPLETE
        },
        'search': {
            BookStatus.SEARCH_QUEUED, BookStatus.SEARCH_ACTIVE,
            BookStatus.SEARCH_COMPLETE, BookStatus.SEARCH_NO_RESULTS
        },
        'download': {
            BookStatus.DOWNLOAD_QUEUED, BookStatus.DOWNLOAD_ACTIVE,
            BookStatus.DOWNLOAD_COMPLETE, BookStatus.DOWNLOAD_FAILED
        },
        'upload': {
            BookStatus.UPLOAD_QUEUED, BookStatus.UPLOAD_ACTIVE,
            BookStatus.UPLOAD_COMPLETE, BookStatus.UPLOAD_FAILED
        },
        'final': {
            BookStatus.COMPLETED, BookStatus.SKIPPED_EXISTS,
            BookStatus.FAILED_PERMANENT
        }
    }

    def __init__(self,
                 db_session: Session = None,
                 session_factory: Callable = None,
                 lark_service=None,
                 task_scheduler=None):
        """
        初始化状态管理器
        
        Args:
            db_session: 数据库会话（可选，用于向后兼容）
            session_factory: 会话工厂函数，用于创建新会话
            lark_service: 飞书通知服务（可选）
            task_scheduler: 任务调度器（可选）
        """
        self.db_session = db_session
        self.session_factory = session_factory
        self.lark_service = lark_service
        self.task_scheduler = task_scheduler
        self.logger = get_logger("state_manager")

    @contextmanager
    def get_session(self):
        """获取数据库会话的上下文管理器"""
        if self.session_factory:
            # 创建新的session并管理其生命周期
            session = self.session_factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        elif self.db_session:
            # 使用现有会话
            yield self.db_session
        else:
            raise ValueError(
                "No session available: neither session_factory nor db_session provided"
            )

    def is_valid_transition(self, from_status: BookStatus,
                            to_status: BookStatus) -> bool:
        """
        检查状态转换是否有效
        
        Args:
            from_status: 当前状态
            to_status: 目标状态
            
        Returns:
            bool: 转换是否有效
        """
        if from_status not in self.VALID_TRANSITIONS:
            return False

        return to_status in self.VALID_TRANSITIONS[from_status]

    def get_stage_for_status(self, status: BookStatus) -> Optional[str]:
        """
        获取状态所属的阶段
        
        Args:
            status: 书籍状态
            
        Returns:
            Optional[str]: 阶段名称，如果找不到则返回None
        """
        for stage, statuses in self.STAGE_STATES.items():
            if status in statuses:
                return stage
        return None

    def get_next_stage_status(
            self, current_status: BookStatus) -> Optional[BookStatus]:
        """
        获取下一阶段的起始状态
        
        Args:
            current_status: 当前状态
            
        Returns:
            Optional[BookStatus]: 下一阶段的起始状态
        """
        stage_transitions = {
            BookStatus.DETAIL_COMPLETE: BookStatus.SEARCH_QUEUED,
            BookStatus.SEARCH_COMPLETE: BookStatus.DOWNLOAD_QUEUED,
            BookStatus.DOWNLOAD_COMPLETE: BookStatus.UPLOAD_QUEUED,
            BookStatus.UPLOAD_COMPLETE: BookStatus.COMPLETED
        }

        return stage_transitions.get(current_status)

    def transition_status(self,
                          book_id: int,
                          to_status: BookStatus,
                          change_reason: str,
                          error_message: Optional[str] = None,
                          processing_time: Optional[float] = None,
                          sync_task_id: Optional[int] = None,
                          retry_count: int = 0) -> bool:
        """
        执行状态转换
        
        Args:
            book_id: 书籍ID
            to_status: 目标状态
            change_reason: 状态变更原因
            error_message: 错误信息（可选）
            processing_time: 处理耗时（可选）
            sync_task_id: 同步任务ID（可选）
            retry_count: 重试次数
            
        Returns:
            bool: 转换是否成功
        """
        try:
            with self.get_session() as session:
                # 获取书籍当前状态
                book = session.get(DoubanBook, book_id)
                if not book:
                    self.logger.error(f"书籍不存在: ID {book_id}")
                    return False

                current_status = book.status

                self.logger.info(
                    f"状态转换: {book_id} {current_status.value} -> {to_status.value} {change_reason}"
                )

                # 验证状态转换
                if not self.is_valid_transition(current_status, to_status):
                    self.logger.error(
                        f"无效的状态转换: {current_status.value} -> {to_status.value} "
                        f"(书籍ID: {book_id})")
                    return False

                # 更新书籍状态
                old_status = book.status
                book.status = to_status
                book.updated_at = datetime.now()

                if error_message:
                    book.error_message = error_message

                # 确保对象被标记为dirty，强制session跟踪此对象
                session.add(book)

                # 创建状态历史记录
                history = BookStatusHistory(book_id=book_id,
                                            old_status=old_status,
                                            new_status=to_status,
                                            change_reason=change_reason,
                                            error_message=error_message,
                                            processing_time=processing_time,
                                            retry_count=retry_count)

                session.add(history)
                # 注意：commit由上下文管理器处理

                self.logger.info(
                    f"状态转换成功: 书籍ID {book_id}, {old_status.value} -> {to_status.value}, "
                    f"事务即将提交, 时间: {datetime.now().isoformat()}")

                # 发送飞书通知
                self._send_status_change_notification(book, old_status,
                                                      to_status, change_reason,
                                                      processing_time)

            # 事务提交完成后，再调度下一个阶段的任务
            # 这确保状态更新已经完全提交到数据库
            # 但要避免在QUEUED状态转换中再次调度，防止递归调用
            if not to_status.value.endswith('_queued'):
                self.logger.debug(
                    f"事务已提交，开始检查是否需要调度下一阶段: 书籍ID {book_id}, 当前状态: {to_status.value}"
                )
                self._schedule_next_stage_if_needed(book_id, to_status)
            else:
                self.logger.debug(
                    f"跳过调度检查，因为当前状态是queued状态: 书籍ID {book_id}, 状态: {to_status.value}"
                )

            return True

        except Exception as e:
            self.logger.error(f"状态转换失败: {str(e)}")
            return False

    def transition_status_in_session(self,
                                   book_id: int,
                                   to_status: BookStatus,
                                   change_reason: str,
                                   session: Session,
                                   processing_time: Optional[float] = None,
                                   retry_count: int = 0,
                                   error_message: Optional[str] = None) -> bool:
        """
        在指定会话中执行状态转换
        
        Args:
            book_id: 书籍ID
            to_status: 目标状态
            change_reason: 状态变更原因
            session: 数据库会话
            processing_time: 处理耗时（可选）
            retry_count: 重试次数
            error_message: 错误信息（可选）
            
        Returns:
            bool: 转换是否成功
        """
        try:
            # 获取书籍当前状态
            book = session.get(DoubanBook, book_id)
            if not book:
                self.logger.error(f"书籍不存在: ID {book_id}")
                return False

            current_status = book.status

            self.logger.info(
                f"状态转换: {book_id} {current_status.value} -> {to_status.value} {change_reason}"
            )

            # 验证状态转换
            if not self.is_valid_transition(current_status, to_status):
                self.logger.error(
                    f"无效的状态转换: {current_status.value} -> {to_status.value} "
                    f"(书籍ID: {book_id})")
                return False

            # 更新书籍状态
            old_status = book.status
            book.status = to_status
            book.updated_at = datetime.now()

            if error_message:
                book.error_message = error_message

            # 确保对象被标记为dirty，强制session跟踪此对象
            session.add(book)

            # 创建状态历史记录
            history = BookStatusHistory(book_id=book_id,
                                        old_status=old_status,
                                        new_status=to_status,
                                        change_reason=change_reason,
                                        error_message=error_message,
                                        processing_time=processing_time,
                                        retry_count=retry_count)

            session.add(history)

            self.logger.info(
                f"状态转换成功: 书籍ID {book_id}, {old_status.value} -> {to_status.value}, "
                f"事务将随外部会话提交, 时间: {datetime.now().isoformat()}")

            # 发送飞书通知
            self._send_status_change_notification(book, old_status,
                                                  to_status, change_reason,
                                                  processing_time)

            return True

        except Exception as e:
            self.logger.error(f"会话内状态转换失败: {str(e)}")
            return False

    def transition_status_with_next_task_in_session(self,
                                                   book_id: int,
                                                   to_status: BookStatus,
                                                   change_reason: str,
                                                   next_stage: str,
                                                   processing_time: Optional[float] = None,
                                                   retry_count: int = 0,
                                                   session: Session = None) -> bool:
        """
        在指定会话中执行状态转换并调度下一阶段任务
        
        Args:
            book_id: 书籍ID
            to_status: 目标状态
            change_reason: 状态变更原因
            next_stage: 下一阶段名称
            processing_time: 处理耗时（可选）
            retry_count: 重试次数
            session: 数据库会话
            
        Returns:
            bool: 转换是否成功
        """
        # 先执行状态转换
        if not self.transition_status_in_session(book_id, to_status, change_reason, 
                                                session, processing_time, retry_count):
            return False
        
        # 调度下一阶段任务
        from core.task_scheduler import TaskScheduler
        if hasattr(self, 'task_scheduler'):
            # 直接调度任务
            task_id = self.task_scheduler.schedule_task(book_id, next_stage)
            self.logger.info(f"自动调度下一阶段任务: 书籍ID {book_id}, 阶段 {next_stage}, 任务ID {task_id}, "
                           f"状态已转换至: {to_status.value}, 调度时间: {datetime.now().isoformat()}")
        else:
            self.logger.warning(f"无法调度下一阶段任务: 缺少task_scheduler引用 (书籍ID {book_id}, 阶段 {next_stage})")
        
        return True

    def get_books_by_status(self,
                            status: BookStatus,
                            limit: Optional[int] = None) -> List[DoubanBook]:
        """
        根据状态获取书籍列表
        
        Args:
            status: 书籍状态
            limit: 限制数量
            
        Returns:
            List[DoubanBook]: 书籍列表
        """
        try:
            with self.get_session() as session:
                query = session.query(DoubanBook).filter(
                    DoubanBook.status == status)

                if limit:
                    query = query.limit(limit)

                return query.all()
        except Exception as e:
            self.logger.error(f"获取书籍列表失败: {str(e)}")
            return []

    def get_books_by_stage(self,
                           stage: str,
                           limit: Optional[int] = None) -> List[DoubanBook]:
        """
        根据阶段获取书籍列表
        
        Args:
            stage: 阶段名称
            limit: 限制数量
            
        Returns:
            List[DoubanBook]: 书籍列表
        """
        if stage not in self.STAGE_STATES:
            return []

        try:
            with self.get_session() as session:
                stage_statuses = list(self.STAGE_STATES[stage])
                query = session.query(DoubanBook).filter(
                    DoubanBook.status.in_(stage_statuses))

                if limit:
                    query = query.limit(limit)

                return query.all()
        except Exception as e:
            self.logger.error(f"获取阶段书籍列表失败: {str(e)}")
            return []

    def get_status_statistics(self) -> Dict[str, int]:
        """
        获取状态统计信息
        
        Returns:
            Dict[str, int]: 各状态的书籍数量
        """
        try:
            from sqlalchemy import func

            with self.get_session() as session:
                stats = {}
                results = session.query(DoubanBook.status,
                                        func.count(DoubanBook.id)).group_by(
                                            DoubanBook.status).all()

                for status, count in results:
                    stats[status.value] = count

                return stats

        except Exception as e:
            self.logger.error(f"获取状态统计失败: {str(e)}")
            return {}

    def get_recent_status_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的状态变更记录
        
        Args:
            limit: 返回记录数量限制
            
        Returns:
            List[Dict]: 状态历史记录字典列表
        """
        try:
            with self.get_session() as session:
                records = session.query(BookStatusHistory).order_by(
                    BookStatusHistory.created_at.desc()).limit(limit).all()

                # 转换为字典以避免DetachedInstanceError
                result = []
                for record in records:
                    result.append({
                        'book_id': record.book_id,
                        'old_status': record.old_status,
                        'new_status': record.new_status,
                        'change_reason': record.change_reason,
                        'created_at': record.created_at,
                        'error_message': record.error_message,
                        'processing_time': record.processing_time,
                        'retry_count': record.retry_count
                    })

                return result
        except Exception as e:
            self.logger.error(f"获取状态日志失败: {str(e)}")
            return []

    def reset_stuck_statuses(self, timeout_minutes: int = 30) -> int:
        """
        重置卡住的状态（比如长时间处于active状态的任务）
        
        Args:
            timeout_minutes: 超时时间（分钟）
            
        Returns:
            int: 重置的记录数量
        """
        try:
            timeout_time = datetime.now() - timedelta(minutes=timeout_minutes)

            # 查找长时间处于active状态的书籍
            stuck_statuses = [
                BookStatus.DETAIL_FETCHING, BookStatus.SEARCH_ACTIVE,
                BookStatus.DOWNLOAD_ACTIVE, BookStatus.UPLOAD_ACTIVE
            ]

            with self.get_session() as session:
                stuck_books = session.query(DoubanBook).filter(
                    DoubanBook.status.in_(stuck_statuses),
                    DoubanBook.updated_at < timeout_time).all()

                # 重置到对应的queued状态
                reset_mapping = {
                    BookStatus.DETAIL_FETCHING: BookStatus.NEW,
                    BookStatus.SEARCH_ACTIVE: BookStatus.SEARCH_QUEUED,
                    BookStatus.DOWNLOAD_ACTIVE: BookStatus.DOWNLOAD_QUEUED,
                    BookStatus.UPLOAD_ACTIVE: BookStatus.UPLOAD_QUEUED
                }

                # 收集需要重置的书籍ID，避免会话绑定问题
                book_ids_to_reset = []
                for book in stuck_books:
                    new_status = reset_mapping.get(book.status)
                    if new_status:
                        book_ids_to_reset.append((book.id, new_status))

            # 在会话外进行状态转换
            reset_count = 0
            for book_id, new_status in book_ids_to_reset:
                if self.transition_status(book_id, new_status,
                                          f"重置超时状态，超时时间: {timeout_minutes}分钟"):
                    reset_count += 1

                self.logger.info(f"重置了 {reset_count} 个卡住的状态")
                return reset_count

        except Exception as e:
            self.logger.error(f"重置卡住的状态失败: {str(e)}")
            return 0

    def recover_from_crash(self) -> int:
        """
        恢复程序崩溃后的状态，将所有ACTIVE状态重置为QUEUED状态
        
        主要用于程序启动时检查是否有未完成的任务需要恢复
        
        Returns:
            int: 恢复的记录数量
        """
        try:
            # 需要恢复的状态映射
            recovery_mapping = {
                BookStatus.DETAIL_FETCHING: BookStatus.NEW,
                BookStatus.SEARCH_ACTIVE: BookStatus.SEARCH_QUEUED,
                BookStatus.DOWNLOAD_ACTIVE: BookStatus.DOWNLOAD_QUEUED,
                BookStatus.UPLOAD_ACTIVE: BookStatus.UPLOAD_QUEUED
            }

            active_statuses = list(recovery_mapping.keys())
            
            with self.get_session() as session:
                # 查找所有处于ACTIVE状态的书籍
                active_books = session.query(DoubanBook).filter(
                    DoubanBook.status.in_(active_statuses)
                ).all()

                # 收集需要恢复的书籍ID
                book_ids_to_recover = []
                for book in active_books:
                    new_status = recovery_mapping.get(book.status)
                    if new_status:
                        book_ids_to_recover.append((book.id, book.status, new_status))

            # 执行状态恢复
            recovered_count = 0
            for book_id, old_status, new_status in book_ids_to_recover:
                if self.transition_status(
                    book_id, 
                    new_status,
                    f"程序崩溃恢复：{old_status} -> {new_status}"
                ):
                    recovered_count += 1

            if recovered_count > 0:
                self.logger.info(f"程序启动时恢复了 {recovered_count} 个崩溃状态")
            else:
                self.logger.debug("程序启动时没有发现需要恢复的崩溃状态")
            
            return recovered_count

        except Exception as e:
            self.logger.error(f"程序崩溃恢复失败: {str(e)}")
            return 0

    def cleanup_mismatched_tasks(self) -> int:
        """
        清理任务和书籍状态不匹配的任务
        
        Returns:
            int: 清理的任务数量
        """
        try:
            # 定义每个阶段需要的书籍状态
            stage_status_requirements = {
                'data_collection': [BookStatus.NEW],
                'search': [BookStatus.DETAIL_COMPLETE, BookStatus.SEARCH_QUEUED, BookStatus.SEARCH_ACTIVE],
                'download': [BookStatus.SEARCH_COMPLETE, BookStatus.DOWNLOAD_QUEUED, BookStatus.DOWNLOAD_ACTIVE],
                'upload': [BookStatus.DOWNLOAD_COMPLETE, BookStatus.UPLOAD_QUEUED, BookStatus.UPLOAD_ACTIVE]
            }
            
            from core.task_scheduler import TaskStatus
            from db.models import ProcessingTask
            
            with self.get_session() as session:
                # 查找所有未完成的任务
                pending_tasks = session.query(ProcessingTask).filter(
                    ProcessingTask.status.in_([
                        TaskStatus.QUEUED.value,
                        TaskStatus.ACTIVE.value
                    ])
                ).all()
                
                # 收集需要清理的任务ID
                tasks_to_cleanup = []
                
                for task in pending_tasks:
                    # 获取对应的书籍
                    book = session.get(DoubanBook, task.book_id)
                    
                    should_cleanup = False
                    
                    if not book:
                        # 书籍不存在，清理任务
                        should_cleanup = True
                        self.logger.info(f"发现无效任务（书籍不存在）: 任务 {task.id}, 书籍ID {task.book_id}")
                    else:
                        # 检查状态匹配
                        required_statuses = stage_status_requirements.get(task.stage, [])
                        if book.status not in required_statuses:
                            should_cleanup = True
                            self.logger.info(
                                f"发现状态不匹配任务: 任务 {task.id}, 书籍 {book.title} (ID: {task.book_id}), "
                                f"任务阶段: {task.stage}, 书籍状态: {book.status}, "
                                f"需要状态: {[s.value for s in required_statuses]}"
                            )
                        
                        # 特殊处理：终态书籍不应该有未完成的任务
                        final_statuses = [
                            BookStatus.COMPLETED, 
                            BookStatus.SKIPPED_EXISTS, 
                            BookStatus.FAILED_PERMANENT,
                            BookStatus.UPLOAD_COMPLETE,
                            BookStatus.SEARCH_NO_RESULTS
                        ]
                        if book.status in final_statuses:
                            should_cleanup = True
                            self.logger.info(f"发现终态书籍的过时任务: 任务 {task.id}, 书籍 {book.title}, 状态: {book.status}")
                    
                    if should_cleanup:
                        tasks_to_cleanup.append(task.id)
                
                # 执行清理
                if tasks_to_cleanup:
                    cleaned_count = session.query(ProcessingTask).filter(
                        ProcessingTask.id.in_(tasks_to_cleanup)
                    ).update({
                        ProcessingTask.status: TaskStatus.CANCELLED.value,
                        ProcessingTask.completed_at: datetime.now()
                    }, synchronize_session=False)
                    
                    self.logger.info(f"清理了 {cleaned_count} 个状态不匹配的任务")
                    return cleaned_count
                else:
                    self.logger.debug("没有发现需要清理的状态不匹配任务")
                    return 0
                    
        except Exception as e:
            self.logger.error(f"清理状态不匹配任务失败: {str(e)}")
            return 0

    def can_retry(self, book_id: int, max_retries: int = 3) -> bool:
        """
        检查是否可以重试
        
        Args:
            book_id: 书籍ID
            max_retries: 最大重试次数
            
        Returns:
            bool: 是否可以重试
        """
        try:
            with self.get_session() as session:
                # 获取最近的状态历史记录数量
                recent_failures = session.query(BookStatusHistory).filter(
                    BookStatusHistory.book_id == book_id,
                    BookStatusHistory.error_message.isnot(None)).order_by(
                        BookStatusHistory.created_at.desc()).limit(
                            max_retries + 1).count()

                return recent_failures <= max_retries

        except Exception as e:
            self.logger.error(f"检查重试次数失败: {str(e)}")
            return False

    def _send_status_change_notification(
            self,
            book: DoubanBook,
            old_status: BookStatus,
            new_status: BookStatus,
            change_reason: str,
            processing_time: Optional[float] = None):
        """
        发送状态转换的飞书通知
        
        Args:
            book: 书籍对象
            old_status: 旧状态
            new_status: 新状态
            change_reason: 变更原因
            processing_time: 处理时间
        """
        if not self.lark_service:
            return

        # 获取状态的中文描述
        status_descriptions = {
            BookStatus.NEW:
            "新发现",
            # BookStatus.DETAIL_FETCHING:
            # "获取详情中",
            BookStatus.DETAIL_COMPLETE:
            "详情获取完成",
            # BookStatus.SEARCH_QUEUED: "排队搜索",
            # BookStatus.SEARCH_ACTIVE: "搜索中",
            BookStatus.SEARCH_COMPLETE:
            "搜索完成",
            BookStatus.SEARCH_NO_RESULTS:
            "搜索无结果",
            # BookStatus.DOWNLOAD_QUEUED:
            # "排队下载",
            # BookStatus.DOWNLOAD_ACTIVE:
            # "下载中",
            BookStatus.DOWNLOAD_COMPLETE:
            "下载完成",
            BookStatus.DOWNLOAD_FAILED:
            "下载失败",
            # BookStatus.UPLOAD_QUEUED:
            # "排队上传",
            # BookStatus.UPLOAD_ACTIVE:
            # "上传中",
            BookStatus.UPLOAD_COMPLETE:
            "上传完成",
            BookStatus.UPLOAD_FAILED:
            "上传失败",
            BookStatus.COMPLETED:
            "✅ 完成",
            BookStatus.SKIPPED_EXISTS:
            "跳过(已存在)",
            BookStatus.FAILED_PERMANENT:
            "❌ 永久失败"
        }

        # 不发送通知的状态
        if new_status not in status_descriptions:
            return

        try:

            old_desc = status_descriptions.get(old_status, old_status.value)
            new_desc = status_descriptions.get(new_status, new_status.value)

            # 构建消息内容
            message_parts = [
                f"📚 **{book.title}**", f"✍️ 作者: {book.author or '未知'}",
                f"🔄 状态: {old_desc} → {new_desc}", f"💡 原因: {change_reason}"
            ]

            if processing_time:
                message_parts.append(f"耗时: {processing_time:.2f}秒")

            if book.isbn:
                message_parts.append(f"ISBN: {book.isbn}")

            message_parts.append(f"书籍ID: {book.id}")

            message = "\n".join(message_parts)

            # 发送通知
            self.lark_service.bot.send_card(message)

        except Exception as e:
            self.logger.warning(f"发送飞书通知失败: {str(e)}")

    def _schedule_next_stage_if_needed(self, book_id: int,
                                       current_status: BookStatus):
        """
        检查是否需要调度下一个阶段的任务
        
        Args:
            book_id: 书籍ID
            current_status: 当前状态
        """
        if not self.task_scheduler:
            return

        # 定义状态到下一个阶段的映射
        next_stage_mapping = {
            BookStatus.DETAIL_COMPLETE: "search",
            BookStatus.SEARCH_COMPLETE: "download",
            BookStatus.DOWNLOAD_COMPLETE: "upload",
        }

        if current_status in next_stage_mapping:
            next_stage = next_stage_mapping[current_status]
            try:
                # 首先转换到下一阶段的queued状态
                next_queued_status = None
                if next_stage == "search":
                    next_queued_status = BookStatus.SEARCH_QUEUED
                elif next_stage == "download":
                    next_queued_status = BookStatus.DOWNLOAD_QUEUED
                elif next_stage == "upload":
                    next_queued_status = BookStatus.UPLOAD_QUEUED

                if next_queued_status:
                    # 直接在数据库中更新状态，避免递归调用transition_status
                    try:
                        with self.get_session() as session:
                            book = session.get(DoubanBook, book_id)
                            if book and book.status == current_status:
                                old_status = book.status
                                book.status = next_queued_status
                                book.updated_at = datetime.now()
                                
                                # 创建状态历史记录
                                history = BookStatusHistory(
                                    book_id=book_id,
                                    old_status=old_status,
                                    new_status=next_queued_status,
                                    change_reason=f"准备进入{next_stage}阶段"
                                )
                                session.add(history)
                                
                                self.logger.info(
                                    f"状态转换: {book_id} {old_status.value} -> {next_queued_status.value} 准备进入{next_stage}阶段"
                                )
                            else:
                                self.logger.warning(f"书籍状态已变更，跳过queued状态转换: 书籍ID {book_id}")
                    except Exception as status_error:
                        self.logger.error(f"queued状态转换失败: {str(status_error)}")
                        return

                # 导入TaskPriority避免循环导入
                from core.task_scheduler import TaskPriority
                try:
                    task_id = self.task_scheduler.schedule_task(
                        book_id=book_id,
                        stage=next_stage,
                        priority=TaskPriority.NORMAL,
                        delay_seconds=3  # 给状态更新充足时间完全提交到数据库
                    )
                    self.logger.info(
                        f"自动调度下一阶段任务: 书籍ID {book_id}, 阶段 {next_stage}, 任务ID {task_id}, "
                        f"状态已转换至: {next_queued_status.value if next_queued_status else '未转换'}, "
                        f"调度时间: {datetime.now().isoformat()}")
                except ValueError as ve:
                    # 状态不匹配的调度错误，记录警告但不阻止程序继续
                    self.logger.warning(f"自动调度任务被跳过: {str(ve)}")
                except Exception as task_error:
                    # 其他调度错误
                    self.logger.error(f"自动调度下一阶段任务失败: {str(task_error)}")
            except Exception as e:
                self.logger.error(f"自动调度下一阶段任务失败: {str(e)}")

    def reset_stale_detail_fetching_books(self, timeout_hours: int = 3) -> int:
        """
        重置停留在DETAIL_FETCHING状态过久的书籍
        
        Args:
            timeout_hours: 超时小时数，默认3小时
            
        Returns:
            int: 重置的书籍数量
        """
        reset_count = 0
        try:
            cutoff_time = datetime.now() - timedelta(hours=timeout_hours)
            with self.get_session() as session:
                # 查找停留在DETAIL_FETCHING状态超过指定时间的书籍
                stale_books = session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.DETAIL_FETCHING,
                    DoubanBook.updated_at < cutoff_time
                ).all()
                
                for book in stale_books:
                    try:
                        # 将状态重置为NEW，让系统重新处理
                        old_status = book.status
                        book.status = BookStatus.NEW
                        book.updated_at = datetime.now()
                        
                        # 记录状态变更历史
                        history = BookStatusHistory(
                            book_id=book.id,
                            old_status=old_status,
                            new_status=BookStatus.NEW,
                            change_reason=f"超时重置: detail_fetching状态超过{timeout_hours}小时自动重置",
                            processing_time=0,
                            created_at=datetime.now()
                        )
                        session.add(history)
                        
                        reset_count += 1
                        self.logger.info(
                            f"重置超时书籍状态: {book.title} (ID: {book.id}), "
                            f"{old_status.value} -> {BookStatus.NEW.value}, "
                            f"停留时间: {datetime.now() - book.updated_at}"
                        )
                    except Exception as e:
                        self.logger.error(f"重置书籍状态失败: {book.title} (ID: {book.id}), 错误: {str(e)}")
                        continue
                
                if reset_count > 0:
                    self.logger.info(f"成功重置 {reset_count} 本超时书籍的状态")
                    
        except Exception as e:
            self.logger.error(f"重置超时书籍状态失败: {str(e)}")
        
        return reset_count
