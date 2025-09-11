# -*- coding: utf-8 -*-
"""
数据库操作

提供数据库连接和操作接口。
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from sqlalchemy import create_engine, desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import scoped_session, sessionmaker

from utils.logger import get_logger

from .models import (Base, BookStatus, BookStatusHistory, DoubanBook,
                     DownloadRecord, ZLibraryBook)


class Database:
    """数据库操作类"""

    def __init__(self, config_manager):
        """
        初始化数据库
        
        Args:
            config_manager: 配置管理器实例
        """
        # 根据配置生成数据库URL
        db_config = config_manager.get_database_config()
        if db_config.get('type') == 'sqlite':
            self.db_url = f"sqlite:///{db_config.get('path', 'data/douban_books.db')}"
        elif db_config.get('type') == 'postgresql':
            self.db_url = f"postgresql://{db_config.get('username')}:{db_config.get('password')}@{db_config.get('host')}:{db_config.get('port')}/{db_config.get('database')}"
        else:
            # 默认使用SQLite
            self.db_url = "sqlite:///data/douban_books.db"
        
        self.logger = get_logger("database")
        self.engine = create_engine(self.db_url)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        # 为新架构提供session_factory
        self.session_factory = sessionmaker(bind=self.engine)

    def _initialize_database(self):
        """
        初始化数据库，如果数据库文件不存在则创建并初始化表结构。
        """
        db_path = Path(self.db_url.replace("sqlite:///", "")).resolve()
        self.logger.info(f"数据库路径解析为: {db_path.as_posix()}")
        if not db_path.exists():
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS sync_tasks (
                                id INTEGER PRIMARY KEY,
                                start_time TEXT NOT NULL,
                                end_time TEXT,
                                status TEXT NOT NULL,
                                books_total INTEGER,
                                books_new INTEGER,
                                books_matched INTEGER,
                                books_downloaded INTEGER,
                                books_uploaded INTEGER,
                                books_failed INTEGER,
                                error_message TEXT
                            )''')
            conn.commit()
            conn.close()

    def init_db(self) -> None:
        """
        初始化数据库，创建所有表
        """
        self.logger.info("初始化数据库...")
        Base.metadata.create_all(self.engine)
        self.logger.info("数据库初始化完成")

    @contextmanager
    def session_scope(self) -> Generator:
        """
        提供事务会话上下文
        
        Yields:
            session: SQLAlchemy 会话对象
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"数据库操作失败: {str(e)}")
            raise
        finally:
            session.close()

    # DoubanBook 相关操作
    def add_book(self, book_data: Dict[str, Any]) -> DoubanBook:
        """
        添加豆瓣书籍
        
        Args:
            book_data: 书籍数据字典
            
        Returns:
            DoubanBook: 添加的书籍对象
        """
        with self.session_scope() as session:
            book = DoubanBook(**book_data)
            session.add(book)
            session.flush()
            self.logger.info(f"添加书籍: {book.title} (ID: {book.id})")
            return book

    def get_book_by_douban_id(self, douban_id: str) -> Optional[DoubanBook]:
        """
        根据豆瓣 ID 获取书籍
        
        Args:
            douban_id: 豆瓣书籍 ID
            
        Returns:
            Optional[DoubanBook]: 书籍对象，如果不存在则返回 None
        """
        with self.session_scope() as session:
            return session.query(DoubanBook).filter(
                DoubanBook.douban_id == douban_id).first()

    def get_book_by_isbn(self, isbn: str) -> Optional[DoubanBook]:
        """
        根据 ISBN 获取书籍
        
        Args:
            isbn: 书籍 ISBN
            
        Returns:
            Optional[DoubanBook]: 书籍对象，如果不存在则返回 None
        """
        with self.session_scope() as session:
            return session.query(DoubanBook).filter(
                DoubanBook.isbn == isbn).first()

    def get_book_by_douban_id(self, douban_id: str) -> Optional[DoubanBook]:
        """
        根据豆瓣 ID 获取书籍
        
        Args:
            douban_id: 豆瓣书籍 ID
            
        Returns:
            Optional[DoubanBook]: 书籍对象，如果不存在则返回 None
        """
        with self.session_scope() as session:
            return session.query(DoubanBook).filter(
                DoubanBook.douban_id == douban_id).first()

    def get_book_by_title_author(self, title: str,
                                 author: str) -> Optional[DoubanBook]:
        """
        根据标题和作者获取书籍
        
        Args:
            title: 书籍标题
            author: 作者名称
            
        Returns:
            Optional[DoubanBook]: 书籍对象，如果不存在则返回 None
        """
        with self.session_scope() as session:
            return session.query(DoubanBook).filter(
                DoubanBook.title == title,
                DoubanBook.author == author).first()

    def get_books_by_status(self, status: BookStatus) -> List[DoubanBook]:
        """
        根据状态获取书籍列表
        
        Args:
            status: 书籍状态
            
        Returns:
            List[DoubanBook]: 书籍对象列表
        """
        with self.session_scope() as session:
            return session.query(DoubanBook).filter(
                DoubanBook.status == status).all()

    def update_book_status(self, book_id: int, status: BookStatus) -> None:
        """
        更新书籍状态
        
        Args:
            book_id: 书籍 ID
            status: 新状态
        """
        with self.session_scope() as session:
            book = session.query(DoubanBook).filter(
                DoubanBook.id == book_id).first()
            if book:
                old_status = book.status
                book.status = status
                self.logger.info(
                    f"更新书籍状态: {book.title} (ID: {book.id}) {old_status.value if old_status else 'None'} -> {status.value}"
                )
            else:
                self.logger.warning(f"尝试更新不存在的书籍状态: ID {book_id}")

    def update_book(self, book_id: int, book_data: Dict[str, Any]) -> None:
        """
        更新书籍信息
        
        Args:
            book_id: 书籍 ID
            book_data: 书籍数据字典
        """
        with self.session_scope() as session:
            book = session.query(DoubanBook).filter(
                DoubanBook.id == book_id).first()
            if book:
                for key, value in book_data.items():
                    if hasattr(book, key):
                        setattr(book, key, value)
                self.logger.info(f"更新书籍信息: {book.title} (ID: {book.id})")
            else:
                self.logger.warning(f"尝试更新不存在的书籍: ID {book_id}")

    # DownloadRecord 相关操作
    def add_download_record(self, record_data: Dict[str,
                                                    Any]) -> DownloadRecord:
        """
        添加下载记录
        
        Args:
            record_data: 下载记录数据字典
            
        Returns:
            DownloadRecord: 添加的下载记录对象
        """
        with self.session_scope() as session:
            record = DownloadRecord(**record_data)
            session.add(record)
            session.flush()
            self.logger.info(
                f"添加下载记录: 书籍 ID {record.book_id}, 格式 {record.file_format} (ID: {record.id})"
            )
            return record

    def get_download_records_by_book_id(self,
                                        book_id: int) -> List[DownloadRecord]:
        """
        根据书籍 ID 获取下载记录
        
        Args:
            book_id: 书籍 ID
            
        Returns:
            List[DownloadRecord]: 下载记录对象列表
        """
        with self.session_scope() as session:
            return session.query(DownloadRecord).filter(
                DownloadRecord.book_id == book_id).all()

    def update_download_record(self, record_id: int,
                               record_data: Dict[str, Any]) -> None:
        """
        更新下载记录
        
        Args:
            record_id: 下载记录 ID
            record_data: 下载记录数据字典
        """
        with self.session_scope() as session:
            record = session.query(DownloadRecord).filter(
                DownloadRecord.id == record_id).first()
            if record:
                for key, value in record_data.items():
                    if hasattr(record, key):
                        setattr(record, key, value)
                self.logger.info(
                    f"更新下载记录: ID {record.id}, 书籍 ID {record.book_id}")
            else:
                self.logger.warning(f"尝试更新不存在的下载记录: ID {record_id}")


    # ZLibraryBook 相关操作
    def add_zlibrary_book(self, book_data: Dict[str, Any]) -> ZLibraryBook:
        """
        添加Z-Library书籍记录
        
        Args:
            book_data: Z-Library书籍数据字典
            
        Returns:
            ZLibraryBook: 添加的Z-Library书籍对象
        """
        with self.session_scope() as session:
            zlibrary_book = ZLibraryBook(**book_data)
            session.add(zlibrary_book)
            session.flush()
            self.logger.info(f"添加Z-Library书籍: {zlibrary_book.title} (ID: {zlibrary_book.id})")
            return zlibrary_book

    def get_zlibrary_books_by_douban_id(self, douban_id: str) -> List[ZLibraryBook]:
        """
        根据豆瓣ID获取Z-Library书籍列表
        
        Args:
            douban_id: 豆瓣书籍ID
            
        Returns:
            List[ZLibraryBook]: Z-Library书籍对象列表
        """
        with self.session_scope() as session:
            return session.query(ZLibraryBook).filter(
                ZLibraryBook.douban_id == douban_id).all()

    def get_zlibrary_book_by_id(self, zlibrary_id: str, douban_id: str = None) -> Optional[ZLibraryBook]:
        """
        根据Z-Library ID获取书籍记录
        
        Args:
            zlibrary_id: Z-Library书籍ID
            douban_id: 豆瓣书籍ID (可选，用于进一步筛选)
            
        Returns:
            Optional[ZLibraryBook]: Z-Library书籍对象，如果不存在则返回 None
        """
        with self.session_scope() as session:
            query = session.query(ZLibraryBook).filter(
                ZLibraryBook.zlibrary_id == zlibrary_id)
            if douban_id:
                query = query.filter(ZLibraryBook.douban_id == douban_id)
            return query.first()

    def update_zlibrary_book(self, book_id: int, book_data: Dict[str, Any]) -> None:
        """
        更新Z-Library书籍信息
        
        Args:
            book_id: Z-Library书籍ID
            book_data: 书籍数据字典
        """
        with self.session_scope() as session:
            book = session.query(ZLibraryBook).filter(
                ZLibraryBook.id == book_id).first()
            if book:
                for key, value in book_data.items():
                    if hasattr(book, key):
                        setattr(book, key, value)
                self.logger.info(f"更新Z-Library书籍信息: {book.title} (ID: {book.id})")
            else:
                self.logger.warning(f"尝试更新不存在的Z-Library书籍: ID {book_id}")

    def get_best_zlibrary_book(self, douban_id: str, format_priority: List[str] = None) -> Optional[ZLibraryBook]:
        """
        根据优先级获取最佳的Z-Library书籍
        
        Args:
            douban_id: 豆瓣书籍ID
            format_priority: 格式优先级列表，例如 ['epub', 'mobi', 'pdf']
            
        Returns:
            Optional[ZLibraryBook]: 最佳匹配的Z-Library书籍对象
        """
        with self.session_scope() as session:
            books = session.query(ZLibraryBook).filter(
                ZLibraryBook.douban_id == douban_id,
                ZLibraryBook.is_available == True
            ).all()
            
            if not books:
                return None
            
            # 如果有格式优先级，按优先级排序
            if format_priority:
                def format_priority_score(book):
                    try:
                        return format_priority.index(book.file_format.lower())
                    except (ValueError, AttributeError):
                        return len(format_priority)  # 未知格式排在最后
                
                books.sort(key=format_priority_score)
            
            # 按质量评分排序（如果有的话）
            books.sort(key=lambda x: x.quality_score or 0, reverse=True)
            
            return books[0]

    # BookStatusHistory 相关操作
    def add_status_history(self, book_id: int, old_status: Optional[BookStatus], 
                          new_status: BookStatus, change_reason: str = None, 
                          error_message: str = None, 
                          processing_time: float = None, retry_count: int = 0) -> BookStatusHistory:
        """
        添加状态变更历史记录
        
        Args:
            book_id: 书籍ID
            old_status: 原状态
            new_status: 新状态
            change_reason: 变更原因
            error_message: 错误信息
            processing_time: 处理耗时
            retry_count: 重试次数
            
        Returns:
            BookStatusHistory: 创建的历史记录对象
        """
        with self.session_scope() as session:
            history = BookStatusHistory(
                book_id=book_id,
                old_status=old_status,
                new_status=new_status,
                change_reason=change_reason,
                error_message=error_message,
                processing_time=processing_time,
                retry_count=retry_count
            )
            session.add(history)
            session.flush()
            self.logger.info(f"添加状态历史: 书籍{book_id} {old_status.value if old_status else 'None'} -> {new_status.value}")
            return history

    def update_book_status_with_history(self, book_id: int, new_status: BookStatus, 
                                       change_reason: str = None, error_message: str = None, 
                                       processing_time: float = None, 
                                       retry_count: int = 0) -> None:
        """
        更新书籍状态并记录历史
        
        Args:
            book_id: 书籍ID
            new_status: 新状态
            change_reason: 变更原因
            error_message: 错误信息
            processing_time: 处理耗时
            retry_count: 重试次数
        """
        with self.session_scope() as session:
            book = session.query(DoubanBook).filter(DoubanBook.id == book_id).first()
            if book:
                old_status = book.status
                book.status = new_status
                
                # 创建历史记录
                history = BookStatusHistory(
                    book_id=book_id,
                    old_status=old_status,
                    new_status=new_status,
                    change_reason=change_reason,
                    error_message=error_message,
                    processing_time=processing_time,
                    retry_count=retry_count
                )
                session.add(history)
                
                self.logger.info(f"更新书籍状态: {book.title} (ID: {book.id}) {old_status.value if old_status else 'None'} -> {new_status.value}")
            else:
                self.logger.warning(f"尝试更新不存在的书籍状态: ID {book_id}")

    def get_book_status_history(self, book_id: int) -> List[BookStatusHistory]:
        """
        获取书籍的状态历史
        
        Args:
            book_id: 书籍ID
            
        Returns:
            List[BookStatusHistory]: 状态历史列表
        """
        with self.session_scope() as session:
            return session.query(BookStatusHistory).filter(
                BookStatusHistory.book_id == book_id
            ).order_by(BookStatusHistory.created_at).all()

    def get_status_statistics(self) -> Dict[str, Any]:
        """
        获取状态统计信息
        
        Returns:
            Dict[str, Any]: 状态统计数据
        """
        with self.session_scope() as session:
            # 当前状态分布
            current_status = {}
            for status in BookStatus:
                count = session.query(DoubanBook).filter(DoubanBook.status == status).count()
                current_status[status.value] = count
            
            # 今日状态变更统计
            from datetime import datetime, timedelta
            today = datetime.now().date()
            today_changes = session.query(BookStatusHistory).filter(
                BookStatusHistory.created_at >= datetime.combine(today, datetime.min.time())
            ).count()
            
            # 失败状态的书籍（带错误信息）
            failed_books = session.query(BookStatusHistory).filter(
                BookStatusHistory.new_status == BookStatus.SEARCH_NOT_FOUND,
                BookStatusHistory.error_message.isnot(None)
            ).count()
            
            return {
                'current_status': current_status,
                'today_changes': today_changes,
                'failed_books': failed_books,
                'total_books': session.query(DoubanBook).count()
            }
