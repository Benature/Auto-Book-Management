# -*- coding: utf-8 -*-
"""
数据库模型

定义 SQLAlchemy ORM 模型。
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey, Float, Boolean
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class BookStatus(enum.Enum):
    """书籍状态枚举"""
    NEW = "new"  # 豆瓣中新发现的书籍
    WITH_DETAIL = "with_detail"  # 已获取详细信息
    MATCHED = "matched"  # 已在 Calibre 中匹配到，结束节点
    SEARCHING = "searching"  # 正在从 Z-Library 搜索
    SEARCH_NOT_FOUND = "search_not_found"  # 未在 Z-Library 找到
    DOWNLOADING = "downloading"  # 正在从 Z-Library 下载
    DOWNLOADED = "downloaded"  # 已从 Z-Library 下载
    UPLOADING = "uploading"  # 正在上传到 Calibre
    UPLOADED = "uploaded"  # 已上传到 Calibre，结束节点


class DoubanBook(Base):
    """豆瓣书籍数据模型"""
    __tablename__ = 'douban_books'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, index=True)
    subtitle = Column(String(255))
    original_title = Column(String(255))
    author = Column(String(255), index=True)
    translator = Column(String(255))
    publisher = Column(String(255))
    publish_date = Column(String(50))
    isbn = Column(String(20), index=True)
    douban_id = Column(String(20), unique=True, index=True)
    douban_url = Column(String(255), unique=True)
    douban_rating = Column(Float)
    cover_url = Column(String(255))
    description = Column(Text)
    search_title = Column(String(255))
    search_author = Column(String(255))
    status = Column(Enum(BookStatus), default=BookStatus.NEW, index=True)
    zlib_dl_url = Column(String(255))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    download_records = relationship("DownloadRecord",
                                    back_populates="book",
                                    cascade="all, delete-orphan")
    zlibrary_books = relationship("ZLibraryBook",
                                  back_populates="douban_book",
                                  cascade="all, delete-orphan")
    status_history = relationship("BookStatusHistory",
                                 back_populates="book",
                                 cascade="all, delete-orphan",
                                 order_by="BookStatusHistory.created_at")

    def __repr__(self):
        return f"<DoubanBook(id={self.id}, title='{self.title}', author='{self.author}', status='{self.status.value if self.status else 'None'}')>"


class DownloadRecord(Base):
    """下载记录数据模型"""
    __tablename__ = 'download_records'

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey('douban_books.id'), nullable=False)
    zlibrary_id = Column(String(50))
    file_format = Column(String(10))  # epub, mobi, pdf 等
    file_size = Column(Integer)  # 文件大小（字节）
    file_path = Column(String(255))  # 本地文件路径
    download_url = Column(String(255))  # Z-Library 下载链接
    calibre_id = Column(Integer)  # Calibre 书库中的 ID
    status = Column(String(20))  # success, failed
    error_message = Column(Text)  # 错误信息
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    book = relationship("DoubanBook", back_populates="download_records")

    def __repr__(self):
        return f"<DownloadRecord(id={self.id}, book_id={self.book_id}, format='{self.file_format}', status='{self.status}')>"


class SyncTask(Base):
    """同步任务数据模型"""
    __tablename__ = 'sync_tasks'

    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime)
    status = Column(String(20))  # running, completed, failed
    books_total = Column(Integer, default=0)
    books_new = Column(Integer, default=0)
    books_matched = Column(Integer, default=0)
    books_downloaded = Column(Integer, default=0)
    books_uploaded = Column(Integer, default=0)
    books_failed = Column(Integer, default=0)
    error_message = Column(Text)

    def __repr__(self):
        return f"<SyncTask(id={self.id}, status='{self.status}', start_time='{self.start_time}')>"


class ZLibraryBook(Base):
    """Z-Library书籍数据模型"""
    __tablename__ = 'zlibrary_books'

    id = Column(Integer, primary_key=True)
    zlibrary_id = Column(String(50), index=True)  # Z-Library中的书籍ID
    douban_id = Column(String(20), ForeignKey('douban_books.douban_id'), nullable=False, index=True)  # 关联豆瓣书籍
    title = Column(String(255), nullable=False, index=True)
    authors = Column(String(500), index=True)  # 作者列表，用;;分隔
    publisher = Column(String(255))
    year = Column(String(10))
    language = Column(String(50))
    isbn = Column(String(20))
    extension = Column(String(10))  # epub, mobi, pdf 等
    size = Column(String(50))  # 文件大小（如 "15.11 MB"）
    url = Column(String(500))  # Z-Library书籍页面链接
    cover = Column(String(500))  # 封面图片链接
    rating = Column(String(10))  # 评分
    quality = Column(String(10))  # 质量评级
    raw_json = Column(Text)  # 原始JSON数据
    download_count = Column(Integer, default=0)  # 下载次数统计
    is_available = Column(Boolean, default=True)  # 是否可用
    last_checked = Column(DateTime)  # 最后检查时间
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    douban_book = relationship("DoubanBook", back_populates="zlibrary_books")

    def __repr__(self):
        return f"<ZLibraryBook(id={self.id}, zlibrary_id='{self.zlibrary_id}', title='{self.title}', format='{self.extension}')>"


class BookStatusHistory(Base):
    """书籍状态变更历史数据模型"""
    __tablename__ = 'book_status_history'

    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey('douban_books.id'), nullable=False, index=True)  # 关联豆瓣书籍
    old_status = Column(Enum(BookStatus), index=True)  # 原状态
    new_status = Column(Enum(BookStatus), nullable=False, index=True)  # 新状态
    change_reason = Column(String(255))  # 状态变更原因
    error_message = Column(Text)  # 错误信息（如果有）
    sync_task_id = Column(Integer, ForeignKey('sync_tasks.id'))  # 关联的同步任务
    processing_time = Column(Float)  # 处理耗时（秒）
    retry_count = Column(Integer, default=0)  # 重试次数
    created_at = Column(DateTime, default=datetime.now, index=True)
    
    # 关联关系
    book = relationship("DoubanBook", back_populates="status_history")
    sync_task = relationship("SyncTask")

    def __repr__(self):
        old_status_str = self.old_status.value if self.old_status else None
        return f"<BookStatusHistory(id={self.id}, book_id={self.book_id}, {old_status_str} -> {self.new_status.value})>"
