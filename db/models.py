# -*- coding: utf-8 -*-

"""
数据库模型

定义 SQLAlchemy ORM 模型。
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class BookStatus(enum.Enum):
    """书籍状态枚举"""
    NEW = "new"  # 新发现的书籍
    MATCHED = "matched"  # 已在 Calibre 中匹配到
    DOWNLOADING = "downloading"  # 正在从 Z-Library 下载
    DOWNLOADED = "downloaded"  # 已从 Z-Library 下载
    UPLOADING = "uploading"  # 正在上传到 Calibre
    UPLOADED = "uploaded"  # 已上传到 Calibre
    FAILED = "failed"  # 处理失败


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
    status = Column(Enum(BookStatus), default=BookStatus.NEW, index=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    download_records = relationship("DownloadRecord", back_populates="book", cascade="all, delete-orphan")
    
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