#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本 V2

将现有数据库迁移到新的Pipeline架构。
"""

import os
import sys
from pathlib import Path
import sqlite3
from typing import Dict, Any
from sqlalchemy import text
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config_manager import ConfigManager
from db.database import Database
from db.models import BookStatus, ProcessingTask, SystemConfig, WorkerStatus
from utils.logger import get_logger, setup_logger


class DatabaseMigrationV2:
    """数据库迁移器 V2"""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        初始化数据库迁移器
        
        Args:
            config_path: 配置文件路径
        """
        # 设置日志
        setup_logger()
        self.logger = get_logger("migration_v2")
        
        # 加载配置
        self.config_manager = ConfigManager(config_path)
        
        # 初始化数据库
        db_url = self.config_manager.get_database_url()
        self.db = Database(db_url)
        self.db_path = db_url.replace("sqlite:///", "")
        
        self.logger.info(f"初始化数据库迁移器 V2: {self.db_path}")
    
    def migrate(self):
        """执行迁移"""
        self.logger.info("开始执行数据库迁移到 Pipeline V2")
        
        try:
            # 1. 备份数据库
            self._backup_database()
            
            # 2. 检查现有表结构
            existing_tables = self._get_existing_tables()
            self.logger.info(f"现有表: {existing_tables}")
            
            # 3. 创建新表
            self._create_new_tables()
            
            # 4. 迁移现有数据
            self._migrate_existing_data()
            
            # 5. 更新书籍状态映射
            self._update_book_status_mapping()
            
            # 6. 初始化系统配置
            self._initialize_system_config()
            
            # 7. 验证迁移结果
            self._verify_migration()
            
            self.logger.info("数据库迁移到 Pipeline V2 完成")
            
        except Exception as e:
            self.logger.error(f"数据库迁移失败: {str(e)}")
            raise
    
    def _backup_database(self):
        """备份数据库"""
        if not os.path.exists(self.db_path):
            self.logger.warning("数据库文件不存在，跳过备份")
            return
        
        backup_path = f"{self.db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        try:
            import shutil
            shutil.copy2(self.db_path, backup_path)
            self.logger.info(f"数据库已备份到: {backup_path}")
        except Exception as e:
            self.logger.error(f"备份数据库失败: {str(e)}")
            raise
    
    def _get_existing_tables(self) -> list:
        """获取现有表列表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            return [row[0] for row in cursor.fetchall()]
    
    def _create_new_tables(self):
        """创建新表"""
        self.logger.info("创建新表结构")
        
        # 初始化数据库（这会创建所有新表）
        self.db.init_db()
        
        self.logger.info("新表结构创建完成")
    
    def _migrate_existing_data(self):
        """迁移现有数据"""
        self.logger.info("开始迁移现有数据")
        
        existing_tables = self._get_existing_tables()
        
        # 豆瓣书籍数据已经存在，不需要迁移
        if 'douban_books' in existing_tables:
            self._migrate_douban_books_data()
        
        # 下载记录数据
        if 'download_records' in existing_tables:
            self._migrate_download_records_data()
        
        # Z-Library书籍数据
        if 'zlibrary_books' in existing_tables:
            self._migrate_zlibrary_books_data()
        
        # 同步任务数据
        if 'sync_tasks' in existing_tables:
            self._migrate_sync_tasks_data()
        
        self.logger.info("现有数据迁移完成")
    
    def _migrate_douban_books_data(self):
        """迁移豆瓣书籍数据"""
        self.logger.info("检查豆瓣书籍数据结构")
        
        with self.db.session_scope() as session:
            # 检查是否需要添加新字段
            try:
                # 尝试查询新字段
                result = session.execute(text("SELECT search_title, search_author FROM douban_books LIMIT 1"))
                self.logger.info("豆瓣书籍表结构已是最新")
            except Exception:
                # 添加新字段
                self.logger.info("添加搜索字段到豆瓣书籍表")
                try:
                    session.execute(text("ALTER TABLE douban_books ADD COLUMN search_title VARCHAR(255)"))
                    session.execute(text("ALTER TABLE douban_books ADD COLUMN search_author VARCHAR(255)"))
                    session.commit()
                    self.logger.info("成功添加搜索字段")
                except Exception as e:
                    self.logger.warning(f"添加搜索字段失败（可能已存在）: {str(e)}")
    
    def _migrate_download_records_data(self):
        """迁移下载记录数据"""
        self.logger.info("检查下载记录数据结构")
        # DownloadRecord表结构基本不变，不需要特殊处理
    
    def _migrate_zlibrary_books_data(self):
        """迁移Z-Library书籍数据"""
        self.logger.info("检查Z-Library书籍数据结构")
        # ZLibraryBook表结构已更新，检查是否需要迁移
        
        with self.db.session_scope() as session:
            try:
                # 检查新字段是否存在
                result = session.execute(text("SELECT raw_json FROM zlibrary_books LIMIT 1"))
                self.logger.info("Z-Library书籍表结构已是最新")
            except Exception:
                self.logger.info("Z-Library书籍表需要更新结构")
                # 如果需要，可以在这里添加字段迁移逻辑
    
    def _migrate_sync_tasks_data(self):
        """迁移同步任务数据"""
        self.logger.info("同步任务数据保持不变")
        # SyncTask表结构基本不变
    
    def _update_book_status_mapping(self):
        """更新书籍状态映射"""
        self.logger.info("更新书籍状态映射到新的Pipeline状态")
        
        # 旧状态到新状态的映射
        status_mapping = {
            # 旧状态 -> 新状态
            'new': BookStatus.NEW,
            'with_detail': BookStatus.DETAIL_COMPLETE,
            'matched': BookStatus.SKIPPED_EXISTS,
            'searching': BookStatus.SEARCH_QUEUED,
            'search_not_found': BookStatus.SEARCH_NO_RESULTS,
            'downloading': BookStatus.DOWNLOAD_QUEUED,
            'downloaded': BookStatus.DOWNLOAD_COMPLETE,
            'uploading': BookStatus.UPLOAD_QUEUED,
            'uploaded': BookStatus.COMPLETED
        }
        
        with self.db.session_scope() as session:
            # 获取需要更新状态的书籍数量
            from db.models import DoubanBook
            
            for old_status, new_status in status_mapping.items():
                try:
                    # 更新状态
                    updated_count = session.execute(
                        text("UPDATE douban_books SET status = :new_status WHERE status = :old_status"),
                        {"new_status": new_status.value, "old_status": old_status}
                    ).rowcount
                    
                    if updated_count > 0:
                        self.logger.info(f"更新状态 {old_status} -> {new_status.value}: {updated_count} 条记录")
                    
                except Exception as e:
                    self.logger.error(f"更新状态映射失败 {old_status} -> {new_status.value}: {str(e)}")
            
            session.commit()
        
        self.logger.info("书籍状态映射更新完成")
    
    def _initialize_system_config(self):
        """初始化系统配置"""
        self.logger.info("初始化系统配置")
        
        default_configs = [
            {
                'key': 'pipeline.max_concurrent_tasks',
                'value': '10',
                'value_type': 'int',
                'description': 'Pipeline最大并发任务数',
                'category': 'pipeline'
            },
            {
                'key': 'pipeline.retry_max_attempts',
                'value': '3',
                'value_type': 'int',
                'description': '最大重试次数',
                'category': 'pipeline'
            },
            {
                'key': 'pipeline.retry_delay_base',
                'value': '30',
                'value_type': 'int',
                'description': '重试基础延迟时间（秒）',
                'category': 'pipeline'
            },
            {
                'key': 'monitoring.metrics_retention_hours',
                'value': '168',  # 7天
                'value_type': 'int',
                'description': '监控指标保留时间（小时）',
                'category': 'monitoring'
            },
            {
                'key': 'monitoring.alert_cooldown_minutes',
                'value': '30',
                'value_type': 'int',
                'description': '告警冷却时间（分钟）',
                'category': 'monitoring'
            }
        ]
        
        with self.db.session_scope() as session:
            for config in default_configs:
                # 检查配置是否已存在
                existing_config = session.query(SystemConfig).filter(
                    SystemConfig.key == config['key']
                ).first()
                
                if not existing_config:
                    system_config = SystemConfig(**config)
                    session.add(system_config)
                    self.logger.info(f"添加系统配置: {config['key']}")
            
            session.commit()
        
        self.logger.info("系统配置初始化完成")
    
    def _verify_migration(self):
        """验证迁移结果"""
        self.logger.info("验证迁移结果")
        
        with self.db.session_scope() as session:
            from db.models import DoubanBook, ProcessingTask, SystemConfig, WorkerStatus, ZLibraryBook
            
            # 检查各表的记录数
            tables_to_check = [
                (DoubanBook, "豆瓣书籍"),
                (ProcessingTask, "处理任务"),
                (SystemConfig, "系统配置"),
                (ZLibraryBook, "Z-Library书籍")
            ]
            
            for model_class, name in tables_to_check:
                try:
                    count = session.query(model_class).count()
                    self.logger.info(f"{name}表: {count} 条记录")
                except Exception as e:
                    self.logger.error(f"检查{name}表失败: {str(e)}")
            
            # 检查书籍状态分布
            from sqlalchemy import func
            try:
                status_distribution = session.query(
                    DoubanBook.status,
                    func.count(DoubanBook.id)
                ).group_by(DoubanBook.status).all()
                
                self.logger.info("书籍状态分布:")
                for status, count in status_distribution:
                    self.logger.info(f"  {status.value}: {count}")
            except Exception as e:
                self.logger.error(f"检查状态分布失败: {str(e)}")
        
        self.logger.info("迁移验证完成")
    
    def rollback(self):
        """回滚迁移"""
        self.logger.info("执行迁移回滚")
        
        # 查找最新的备份文件
        backup_files = []
        db_dir = Path(self.db_path).parent
        
        for file_path in db_dir.glob(f"{Path(self.db_path).name}.backup.*"):
            backup_files.append(file_path)
        
        if not backup_files:
            self.logger.error("未找到备份文件，无法回滚")
            return False
        
        # 选择最新的备份文件
        latest_backup = max(backup_files, key=lambda p: p.stat().st_mtime)
        
        try:
            import shutil
            shutil.copy2(str(latest_backup), self.db_path)
            self.logger.info(f"已从备份文件恢复数据库: {latest_backup}")
            return True
        except Exception as e:
            self.logger.error(f"回滚失败: {str(e)}")
            return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="数据库迁移工具 V2")
    parser.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--rollback", action="store_true", help="回滚迁移")
    parser.add_argument("--verify-only", action="store_true", help="仅验证数据库状态")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.config):
        print(f"错误: 配置文件不存在: {args.config}")
        return 1
    
    try:
        migrator = DatabaseMigrationV2(args.config)
        
        if args.rollback:
            success = migrator.rollback()
            return 0 if success else 1
        elif args.verify_only:
            migrator._verify_migration()
            return 0
        else:
            migrator.migrate()
            return 0
    
    except Exception as e:
        print(f"迁移失败: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())