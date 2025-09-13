#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理processing_tasks表中的历史记录
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.state_manager import BookStateManager
from core.task_scheduler import TaskScheduler
from utils.logger import get_logger


def main():
    """清理历史任务记录"""
    logger = get_logger("cleanup_tasks")
    
    try:
        # 初始化组件
        state_manager = BookStateManager()
        scheduler = TaskScheduler(state_manager)
        
        # 执行清理
        logger.info("开始清理历史任务记录...")
        deleted_count = scheduler.cleanup_all_completed_tasks()
        
        logger.info(f"清理完成，删除了 {deleted_count} 条记录")
        
    except Exception as e:
        logger.error(f"清理失败: {str(e)}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())