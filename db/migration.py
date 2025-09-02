# -*- coding: utf-8 -*-
"""
数据库迁移

处理数据库结构变化和数据迁移。
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from utils.logger import get_logger


class Migration:
    """数据库迁移类"""
    
    def __init__(self, db_path: str):
        """
        初始化迁移工具
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.logger = get_logger("migration")
        
    def _execute_sql(self, sql: str, params: tuple = None) -> None:
        """
        执行SQL语句
        
        Args:
            sql: SQL语句
            params: 参数
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            conn.commit()
            conn.close()
            self.logger.info(f"执行SQL成功: {sql[:50]}...")
        except Exception as e:
            self.logger.error(f"执行SQL失败: {sql[:50]}... - {str(e)}")
            raise
    
    def _table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        Args:
            table_name: 表名
            
        Returns:
            bool: 表是否存在
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
            result = cursor.fetchone() is not None
            conn.close()
            return result
        except Exception as e:
            self.logger.error(f"检查表存在性失败: {table_name} - {str(e)}")
            return False
    
    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """
        检查列是否存在
        
        Args:
            table_name: 表名
            column_name: 列名
            
        Returns:
            bool: 列是否存在
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [column[1] for column in cursor.fetchall()]
            conn.close()
            return column_name in columns
        except Exception as e:
            self.logger.error(f"检查列存在性失败: {table_name}.{column_name} - {str(e)}")
            return False
    
    def _get_migration_version(self) -> int:
        """
        获取当前迁移版本
        
        Returns:
            int: 当前版本号
        """
        try:
            # 如果迁移表不存在，创建它
            if not self._table_exists('migration_versions'):
                self._execute_sql('''
                    CREATE TABLE migration_versions (
                        id INTEGER PRIMARY KEY,
                        version INTEGER NOT NULL,
                        applied_at DATETIME NOT NULL
                    )
                ''')
                self._execute_sql(
                    "INSERT INTO migration_versions (version, applied_at) VALUES (?, ?)",
                    (0, datetime.now().isoformat())
                )
                return 0
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(version) FROM migration_versions")
            result = cursor.fetchone()
            conn.close()
            return result[0] if result[0] is not None else 0
        except Exception as e:
            self.logger.error(f"获取迁移版本失败: {str(e)}")
            return 0
    
    def _set_migration_version(self, version: int) -> None:
        """
        设置迁移版本
        
        Args:
            version: 版本号
        """
        self._execute_sql(
            "INSERT INTO migration_versions (version, applied_at) VALUES (?, ?)",
            (version, datetime.now().isoformat())
        )
    
    def migrate_v001_add_search_columns(self) -> None:
        """
        迁移 v001: 添加 search_title 和 search_author 列到 douban_books 表
        """
        self.logger.info("开始迁移 v001: 添加搜索列")
        
        if not self._table_exists('douban_books'):
            self.logger.warning("douban_books 表不存在，跳过迁移")
            return
        
        # 添加 search_title 列
        if not self._column_exists('douban_books', 'search_title'):
            self._execute_sql("ALTER TABLE douban_books ADD COLUMN search_title VARCHAR(255)")
            self.logger.info("添加 search_title 列成功")
        else:
            self.logger.info("search_title 列已存在，跳过")
        
        # 添加 search_author 列
        if not self._column_exists('douban_books', 'search_author'):
            self._execute_sql("ALTER TABLE douban_books ADD COLUMN search_author VARCHAR(255)")
            self.logger.info("添加 search_author 列成功")
        else:
            self.logger.info("search_author 列已存在，跳过")
        
        self.logger.info("迁移 v001 完成")
    
    def migrate_v002_fix_download_records(self) -> None:
        """
        迁移 v002: 修复 download_records 表结构
        """
        self.logger.info("开始迁移 v002: 修复下载记录表")
        
        if not self._table_exists('download_records'):
            self.logger.warning("download_records 表不存在，跳过迁移")
            return
        
        # 添加缺失的列
        missing_columns = {
            'source': 'VARCHAR(50) DEFAULT "zlibrary"',
            'sync_task_id': 'INTEGER'
        }
        
        for column_name, column_def in missing_columns.items():
            if not self._column_exists('download_records', column_name):
                self._execute_sql(f"ALTER TABLE download_records ADD COLUMN {column_name} {column_def}")
                self.logger.info(f"添加 {column_name} 列成功")
            else:
                self.logger.info(f"{column_name} 列已存在，跳过")
        
        self.logger.info("迁移 v002 完成")
    
    def migrate_v003_create_zlibrary_books(self) -> None:
        """
        迁移 v003: 创建 zlibrary_books 表
        """
        self.logger.info("开始迁移 v003: 创建Z-Library书籍表")
        
        if self._table_exists('zlibrary_books'):
            self.logger.info("zlibrary_books 表已存在，跳过迁移")
            return
        
        create_table_sql = '''
        CREATE TABLE zlibrary_books (
            id INTEGER PRIMARY KEY,
            zlibrary_id VARCHAR(50),
            douban_id VARCHAR(20) NOT NULL,
            title VARCHAR(255) NOT NULL,
            author VARCHAR(255),
            publisher VARCHAR(255),
            year VARCHAR(10),
            language VARCHAR(50),
            isbn VARCHAR(20),
            file_format VARCHAR(10),
            file_size INTEGER,
            download_url VARCHAR(500),
            mirror_url VARCHAR(500),
            quality_score FLOAT,
            download_count INTEGER DEFAULT 0,
            is_available BOOLEAN DEFAULT 1,
            last_checked DATETIME,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(douban_id) REFERENCES douban_books(douban_id)
        )
        '''
        
        self._execute_sql(create_table_sql)
        
        # 创建索引
        indexes = [
            "CREATE INDEX ix_zlibrary_books_zlibrary_id ON zlibrary_books (zlibrary_id)",
            "CREATE INDEX ix_zlibrary_books_douban_id ON zlibrary_books (douban_id)",
            "CREATE INDEX ix_zlibrary_books_title ON zlibrary_books (title)",
            "CREATE INDEX ix_zlibrary_books_author ON zlibrary_books (author)"
        ]
        
        for index_sql in indexes:
            self._execute_sql(index_sql)
        
        self.logger.info("迁移 v003 完成")
    
    def migrate_v004_add_zlib_dl_url(self) -> None:
        """
        迁移 v004: 添加 zlib_dl_url 列到 douban_books 表
        """
        self.logger.info("开始迁移 v004: 添加Z-Library下载URL列")
        
        if not self._table_exists('douban_books'):
            self.logger.warning("douban_books 表不存在，跳过迁移")
            return
        
        # 添加 zlib_dl_url 列
        if not self._column_exists('douban_books', 'zlib_dl_url'):
            self._execute_sql("ALTER TABLE douban_books ADD COLUMN zlib_dl_url VARCHAR(255)")
            self.logger.info("添加 zlib_dl_url 列成功")
        else:
            self.logger.info("zlib_dl_url 列已存在，跳过")
        
        self.logger.info("迁移 v004 完成")
    
    def migrate_v005_create_book_status_history(self) -> None:
        """
        迁移 v005: 创建 book_status_history 表
        """
        self.logger.info("开始迁移 v005: 创建书籍状态历史表")
        
        if self._table_exists('book_status_history'):
            self.logger.info("book_status_history 表已存在，跳过迁移")
            return
        
        create_table_sql = '''
        CREATE TABLE book_status_history (
            id INTEGER PRIMARY KEY,
            book_id INTEGER NOT NULL,
            old_status VARCHAR(16),
            new_status VARCHAR(16) NOT NULL,
            change_reason VARCHAR(255),
            error_message TEXT,
            sync_task_id INTEGER,
            processing_time FLOAT,
            retry_count INTEGER DEFAULT 0,
            created_at DATETIME NOT NULL,
            FOREIGN KEY(book_id) REFERENCES douban_books(id),
            FOREIGN KEY(sync_task_id) REFERENCES sync_tasks(id)
        )
        '''
        
        self._execute_sql(create_table_sql)
        
        # 创建索引
        indexes = [
            "CREATE INDEX ix_book_status_history_book_id ON book_status_history (book_id)",
            "CREATE INDEX ix_book_status_history_old_status ON book_status_history (old_status)",
            "CREATE INDEX ix_book_status_history_new_status ON book_status_history (new_status)",
            "CREATE INDEX ix_book_status_history_created_at ON book_status_history (created_at)"
        ]
        
        for index_sql in indexes:
            self._execute_sql(index_sql)
        
        self.logger.info("迁移 v005 完成")
    
    def run_migrations(self) -> None:
        """
        运行所有未执行的迁移
        """
        self.logger.info("开始运行数据库迁移")
        
        current_version = self._get_migration_version()
        self.logger.info(f"当前数据库版本: {current_version}")
        
        # 定义所有迁移
        migrations = [
            (1, self.migrate_v001_add_search_columns),
            (2, self.migrate_v002_fix_download_records),
            (3, self.migrate_v003_create_zlibrary_books),
            (4, self.migrate_v004_add_zlib_dl_url),
            (5, self.migrate_v005_create_book_status_history),
        ]
        
        for version, migration_func in migrations:
            if version > current_version:
                self.logger.info(f"运行迁移 v{version:03d}")
                try:
                    migration_func()
                    self._set_migration_version(version)
                    self.logger.info(f"迁移 v{version:03d} 完成")
                except Exception as e:
                    self.logger.error(f"迁移 v{version:03d} 失败: {str(e)}")
                    raise
            else:
                self.logger.info(f"迁移 v{version:03d} 已执行，跳过")
        
        final_version = self._get_migration_version()
        self.logger.info(f"迁移完成，当前版本: {final_version}")


def run_migrations(db_path: str) -> None:
    """
    运行数据库迁移
    
    Args:
        db_path: 数据库文件路径
    """
    migration = Migration(db_path)
    migration.run_migrations()


if __name__ == "__main__":
    # 命令行执行迁移
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python migration.py <db_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    run_migrations(db_path)