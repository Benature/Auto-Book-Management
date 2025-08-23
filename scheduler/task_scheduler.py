# -*- coding: utf-8 -*-
"""
任务调度器

负责定期执行豆瓣书籍同步任务。
"""

import schedule
import time
import threading
from typing import Callable, Dict, Any, List, Optional
import logging
from datetime import datetime, timedelta
import traceback

from utils.logger import get_logger, log_exception


class TaskScheduler:
    """任务调度器类"""

    def __init__(self):
        """
        初始化任务调度器
        """
        self.logger = get_logger("task_scheduler")
        self.running = False
        self.scheduler_thread = None
        self.tasks = {}

    def add_task(self, name: str, func: Callable, *args, **kwargs) -> None:
        """
        添加任务
        
        Args:
            name: 任务名称
            func: 任务函数
            *args: 函数参数
            **kwargs: 函数关键字参数
        """
        self.tasks[name] = {
            'func': func,
            'args': args,
            'kwargs': kwargs,
            'schedule': None,
            'last_run': None,
            'next_run': None,
            'enabled': True
        }
        self.logger.info(f"添加任务: {name}")

    def schedule_task(self, name: str, schedule_type: str,
                      **schedule_kwargs) -> bool:
        """
        设置任务调度
        
        Args:
            name: 任务名称
            schedule_type: 调度类型 (daily, weekly, interval)
            **schedule_kwargs: 调度参数
                - daily: at (HH:MM 格式)
                - weekly: day (0-6, 0=周一), at (HH:MM 格式)
                - interval: hours/minutes/seconds
                
        Returns:
            bool: 是否成功设置调度
        """
        if name not in self.tasks:
            self.logger.error(f"任务不存在: {name}")
            return False

        task = self.tasks[name]
        func = task['func']
        args = task['args']
        kwargs = task['kwargs']

        # 包装任务函数，添加错误处理和日志
        def task_wrapper():
            try:
                self.logger.info(f"执行任务: {name}")
                task['last_run'] = datetime.now()
                result = func(*args, **kwargs)
                self.logger.info(f"任务完成: {name}")
                return result
            except Exception as e:
                self.logger.error(f"任务执行失败: {name}, 错误: {str(e)}")
                log_exception(e)
                return None

        # 根据调度类型设置调度
        if schedule_type == 'daily':
            if 'at' not in schedule_kwargs:
                self.logger.error(f"缺少参数 'at' 用于每日调度: {name}")
                return False

            task['schedule'] = schedule.every().day.at(
                schedule_kwargs['at']).do(task_wrapper)
            next_run = self._calculate_next_run_time('daily', schedule_kwargs)

        elif schedule_type == 'weekly':
            if 'day' not in schedule_kwargs or 'at' not in schedule_kwargs:
                self.logger.error(f"缺少参数 'day' 或 'at' 用于每周调度: {name}")
                return False

            day_mapping = {
                0: schedule.every().monday,
                1: schedule.every().tuesday,
                2: schedule.every().wednesday,
                3: schedule.every().thursday,
                4: schedule.every().friday,
                5: schedule.every().saturday,
                6: schedule.every().sunday
            }

            day = schedule_kwargs['day']
            if day not in day_mapping:
                self.logger.error(f"无效的星期几参数: {day}")
                return False

            task['schedule'] = day_mapping[day].at(
                schedule_kwargs['at']).do(task_wrapper)
            next_run = self._calculate_next_run_time('weekly', schedule_kwargs)

        elif schedule_type == 'interval':
            interval_set = False

            if 'hours' in schedule_kwargs and schedule_kwargs['hours'] > 0:
                task['schedule'] = schedule.every(
                    schedule_kwargs['hours']).hours.do(task_wrapper)
                next_run = datetime.now() + timedelta(
                    hours=schedule_kwargs['hours'])
                interval_set = True

            elif 'minutes' in schedule_kwargs and schedule_kwargs[
                    'minutes'] > 0:
                task['schedule'] = schedule.every(
                    schedule_kwargs['minutes']).minutes.do(task_wrapper)
                next_run = datetime.now() + timedelta(
                    minutes=schedule_kwargs['minutes'])
                interval_set = True

            elif 'seconds' in schedule_kwargs and schedule_kwargs[
                    'seconds'] > 0:
                task['schedule'] = schedule.every(
                    schedule_kwargs['seconds']).seconds.do(task_wrapper)
                next_run = datetime.now() + timedelta(
                    seconds=schedule_kwargs['seconds'])
                interval_set = True

            if not interval_set:
                self.logger.error(f"缺少有效的间隔参数 (hours/minutes/seconds): {name}")
                return False
        else:
            self.logger.error(f"无效的调度类型: {schedule_type}")
            return False

        task['next_run'] = next_run
        self.logger.info(f"设置任务调度: {name}, 下次执行时间: {next_run}")
        return True

    def _calculate_next_run_time(self, schedule_type: str,
                                 schedule_kwargs: Dict[str, Any]) -> datetime:
        """
        计算下次执行时间
        
        Args:
            schedule_type: 调度类型
            schedule_kwargs: 调度参数
            
        Returns:
            datetime: 下次执行时间
        """
        now = datetime.now()

        if schedule_type == 'daily':
            time_str = schedule_kwargs['at']
            hour, minute = map(int, time_str.split(':'))
            next_run = now.replace(hour=hour,
                                   minute=minute,
                                   second=0,
                                   microsecond=0)

            if next_run <= now:
                next_run += timedelta(days=1)

        elif schedule_type == 'weekly':
            time_str = schedule_kwargs['at']
            day = schedule_kwargs['day']  # 0-6, 0=周一
            hour, minute = map(int, time_str.split(':'))

            # 计算下一个指定星期几
            days_ahead = day - now.weekday()
            if days_ahead <= 0:  # 如果今天已经是指定的星期几或已经过了，则计算下周
                days_ahead += 7

            next_run = now.replace(
                hour=hour, minute=minute, second=0,
                microsecond=0) + timedelta(days=days_ahead)

            # 如果今天是指定的星期几，但时间已经过了，则计算下周
            if days_ahead == 0 and next_run <= now:
                next_run += timedelta(days=7)
        else:
            # 对于 interval 类型，在调用函数中直接计算
            next_run = now

        return next_run

    def enable_task(self, name: str) -> bool:
        """
        启用任务
        
        Args:
            name: 任务名称
            
        Returns:
            bool: 是否成功启用
        """
        if name not in self.tasks:
            self.logger.error(f"任务不存在: {name}")
            return False

        self.tasks[name]['enabled'] = True
        self.logger.info(f"启用任务: {name}")
        return True

    def disable_task(self, name: str) -> bool:
        """
        禁用任务
        
        Args:
            name: 任务名称
            
        Returns:
            bool: 是否成功禁用
        """
        if name not in self.tasks:
            self.logger.error(f"任务不存在: {name}")
            return False

        self.tasks[name]['enabled'] = False
        self.logger.info(f"禁用任务: {name}")
        return True

    def get_task_status(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取任务状态
        
        Args:
            name: 任务名称，如果为 None 则返回所有任务状态
            
        Returns:
            Dict[str, Any]: 任务状态信息
        """
        if name is not None:
            if name not in self.tasks:
                return {}

            task = self.tasks[name]
            return {
                'name':
                name,
                'enabled':
                task['enabled'],
                'last_run':
                task['last_run'].strftime('%Y-%m-%d %H:%M:%S')
                if task['last_run'] else None,
                'next_run':
                task['next_run'].strftime('%Y-%m-%d %H:%M:%S')
                if task['next_run'] else None
            }
        else:
            result = {}
            for name, task in self.tasks.items():
                result[name] = {
                    'enabled':
                    task['enabled'],
                    'last_run':
                    task['last_run'].strftime('%Y-%m-%d %H:%M:%S')
                    if task['last_run'] else None,
                    'next_run':
                    task['next_run'].strftime('%Y-%m-%d %H:%M:%S')
                    if task['next_run'] else None
                }
            return result

    def run_task_now(self, name: str) -> bool:
        """
        立即执行任务
        
        Args:
            name: 任务名称
            
        Returns:
            bool: 是否成功执行
        """
        if name not in self.tasks:
            self.logger.error(f"任务不存在: {name}")
            return False

        task = self.tasks[name]
        if not task['enabled']:
            self.logger.warning(f"任务已禁用: {name}")
            return False

        try:
            self.logger.info(f"立即执行任务: {name}")
            task['last_run'] = datetime.now()
            result = task['func'](*task['args'], **task['kwargs'])
            self.logger.info(f"任务完成: {name}")
            return True
        except Exception as e:
            self.logger.error(f"任务执行失败: {name}, 错误: {str(e)}")
            log_exception(e)
            return False

    def start(self) -> None:
        """
        启动调度器
        """
        if self.running:
            self.logger.warning("调度器已经在运行")
            return

        self.running = True
        self.logger.info("启动任务调度器")

        def run_scheduler():
            while self.running:
                try:
                    # 运行所有已启用的任务
                    schedule.run_pending()

                    # 更新任务的下次执行时间
                    for name, task in self.tasks.items():
                        if task['schedule'] and task['enabled']:
                            job = task['schedule']
                            if hasattr(job, 'next_run'):
                                task['next_run'] = job.next_run

                    # 休眠 1 秒
                    time.sleep(1)
                except Exception as e:
                    self.logger.error(f"调度器运行异常: {str(e)}")
                    log_exception(e)
                    time.sleep(5)  # 出错后等待 5 秒再继续

        # 创建并启动调度器线程
        self.scheduler_thread = threading.Thread(target=run_scheduler,
                                                 daemon=True)
        self.scheduler_thread.start()

    def stop(self) -> None:
        """
        停止调度器
        """
        if not self.running:
            self.logger.warning("调度器未运行")
            return

        self.logger.info("停止任务调度器")
        self.running = False

        # 等待调度器线程结束
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)

        # 清除所有调度任务
        schedule.clear()

        # 重置任务的调度信息
        for name, task in self.tasks.items():
            task['schedule'] = None
            task['next_run'] = None
