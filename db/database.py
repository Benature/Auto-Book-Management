# -*- coding: utf-8 -*-
"""
数据库操作

提供数据库连接和操作接口。
"""

from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError
from contextlib import contextmanager
from typing import List, Optional, Dict, Any, Generator, Tuple
import logging

from .models import Base, DoubanBook, DownloadRecord, SyncTask, BookStatus
from utils.logger import get_logger


class Database:
    """数据库操作类"""

    def __init__(self, db_url: str):
        """
        初始化数据库
        
        Args:
            db_url: 数据库连接 URL
        """
        self.logger = get_logger("database")
        self.engine = create_engine(db_url)
        self.Session = scoped_session(sessionmaker(bind=self.engine))

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

    # SyncTask 相关操作
    def create_sync_task(self) -> SyncTask:
        """
        创建同步任务
        
        Returns:
            SyncTask: 创建的同步任务对象
        """
        with self.session_scope() as session:
            task = SyncTask(status="running")
            session.add(task)
            session.flush()
            self.logger.info(f"创建同步任务: ID {task.id}")
            return task

    def update_sync_task(self, task_id: int, task_data: Dict[str,
                                                             Any]) -> None:
        """
        更新同步任务
        
        Args:
            task_id: 同步任务 ID
            task_data: 同步任务数据字典
        """
        with self.session_scope() as session:
            task = session.query(SyncTask).filter(
                SyncTask.id == task_id).first()
            if task:
                for key, value in task_data.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                self.logger.info(f"更新同步任务: ID {task.id}, 状态 {task.status}")
            else:
                self.logger.warning(f"尝试更新不存在的同步任务: ID {task_id}")

    def get_latest_sync_task(self) -> Optional[SyncTask]:
        """
        获取最新的同步任务
        
        Returns:
            Optional[SyncTask]: 同步任务对象，如果不存在则返回 None
        """
        with self.session_scope() as session:
            return session.query(SyncTask).order_by(desc(SyncTask.id)).first()

    def get_sync_task_stats(self) -> Dict[str, int]:
        """
        获取同步任务统计信息
        
        Returns:
            Dict[str, int]: 统计信息字典
        """
        with self.session_scope() as session:
            stats = {
                "total":
                session.query(DoubanBook).count(),
                "new":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.NEW).count(),
                "matched":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.MATCHED).count(),
                "downloading":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.DOWNLOADING).count(),
                "downloaded":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.DOWNLOADED).count(),
                "uploading":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.UPLOADING).count(),
                "uploaded":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.UPLOADED).count(),
                "failed":
                session.query(DoubanBook).filter(
                    DoubanBook.status == BookStatus.FAILED).count(),
            }
            return stats
