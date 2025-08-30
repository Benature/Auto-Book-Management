# -*- coding: utf-8 -*-
"""
监控系统

提供系统监控、指标收集和告警功能。
"""

import time
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
from sqlalchemy.orm import Session

from db.models import BookStatus, DoubanBook, ProcessingTask
from utils.logger import get_logger


class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"        # 计数器
    GAUGE = "gauge"           # 仪表盘
    HISTOGRAM = "histogram"   # 直方图
    RATE = "rate"            # 速率


@dataclass
class Metric:
    """指标数据"""
    name: str
    value: float
    metric_type: MetricType
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    condition: Callable[[float], bool]
    message_template: str
    severity: str = "warning"
    cooldown_minutes: int = 30
    last_triggered: Optional[datetime] = None


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self, db_session: Session, collection_interval: int = 60):
        """
        初始化指标收集器
        
        Args:
            db_session: 数据库会话
            collection_interval: 收集间隔（秒）
        """
        self.db_session = db_session
        self.collection_interval = collection_interval
        self.logger = get_logger("metrics_collector")
        
        # 指标存储
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._metrics_lock = threading.Lock()
        
        # 收集器状态
        self._running = False
        self._stop_event = threading.Event()
        self._collector_thread: Optional[threading.Thread] = None
        
        # 注册的自定义指标收集器
        self._custom_collectors: List[Callable] = []
    
    def start(self):
        """启动指标收集"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._collector_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._collector_thread.start()
        self.logger.info("指标收集器已启动")
    
    def stop(self):
        """停止指标收集"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._collector_thread and self._collector_thread.is_alive():
            self._collector_thread.join(timeout=10)
        
        self.logger.info("指标收集器已停止")
    
    def _collection_loop(self):
        """收集循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self._collect_system_metrics()
                self._collect_custom_metrics()
                
                # 等待下一次收集
                if self._stop_event.wait(self.collection_interval):
                    break
                    
            except Exception as e:
                self.logger.error(f"指标收集异常: {str(e)}")
                time.sleep(self.collection_interval)
    
    def _collect_system_metrics(self):
        """收集系统指标"""
        try:
            # 书籍状态统计
            status_stats = self._collect_book_status_metrics()
            for status, count in status_stats.items():
                self._record_metric(Metric(
                    name="books_by_status",
                    value=count,
                    metric_type=MetricType.GAUGE,
                    labels={"status": status}
                ))
            
            # 任务统计
            task_stats = self._collect_task_metrics()
            for stage, count in task_stats.items():
                self._record_metric(Metric(
                    name="tasks_by_stage",
                    value=count,
                    metric_type=MetricType.GAUGE,
                    labels={"stage": stage}
                ))
            
            # 错误率统计
            error_rate = self._collect_error_rate()
            self._record_metric(Metric(
                name="error_rate",
                value=error_rate,
                metric_type=MetricType.GAUGE
            ))
            
            # 处理速度统计
            processing_rate = self._collect_processing_rate()
            self._record_metric(Metric(
                name="processing_rate",
                value=processing_rate,
                metric_type=MetricType.RATE,
                labels={"unit": "books_per_hour"}
            ))
            
        except Exception as e:
            self.logger.error(f"收集系统指标失败: {str(e)}")
    
    def _collect_book_status_metrics(self) -> Dict[str, int]:
        """收集书籍状态指标"""
        try:
            from sqlalchemy import func
            
            results = self.db_session.query(
                DoubanBook.status,
                func.count(DoubanBook.id)
            ).group_by(DoubanBook.status).all()
            
            return {status.value: count for status, count in results}
        except Exception:
            return {}
    
    def _collect_task_metrics(self) -> Dict[str, int]:
        """收集任务指标"""
        try:
            from sqlalchemy import func
            
            results = self.db_session.query(
                ProcessingTask.stage,
                func.count(ProcessingTask.id)
            ).filter(
                ProcessingTask.status.in_(['queued', 'active'])
            ).group_by(ProcessingTask.stage).all()
            
            return {stage: count for stage, count in results}
        except Exception:
            return {}
    
    def _collect_error_rate(self) -> float:
        """收集错误率"""
        try:
            # 计算最近1小时的错误率
            one_hour_ago = datetime.now() - timedelta(hours=1)
            
            total_tasks = self.db_session.query(ProcessingTask).filter(
                ProcessingTask.created_at >= one_hour_ago
            ).count()
            
            failed_tasks = self.db_session.query(ProcessingTask).filter(
                ProcessingTask.created_at >= one_hour_ago,
                ProcessingTask.status == 'failed'
            ).count()
            
            if total_tasks > 0:
                return (failed_tasks / total_tasks) * 100
            return 0.0
        except Exception:
            return 0.0
    
    def _collect_processing_rate(self) -> float:
        """收集处理速度"""
        try:
            # 计算最近1小时的处理速度
            one_hour_ago = datetime.now() - timedelta(hours=1)
            
            completed_count = self.db_session.query(DoubanBook).filter(
                DoubanBook.updated_at >= one_hour_ago,
                DoubanBook.status == BookStatus.COMPLETED
            ).count()
            
            return completed_count  # 本小时完成的书籍数
        except Exception:
            return 0.0
    
    def _collect_custom_metrics(self):
        """收集自定义指标"""
        for collector in self._custom_collectors:
            try:
                metrics = collector()
                if isinstance(metrics, list):
                    for metric in metrics:
                        if isinstance(metric, Metric):
                            self._record_metric(metric)
            except Exception as e:
                self.logger.error(f"自定义指标收集失败: {str(e)}")
    
    def _record_metric(self, metric: Metric):
        """记录指标"""
        with self._metrics_lock:
            metric_key = self._get_metric_key(metric.name, metric.labels)
            self._metrics[metric_key].append(metric)
    
    def _get_metric_key(self, name: str, labels: Dict[str, str]) -> str:
        """生成指标键"""
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name
    
    def register_custom_collector(self, collector: Callable[[], List[Metric]]):
        """
        注册自定义指标收集器
        
        Args:
            collector: 收集器函数，返回Metric列表
        """
        self._custom_collectors.append(collector)
    
    def get_metrics(self, name: str = None, time_range_minutes: int = 60) -> List[Metric]:
        """
        获取指标数据
        
        Args:
            name: 指标名称（可选）
            time_range_minutes: 时间范围（分钟）
            
        Returns:
            List[Metric]: 指标列表
        """
        cutoff_time = datetime.now() - timedelta(minutes=time_range_minutes)
        metrics = []
        
        with self._metrics_lock:
            for metric_key, metric_queue in self._metrics.items():
                if name and not metric_key.startswith(name):
                    continue
                
                # 过滤时间范围内的指标
                filtered_metrics = [
                    m for m in metric_queue 
                    if m.timestamp >= cutoff_time
                ]
                metrics.extend(filtered_metrics)
        
        return sorted(metrics, key=lambda m: m.timestamp)
    
    def get_latest_metric_value(self, name: str, labels: Dict[str, str] = None) -> Optional[float]:
        """
        获取最新的指标值
        
        Args:
            name: 指标名称
            labels: 标签过滤
            
        Returns:
            Optional[float]: 最新指标值
        """
        metric_key = self._get_metric_key(name, labels or {})
        
        with self._metrics_lock:
            if metric_key in self._metrics and self._metrics[metric_key]:
                return self._metrics[metric_key][-1].value
        
        return None


class AlertManager:
    """告警管理器"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """
        初始化告警管理器
        
        Args:
            metrics_collector: 指标收集器
        """
        self.metrics_collector = metrics_collector
        self.logger = get_logger("alert_manager")
        
        # 告警规则
        self.alert_rules: Dict[str, AlertRule] = {}
        
        # 告警回调
        self.alert_callbacks: List[Callable[[str, str, str], None]] = []
        
        # 告警管理器状态
        self._running = False
        self._stop_event = threading.Event()
        self._alert_thread: Optional[threading.Thread] = None
        
        # 注册默认告警规则
        self._register_default_alerts()
    
    def _register_default_alerts(self):
        """注册默认告警规则"""
        # 高错误率告警
        self.add_alert_rule(AlertRule(
            name="high_error_rate",
            condition=lambda x: x > 50,  # 错误率 > 50%
            message_template="错误率过高: {value:.1f}%",
            severity="critical",
            cooldown_minutes=15
        ))
        
        # 处理速度过慢告警
        self.add_alert_rule(AlertRule(
            name="slow_processing",
            condition=lambda x: x < 1,  # 处理速度 < 1本/小时
            message_template="处理速度过慢: {value:.1f} 本/小时",
            severity="warning",
            cooldown_minutes=60
        ))
        
        # 队列积压告警
        def check_queue_backlog():
            total_queued = 0
            for stage in ['data_collection', 'search', 'download', 'upload']:
                count = self.metrics_collector.get_latest_metric_value(
                    "tasks_by_stage", {"stage": stage}
                )
                if count:
                    total_queued += count
            return total_queued
        
        self.add_alert_rule(AlertRule(
            name="queue_backlog",
            condition=lambda x: x > 100,  # 队列积压 > 100个任务
            message_template="队列积压严重: {value:.0f} 个待处理任务",
            severity="warning",
            cooldown_minutes=30
        ))
    
    def start(self):
        """启动告警管理器"""
        if self._running:
            return
        
        self._running = True
        self._stop_event.clear()
        self._alert_thread = threading.Thread(target=self._alert_loop, daemon=True)
        self._alert_thread.start()
        self.logger.info("告警管理器已启动")
    
    def stop(self):
        """停止告警管理器"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._alert_thread and self._alert_thread.is_alive():
            self._alert_thread.join(timeout=10)
        
        self.logger.info("告警管理器已停止")
    
    def _alert_loop(self):
        """告警循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self._check_alerts()
                
                # 每分钟检查一次
                if self._stop_event.wait(60):
                    break
                    
            except Exception as e:
                self.logger.error(f"告警检查异常: {str(e)}")
                time.sleep(60)
    
    def _check_alerts(self):
        """检查告警"""
        current_time = datetime.now()
        
        for rule in self.alert_rules.values():
            try:
                # 检查冷却时间
                if (rule.last_triggered and 
                    (current_time - rule.last_triggered).total_seconds() < rule.cooldown_minutes * 60):
                    continue
                
                # 获取相应的指标值
                metric_value = self._get_metric_value_for_rule(rule)
                
                if metric_value is not None and rule.condition(metric_value):
                    # 触发告警
                    message = rule.message_template.format(value=metric_value)
                    self._trigger_alert(rule.name, rule.severity, message)
                    rule.last_triggered = current_time
                    
            except Exception as e:
                self.logger.error(f"检查告警规则 {rule.name} 失败: {str(e)}")
    
    def _get_metric_value_for_rule(self, rule: AlertRule) -> Optional[float]:
        """获取告警规则对应的指标值"""
        # 根据告警规则名称获取对应的指标
        metric_mapping = {
            "high_error_rate": "error_rate",
            "slow_processing": "processing_rate",
            "queue_backlog": self._calculate_total_queue_size
        }
        
        if rule.name in metric_mapping:
            metric_or_func = metric_mapping[rule.name]
            
            if callable(metric_or_func):
                return metric_or_func()
            else:
                return self.metrics_collector.get_latest_metric_value(metric_or_func)
        
        return None
    
    def _calculate_total_queue_size(self) -> float:
        """计算总队列大小"""
        total = 0.0
        for stage in ['data_collection', 'search', 'download', 'upload']:
            count = self.metrics_collector.get_latest_metric_value(
                "tasks_by_stage", {"stage": stage}
            )
            if count:
                total += count
        return total
    
    def _trigger_alert(self, name: str, severity: str, message: str):
        """触发告警"""
        self.logger.warning(f"告警触发 [{severity.upper()}] {name}: {message}")
        
        # 执行告警回调
        for callback in self.alert_callbacks:
            try:
                callback(name, severity, message)
            except Exception as e:
                self.logger.error(f"告警回调执行失败: {str(e)}")
    
    def add_alert_rule(self, rule: AlertRule):
        """
        添加告警规则
        
        Args:
            rule: 告警规则
        """
        self.alert_rules[rule.name] = rule
        self.logger.info(f"添加告警规则: {rule.name}")
    
    def remove_alert_rule(self, name: str):
        """
        移除告警规则
        
        Args:
            name: 规则名称
        """
        if name in self.alert_rules:
            del self.alert_rules[name]
            self.logger.info(f"移除告警规则: {name}")
    
    def register_alert_callback(self, callback: Callable[[str, str, str], None]):
        """
        注册告警回调函数
        
        Args:
            callback: 回调函数，参数为(name, severity, message)
        """
        self.alert_callbacks.append(callback)


class MonitoringSystem:
    """监控系统"""
    
    def __init__(self, db_session: Session):
        """
        初始化监控系统
        
        Args:
            db_session: 数据库会话
        """
        self.db_session = db_session
        self.logger = get_logger("monitoring_system")
        
        # 初始化组件
        self.metrics_collector = MetricsCollector(db_session)
        self.alert_manager = AlertManager(self.metrics_collector)
    
    def start(self):
        """启动监控系统"""
        self.logger.info("启动监控系统")
        self.metrics_collector.start()
        self.alert_manager.start()
    
    def stop(self):
        """停止监控系统"""
        self.logger.info("停止监控系统")
        self.alert_manager.stop()
        self.metrics_collector.stop()
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据"""
        return {
            'timestamp': datetime.now().isoformat(),
            'book_statistics': {
                status: self.metrics_collector.get_latest_metric_value(
                    "books_by_status", {"status": status}
                ) or 0
                for status in BookStatus.__members__.values()
            },
            'task_statistics': {
                stage: self.metrics_collector.get_latest_metric_value(
                    "tasks_by_stage", {"stage": stage}
                ) or 0
                for stage in ['data_collection', 'search', 'download', 'upload']
            },
            'performance_metrics': {
                'error_rate': self.metrics_collector.get_latest_metric_value("error_rate") or 0,
                'processing_rate': self.metrics_collector.get_latest_metric_value("processing_rate") or 0
            },
            'alert_rules': [
                {
                    'name': rule.name,
                    'severity': rule.severity,
                    'last_triggered': rule.last_triggered.isoformat() if rule.last_triggered else None
                }
                for rule in self.alert_manager.alert_rules.values()
            ]
        }