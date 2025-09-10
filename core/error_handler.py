# -*- coding: utf-8 -*-
"""
错误处理和恢复机制

提供统一的错误处理、分类和恢复策略。
"""

import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from core.pipeline import (AuthError, DownloadLimitExhaustedError,
                           NetworkError, ProcessingError,
                           ResourceNotFoundError)
from core.state_manager import BookStateManager
from db.models import BookStatus, BookStatusHistory, DoubanBook, ProcessingTask
from utils.logger import get_logger


class ErrorSeverity(Enum):
    """错误严重级别"""
    LOW = "low"          # 轻微错误，可以重试
    MEDIUM = "medium"    # 中等错误，需要延迟重试
    HIGH = "high"        # 严重错误，需要人工干预
    CRITICAL = "critical"  # 致命错误，停止处理


class RetryStrategy(Enum):
    """重试策略"""
    IMMEDIATE = "immediate"      # 立即重试
    EXPONENTIAL_BACKOFF = "exponential_backoff"  # 指数退避
    FIXED_DELAY = "fixed_delay"  # 固定延迟
    NO_RETRY = "no_retry"        # 不重试


@dataclass
class ErrorInfo:
    """错误信息"""
    error_type: str
    error_message: str
    severity: ErrorSeverity
    retry_strategy: RetryStrategy
    max_retries: int = 3
    base_delay_seconds: int = 30
    retryable: bool = True
    requires_human_intervention: bool = False


class ErrorClassifier:
    """错误分类器"""
    
    # 错误模式和对应的错误信息
    ERROR_PATTERNS = {
        # 网络相关错误
        "timeout": ErrorInfo(
            error_type="network_timeout",
            error_message="网络超时",
            severity=ErrorSeverity.LOW,
            retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=5,
            base_delay_seconds=30
        ),
        "connection": ErrorInfo(
            error_type="network_connection",
            error_message="网络连接失败",
            severity=ErrorSeverity.MEDIUM,
            retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=3,
            base_delay_seconds=60
        ),
        "dns": ErrorInfo(
            error_type="network_dns",
            error_message="DNS解析失败",
            severity=ErrorSeverity.MEDIUM,
            retry_strategy=RetryStrategy.FIXED_DELAY,
            max_retries=3,
            base_delay_seconds=300
        ),
        
        # 认证相关错误
        "login": ErrorInfo(
            error_type="auth_login",
            error_message="登录失败",
            severity=ErrorSeverity.HIGH,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False,
            requires_human_intervention=True
        ),
        "unauthorized": ErrorInfo(
            error_type="auth_unauthorized",
            error_message="认证失败",
            severity=ErrorSeverity.HIGH,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False,
            requires_human_intervention=True
        ),
        "403": ErrorInfo(
            error_type="auth_forbidden",
            error_message="访问被禁止",
            severity=ErrorSeverity.HIGH,
            retry_strategy=RetryStrategy.FIXED_DELAY,
            max_retries=2,
            base_delay_seconds=3600,  # 1小时后重试
            requires_human_intervention=True
        ),
        
        # 资源相关错误
        "404": ErrorInfo(
            error_type="resource_not_found",
            error_message="资源未找到",
            severity=ErrorSeverity.LOW,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False
        ),
        "not found": ErrorInfo(
            error_type="resource_not_found",
            error_message="资源未找到",
            severity=ErrorSeverity.LOW,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False
        ),
        
        # 系统相关错误
        "disk space": ErrorInfo(
            error_type="system_disk_space",
            error_message="磁盘空间不足",
            severity=ErrorSeverity.CRITICAL,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False,
            requires_human_intervention=True
        ),
        "permission": ErrorInfo(
            error_type="system_permission",
            error_message="权限不足",
            severity=ErrorSeverity.HIGH,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False,
            requires_human_intervention=True
        ),
        
        # 数据相关错误
        "data_missing": ErrorInfo(
            error_type="data_missing",
            error_message="数据缺失",
            severity=ErrorSeverity.MEDIUM,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False
        ),
        "data_invalid": ErrorInfo(
            error_type="data_invalid",
            error_message="数据无效",
            severity=ErrorSeverity.MEDIUM,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False
        ),
        
        # 下载限制相关错误
        "download_limit": ErrorInfo(
            error_type="download_limit_exhausted",
            error_message="下载次数用完",
            severity=ErrorSeverity.MEDIUM,
            retry_strategy=RetryStrategy.NO_RETRY,
            retryable=False,
            requires_human_intervention=True
        )
    }
    
    @classmethod
    def classify_error(cls, error: Exception, context: Dict[str, Any] = None) -> ErrorInfo:
        """
        分类错误
        
        Args:
            error: 异常对象
            context: 上下文信息
            
        Returns:
            ErrorInfo: 错误信息
        """
        error_message = str(error).lower()
        
        # 检查异常类型
        if isinstance(error, DownloadLimitExhaustedError):
            return cls.ERROR_PATTERNS["download_limit"]
        elif isinstance(error, NetworkError):
            return cls._get_network_error_info(error_message)
        elif isinstance(error, AuthError):
            return cls._get_auth_error_info(error_message)
        elif isinstance(error, ResourceNotFoundError):
            return cls._get_resource_error_info(error_message)
        elif isinstance(error, ProcessingError):
            if hasattr(error, 'error_type'):
                pattern = error.error_type
            else:
                pattern = "processing"
        else:
            # 根据错误消息匹配模式
            pattern = cls._match_error_pattern(error_message)
        
        # 获取对应的错误信息
        return cls.ERROR_PATTERNS.get(pattern, cls._get_default_error_info(error_message))
    
    @classmethod
    def _match_error_pattern(cls, error_message: str) -> str:
        """匹配错误模式"""
        for pattern in cls.ERROR_PATTERNS.keys():
            if pattern in error_message:
                return pattern
        return "unknown"
    
    @classmethod
    def _get_network_error_info(cls, error_message: str) -> ErrorInfo:
        """获取网络错误信息"""
        if "timeout" in error_message:
            return cls.ERROR_PATTERNS["timeout"]
        elif "connection" in error_message:
            return cls.ERROR_PATTERNS["connection"]
        elif "dns" in error_message:
            return cls.ERROR_PATTERNS["dns"]
        else:
            return ErrorInfo(
                error_type="network_unknown",
                error_message="网络错误",
                severity=ErrorSeverity.MEDIUM,
                retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                max_retries=3
            )
    
    @classmethod
    def _get_auth_error_info(cls, error_message: str) -> ErrorInfo:
        """获取认证错误信息"""
        if "403" in error_message:
            return cls.ERROR_PATTERNS["403"]
        elif "login" in error_message:
            return cls.ERROR_PATTERNS["login"]
        else:
            return cls.ERROR_PATTERNS["unauthorized"]
    
    @classmethod
    def _get_resource_error_info(cls, error_message: str) -> ErrorInfo:
        """获取资源错误信息"""
        return cls.ERROR_PATTERNS["not found"]
    
    @classmethod
    def _get_default_error_info(cls, error_message: str) -> ErrorInfo:
        """获取默认错误信息"""
        return ErrorInfo(
            error_type="unknown",
            error_message="未知错误",
            severity=ErrorSeverity.MEDIUM,
            retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            max_retries=2,
            base_delay_seconds=60
        )


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, state_manager: BookStateManager):
        """
        初始化错误处理器
        
        Args:
            state_manager: 状态管理器
        """
        self.state_manager = state_manager
        self.logger = get_logger("error_handler")
        
        # 错误处理回调函数
        self._error_callbacks: Dict[str, List[Callable]] = {}
        
        # 统计信息
        self._error_stats = {
            'total_errors': 0,
            'errors_by_type': {},
            'errors_by_severity': {},
            'recovery_success_rate': 0.0
        }
    
    def handle_error(
        self,
        book_id: int,
        stage: str,
        error: Exception,
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        处理错误
        
        Args:
            book_id: 书籍ID
            stage: 处理阶段
            error: 异常对象
            context: 上下文信息
            
        Returns:
            Dict[str, Any]: 处理结果
        """
        try:
            # 分类错误
            error_info = ErrorClassifier.classify_error(error, context)
            
            # 更新统计
            self._update_error_stats(error_info)
            
            # 记录错误详情
            self._log_error_details(book_id, stage, error, error_info, context)
            
            # 执行错误处理策略
            recovery_action = self._execute_error_strategy(book_id, stage, error_info)
            
            # 触发错误回调
            self._trigger_error_callbacks(error_info.error_type, {
                'book_id': book_id,
                'stage': stage,
                'error': error,
                'error_info': error_info,
                'recovery_action': recovery_action,
                'context': context
            })
            
            return {
                'handled': True,
                'error_type': error_info.error_type,
                'severity': error_info.severity.value,
                'retryable': error_info.retryable,
                'recovery_action': recovery_action,
                'requires_human_intervention': error_info.requires_human_intervention
            }
            
        except Exception as handler_error:
            self.logger.error(f"错误处理器本身出错: {str(handler_error)}")
            self.logger.error(traceback.format_exc())
            
            # 回退到基本错误处理
            return self._fallback_error_handling(book_id, stage, error)
    
    def _execute_error_strategy(self, book_id: int, stage: str, error_info: ErrorInfo) -> Dict[str, Any]:
        """执行错误处理策略"""
        with self.state_manager.get_session() as session:
            book = session.get(DoubanBook, book_id)
        if not book:
            return {'action': 'skip', 'reason': 'book not found'}
        
        # 检查重试次数
        retry_count = self._get_retry_count(book_id, stage)
        
        if not error_info.retryable or retry_count >= error_info.max_retries:
            # 标记为永久失败
            self.state_manager.transition_status(
                book_id,
                BookStatus.FAILED_PERMANENT,
                f"{stage}阶段错误: {error_info.error_message}",
                error_message=f"错误类型: {error_info.error_type}, 重试次数: {retry_count}"
            )
            
            return {
                'action': 'mark_failed',
                'reason': f'超过最大重试次数或不可重试错误: {error_info.error_type}'
            }
        
        # 计算重试时间
        next_retry_time = self._calculate_retry_time(retry_count, error_info)
        
        # 设置重试状态
        retry_status = self._get_retry_status(stage)
        
        self.state_manager.transition_status(
            book_id,
            retry_status,
            f"{stage}阶段错误，准备重试",
            error_message=f"错误类型: {error_info.error_type}, 重试计划: {next_retry_time}",
            retry_count=retry_count + 1
        )
        
        return {
            'action': 'schedule_retry',
            'retry_count': retry_count + 1,
            'max_retries': error_info.max_retries,
            'next_retry_time': next_retry_time,
            'retry_strategy': error_info.retry_strategy.value
        }
    
    def _calculate_retry_time(self, retry_count: int, error_info: ErrorInfo) -> datetime:
        """计算重试时间"""
        base_delay = error_info.base_delay_seconds
        
        if error_info.retry_strategy == RetryStrategy.IMMEDIATE:
            delay_seconds = 0
        elif error_info.retry_strategy == RetryStrategy.FIXED_DELAY:
            delay_seconds = base_delay
        elif error_info.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay_seconds = base_delay * (2 ** retry_count)
            # 限制最大延迟
            delay_seconds = min(delay_seconds, 3600)  # 最大1小时
        else:
            delay_seconds = base_delay
        
        return datetime.now() + timedelta(seconds=delay_seconds)
    
    def _get_retry_status(self, stage: str) -> BookStatus:
        """获取重试状态"""
        retry_status_mapping = {
            'data_collection': BookStatus.NEW,
            'search': BookStatus.SEARCH_QUEUED,
            'download': BookStatus.DOWNLOAD_QUEUED,
            'upload': BookStatus.UPLOAD_QUEUED
        }
        return retry_status_mapping.get(stage, BookStatus.FAILED_PERMANENT)
    
    def _get_retry_count(self, book_id: int, stage: str) -> int:
        """获取重试次数"""
        try:
            # 查询最近的错误历史记录
            with self.state_manager.get_session() as session:
                recent_errors = session.query(BookStatusHistory).filter(
                    BookStatusHistory.book_id == book_id,
                    BookStatusHistory.error_message.isnot(None),
                    BookStatusHistory.created_at > datetime.now() - timedelta(hours=24)
                ).count()
            
            return recent_errors
        except Exception as e:
            self.logger.error(f"获取重试次数失败: {str(e)}")
            return 0
    
    def _log_error_details(
        self,
        book_id: int,
        stage: str,
        error: Exception,
        error_info: ErrorInfo,
        context: Dict[str, Any] = None
    ):
        """记录错误详情"""
        with self.state_manager.get_session() as session:
            book = session.get(DoubanBook, book_id)
        book_title = book.title if book else f"ID:{book_id}"
        
        self.logger.error(
            f"处理错误 - 书籍: {book_title}, 阶段: {stage}, "
            f"错误类型: {error_info.error_type}, 严重级别: {error_info.severity.value}"
        )
        self.logger.error(f"错误消息: {str(error)}")
        
        if context:
            self.logger.debug(f"上下文信息: {context}")
        
        # 记录详细的堆栈跟踪（仅用于调试）
        if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.logger.debug(f"堆栈跟踪:\n{traceback.format_exc()}")
    
    def _update_error_stats(self, error_info: ErrorInfo):
        """更新错误统计"""
        self._error_stats['total_errors'] += 1
        
        # 按类型统计
        error_type = error_info.error_type
        if error_type not in self._error_stats['errors_by_type']:
            self._error_stats['errors_by_type'][error_type] = 0
        self._error_stats['errors_by_type'][error_type] += 1
        
        # 按严重级别统计
        severity = error_info.severity.value
        if severity not in self._error_stats['errors_by_severity']:
            self._error_stats['errors_by_severity'][severity] = 0
        self._error_stats['errors_by_severity'][severity] += 1
    
    def _trigger_error_callbacks(self, error_type: str, callback_data: Dict[str, Any]):
        """触发错误回调"""
        if error_type in self._error_callbacks:
            for callback in self._error_callbacks[error_type]:
                try:
                    callback(callback_data)
                except Exception as e:
                    self.logger.error(f"错误回调执行失败: {str(e)}")
    
    def _fallback_error_handling(self, book_id: int, stage: str, error: Exception) -> Dict[str, Any]:
        """回退错误处理"""
        self.logger.error(f"使用回退错误处理: 书籍ID {book_id}, 阶段 {stage}")
        
        # 简单地标记为失败
        self.state_manager.transition_status(
            book_id,
            BookStatus.FAILED_PERMANENT,
            f"{stage}阶段错误（回退处理）",
            error_message=str(error)
        )
        
        return {
            'handled': True,
            'error_type': 'fallback',
            'severity': 'high',
            'retryable': False,
            'recovery_action': {'action': 'mark_failed', 'reason': 'fallback error handling'}
        }
    
    def register_error_callback(self, error_type: str, callback: Callable):
        """
        注册错误回调函数
        
        Args:
            error_type: 错误类型
            callback: 回调函数
        """
        if error_type not in self._error_callbacks:
            self._error_callbacks[error_type] = []
        self._error_callbacks[error_type].append(callback)
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """获取错误统计信息"""
        return self._error_stats.copy()
    
    def reset_error_statistics(self):
        """重置错误统计"""
        self._error_stats = {
            'total_errors': 0,
            'errors_by_type': {},
            'errors_by_severity': {},
            'recovery_success_rate': 0.0
        }