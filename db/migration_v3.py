# -*- coding: utf-8 -*-
"""
数据库迁移脚本 V3

添加新的Z-Library书籍字段和下载队列表
"""

import sys
import os
import traceback
from pathlib import Path
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from db.models import Base, ZLibraryBook, DownloadQueue
from db.database import Database
from config.config_manager import ConfigManager
from utils.logger import get_logger

logger = get_logger("migration_v3")


class DatabaseMigrationV3:
    """数据库迁移V3 - 支持新的Z-Library字段和下载队列"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.db = Database(config_manager)
        self.engine = self.db.engine
        self.session_factory = sessionmaker(bind=self.engine)
        self.inspector = inspect(self.engine)
        
    def check_current_schema(self):
        """检查当前数据库模式"""
        logger.info("检查当前数据库模式...")
        
        tables = self.inspector.get_table_names()
        logger.info(f"现有表: {tables}")
        
        # 检查zlibrary_books表的字段
        if 'zlibrary_books' in tables:
            columns = self.inspector.get_columns('zlibrary_books')
            column_names = [col['name'] for col in columns]
            logger.info(f"zlibrary_books表现有字段: {column_names}")
            
            # 检查是否需要添加新字段
            new_fields = ['edition', 'description', 'categories', 'categories_url', 'download_url', 'match_score']
            missing_fields = [field for field in new_fields if field not in column_names]
            if missing_fields:
                logger.warning(f"zlibrary_books表缺少字段: {missing_fields}")
            else:
                logger.info("zlibrary_books表字段完整")
        
        # 检查download_queue表是否存在
        if 'download_queue' not in tables:
            logger.warning("download_queue表不存在，需要创建")
        else:
            logger.info("download_queue表已存在")
    
    def migrate_zlibrary_books_table(self):
        """迁移zlibrary_books表，添加新字段"""
        logger.info("开始迁移zlibrary_books表...")
        
        try:
            with self.engine.connect() as conn:
                # 检查表是否存在
                if not self.inspector.has_table('zlibrary_books'):
                    logger.warning("zlibrary_books表不存在，跳过迁移")
                    return
                
                # 获取现有字段
                columns = self.inspector.get_columns('zlibrary_books')
                column_names = [col['name'] for col in columns]
                
                # 需要添加的新字段
                new_columns = [
                    ("edition", "TEXT"),
                    ("description", "TEXT"),  
                    ("categories", "TEXT"),
                    ("categories_url", "TEXT"),
                    ("download_url", "TEXT"),
                    ("match_score", "REAL DEFAULT 0.0")
                ]
                
                # 添加缺少的字段
                for col_name, col_type in new_columns:
                    if col_name not in column_names:
                        logger.info(f"添加字段: {col_name}")
                        sql = f"ALTER TABLE zlibrary_books ADD COLUMN {col_name} {col_type};"
                        conn.execute(text(sql))
                        conn.commit()
                
                # 为match_score字段创建索引
                if 'match_score' not in column_names:
                    logger.info("为match_score字段创建索引")
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_zlibrary_books_match_score ON zlibrary_books (match_score);"))
                    conn.commit()
                
                logger.info("zlibrary_books表迁移完成")
                
        except Exception as e:
            logger.error(f"迁移zlibrary_books表失败: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
    
    def create_download_queue_table(self):
        """创建下载队列表"""
        logger.info("创建download_queue表...")
        
        try:
            # 检查表是否已存在
            if self.inspector.has_table('download_queue'):
                logger.info("download_queue表已存在，跳过创建")
                return
            
            # 创建表的SQL
            create_table_sql = """
            CREATE TABLE download_queue (
                id INTEGER PRIMARY KEY,
                douban_book_id INTEGER NOT NULL UNIQUE,
                zlibrary_book_id INTEGER NOT NULL,
                download_url VARCHAR(500) NOT NULL,
                priority INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'queued',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (douban_book_id) REFERENCES douban_books(id),
                FOREIGN KEY (zlibrary_book_id) REFERENCES zlibrary_books(id)
            );
            """
            
            # 创建索引的SQL
            indexes_sql = [
                "CREATE INDEX ix_download_queue_douban_book_id ON download_queue (douban_book_id);",
                "CREATE INDEX ix_download_queue_zlibrary_book_id ON download_queue (zlibrary_book_id);", 
                "CREATE INDEX ix_download_queue_priority ON download_queue (priority);",
                "CREATE INDEX ix_download_queue_status ON download_queue (status);",
                "CREATE INDEX ix_download_queue_created_at ON download_queue (created_at);"
            ]
            
            with self.engine.connect() as conn:
                # 创建表
                conn.execute(text(create_table_sql))
                conn.commit()
                logger.info("download_queue表创建成功")
                
                # 创建索引
                for index_sql in indexes_sql:
                    conn.execute(text(index_sql))
                    conn.commit()
                logger.info("download_queue表索引创建完成")
                
        except Exception as e:
            logger.error(f"创建download_queue表失败: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
    
    def update_existing_match_scores(self):
        """为现有的Z-Library书籍更新匹配度得分"""
        logger.info("为现有Z-Library书籍计算匹配度得分...")
        
        try:
            from services.zlibrary_service_v2 import ZLibrarySearchService
            from db.models import DoubanBook
            
            # 创建ZLibrary搜索服务实例
            zlibrary_service = ZLibrarySearchService(self.config_manager)
            
            with self.session_factory() as session:
                # 获取所有match_score为0的记录
                zlibrary_books = session.query(ZLibraryBook).filter(
                    ZLibraryBook.match_score == 0.0
                ).all()
                
                updated_count = 0
                
                for zlib_book in zlibrary_books:
                    try:
                        # 获取对应的豆瓣书籍信息
                        douban_book = session.query(DoubanBook).filter(
                            DoubanBook.douban_id == zlib_book.douban_id
                        ).first()
                        
                        if not douban_book:
                            continue
                        
                        # 构建豆瓣书籍信息字典
                        douban_info = {
                            'title': douban_book.title or '',
                            'author': douban_book.author or '',
                            'publisher': douban_book.publisher or '',
                            'publish_date': douban_book.publish_date or '',
                            'isbn': douban_book.isbn or ''
                        }
                        
                        # 构建Z-Library书籍信息字典
                        zlib_info = {
                            'title': zlib_book.title or '',
                            'authors': zlib_book.authors or '',
                            'publisher': zlib_book.publisher or '',
                            'year': zlib_book.year or '',
                            'isbn': zlib_book.isbn or ''
                        }
                        
                        # 计算匹配度
                        match_score = zlibrary_service.calculate_match_score(douban_info, zlib_info)
                        zlib_book.match_score = match_score
                        updated_count += 1
                        
                        if updated_count % 50 == 0:
                            logger.info(f"已更新 {updated_count} 条记录的匹配度...")
                        
                    except Exception as e:
                        logger.error(f"更新记录 {zlib_book.id} 匹配度失败: {str(e)}")
                        continue
                
                session.commit()
                logger.info(f"匹配度更新完成，共更新 {updated_count} 条记录")
                
        except Exception as e:
            logger.error(f"更新匹配度得分失败: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            # 不抛出异常，因为这不是关键步骤
    
    def create_best_match_download_queue(self):
        """为现有书籍创建最佳匹配的下载队列"""
        logger.info("为现有书籍创建最佳匹配下载队列...")
        
        try:
            from db.models import DoubanBook
            
            with self.session_factory() as session:
                # 获取所有已完成搜索的豆瓣书籍
                douban_books = session.query(DoubanBook).filter(
                    DoubanBook.status.in_(['search_complete', 'download_queued', 'download_active', 'download_complete'])
                ).all()
                
                created_count = 0
                
                for book in douban_books:
                    try:
                        # 检查是否已存在下载队列项
                        existing = session.query(DownloadQueue).filter(
                            DownloadQueue.douban_book_id == book.id
                        ).first()
                        
                        if existing:
                            continue
                        
                        # 获取该书最佳匹配的Z-Library书籍
                        best_match = session.query(ZLibraryBook).filter(
                            ZLibraryBook.douban_id == book.douban_id,
                            ZLibraryBook.download_url != '',
                            ZLibraryBook.download_url.is_not(None)
                        ).order_by(ZLibraryBook.match_score.desc()).first()
                        
                        if not best_match:
                            continue
                        
                        # 计算优先级
                        priority = int(best_match.match_score * 100)
                        
                        # 文件格式优先级
                        format_priority = {
                            'epub': 50, 'mobi': 40, 'azw3': 35, 
                            'pdf': 20, 'djvu': 10
                        }
                        priority += format_priority.get(best_match.extension.lower(), 0)
                        
                        # 创建下载队列项
                        queue_item = DownloadQueue(
                            douban_book_id=book.id,
                            zlibrary_book_id=best_match.id,
                            download_url=best_match.download_url,
                            priority=priority,
                            status='queued'
                        )
                        
                        session.add(queue_item)
                        created_count += 1
                        
                        if created_count % 20 == 0:
                            logger.info(f"已创建 {created_count} 个下载队列项...")
                            
                    except Exception as e:
                        logger.error(f"为书籍 {book.id} 创建下载队列失败: {str(e)}")
                        continue
                
                session.commit()
                logger.info(f"下载队列创建完成，共创建 {created_count} 个项目")
                
        except Exception as e:
            logger.error(f"创建下载队列失败: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            # 不抛出异常，因为这不是关键步骤
    
    def run_migration(self):
        """执行完整的数据库迁移"""
        logger.info("开始执行数据库迁移V3...")
        
        try:
            # 1. 检查当前模式
            self.check_current_schema()
            
            # 2. 迁移zlibrary_books表
            self.migrate_zlibrary_books_table()
            
            # 3. 创建download_queue表
            self.create_download_queue_table()
            
            # 4. 更新现有记录的匹配度得分
            self.update_existing_match_scores()
            
            # 5. 为现有书籍创建下载队列
            self.create_best_match_download_queue()
            
            logger.info("数据库迁移V3完成!")
            
        except Exception as e:
            logger.error(f"数据库迁移失败: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
    
    def rollback_migration(self):
        """回滚迁移（仅用于开发测试）"""
        logger.warning("开始回滚数据库迁移...")
        
        try:
            with self.engine.connect() as conn:
                # 删除新添加的字段（仅SQLite不直接支持，需要重建表）
                logger.warning("SQLite不支持直接删除字段，请手动处理或重建数据库")
                
                # 删除download_queue表
                if self.inspector.has_table('download_queue'):
                    conn.execute(text("DROP TABLE download_queue;"))
                    conn.commit()
                    logger.info("已删除download_queue表")
                
        except Exception as e:
            logger.error(f"回滚迁移失败: {str(e)}")
            raise


def main():
    """主函数"""
    try:
        # 加载配置
        config_path = Path(__file__).parent.parent / "config.yaml"
        config_manager = ConfigManager(str(config_path))
        
        # 创建迁移实例
        migration = DatabaseMigrationV3(config_manager)
        
        # 执行迁移
        migration.run_migration()
        
        print("数据库迁移V3执行成功!")
        
    except Exception as e:
        print(f"迁移执行失败: {str(e)}")
        logger.error(f"迁移执行失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()