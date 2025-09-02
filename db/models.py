# -*- coding: utf-8 -*-
"""
数据库模型

定义 SQLAlchemy ORM 模型。
"""

import enum
from datetime import datetime

from sqlalchemy import (JSON, Boolean, Column, DateTime, Enum, Float,
                        ForeignKey, Integer, String, Text)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class BookStatus(enum.Enum):
    """书籍状态枚举 - 重构为分阶段pipeline架构"""
    # 数据收集阶段
    NEW = "new"                           # 豆瓣新发现
    DETAIL_FETCHING = "detail_fetching"   # 获取详情中
    DETAIL_COMPLETE = "detail_complete"   # 详情完成
    
    # 搜索阶段  
    SEARCH_QUEUED = "search_queued"       # 排队搜索
    SEARCH_ACTIVE = "search_active"       # 搜索中
    SEARCH_COMPLETE = "search_complete"   # 搜索完成有结果
    SEARCH_NO_RESULTS = "search_no_results"  # 搜索无结果
    
    # 下载阶段
    DOWNLOAD_QUEUED = "download_queued"   # 排队下载
    DOWNLOAD_ACTIVE = "download_active"   # 下载中
    DOWNLOAD_COMPLETE = "download_complete"  # 下载完成
    DOWNLOAD_FAILED = "download_failed"   # 下载失败
    
    # 上传阶段
    UPLOAD_QUEUED = "upload_queued"       # 排队上传
    UPLOAD_ACTIVE = "upload_active"       # 上传中
    UPLOAD_COMPLETE = "upload_complete"   # 上传完成
    UPLOAD_FAILED = "upload_failed"       # 上传失败
    
    # 终态
    COMPLETED = "completed"               # 成功完成
    SKIPPED_EXISTS = "skipped_exists"     # 已存在跳过
    FAILED_PERMANENT = "failed_permanent" # 永久失败


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
    edition = Column(String(50))  # 版次信息
    language = Column(String(50))
    isbn = Column(String(20))
    extension = Column(String(10))  # epub, mobi, pdf 等
    size = Column(String(50))  # 文件大小（如 "15.11 MB"）
    url = Column(String(500))  # Z-Library书籍页面链接
    cover = Column(String(500))  # 封面图片链接
    description = Column(Text)  # 书籍描述信息
    categories = Column(String(255))  # 分类信息
    categories_url = Column(String(500))  # 分类链接
    download_url = Column(String(500))  # 下载链接
    rating = Column(String(10))  # 评分
    quality = Column(String(10))  # 质量评级
    match_score = Column(Float, default=0.0, index=True)  # 匹配度得分(0.0-1.0)
    raw_json = Column(Text)  # 原始JSON数据
    download_count = Column(Integer, default=0)  # 下载次数统计
    is_available = Column(Boolean, default=True)  # 是否可用
    last_checked = Column(DateTime)  # 最后检查时间
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    douban_book = relationship("DoubanBook", back_populates="zlibrary_books")

    def __repr__(self):
        return f"<ZLibraryBook(id={self.id}, zlibrary_id='{self.zlibrary_id}', title='{self.title}', format='{self.extension}', score={self.match_score})>"


class DownloadQueue(Base):
    """下载队列数据模型 - 存储匹配度最高的待下载书籍"""
    __tablename__ = 'download_queue'

    id = Column(Integer, primary_key=True)
    douban_book_id = Column(Integer, ForeignKey('douban_books.id'), nullable=False, unique=True, index=True)  # 每本豆瓣书只能有一个最佳匹配
    zlibrary_book_id = Column(Integer, ForeignKey('zlibrary_books.id'), nullable=False, index=True)  # 关联最佳匹配的Z-Library书籍
    download_url = Column(String(500), nullable=False)  # 直接下载链接
    priority = Column(Integer, default=0, index=True)  # 下载优先级，数字越大越优先
    status = Column(String(20), default='queued', index=True)  # queued, downloading, completed, failed
    error_message = Column(Text)  # 错误信息
    retry_count = Column(Integer, default=0)  # 重试次数
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    douban_book = relationship("DoubanBook")
    zlibrary_book = relationship("ZLibraryBook")

    def __repr__(self):
        return f"<DownloadQueue(id={self.id}, douban_book_id={self.douban_book_id}, status='{self.status}', priority={self.priority})>"


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


class ProcessingTask(Base):
    """处理任务数据模型 - 支持Pipeline架构"""
    __tablename__ = 'processing_tasks'
    
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey('douban_books.id'), nullable=False, index=True)
    stage = Column(String(50), nullable=False, index=True)  # data_collection, search, download, upload, cleanup
    status = Column(String(50), nullable=False, index=True)  # queued, active, completed, failed, skipped
    priority = Column(Integer, default=0, index=True)  # 优先级，数字越大优先级越高
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text)
    error_type = Column(String(100))  # network, auth, resource_not_found, system, etc.
    task_data = Column(JSON)  # 任务相关的额外数据
    assigned_worker = Column(String(100))  # 分配的工作进程ID
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    next_retry_at = Column(DateTime)  # 下次重试时间
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    book = relationship("DoubanBook")
    
    def __repr__(self):
        return f"<ProcessingTask(id={self.id}, book_id={self.book_id}, stage='{self.stage}', status='{self.status}')>"


class SystemConfig(Base):
    """系统配置数据模型"""
    __tablename__ = 'system_config'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text)
    value_type = Column(String(50), default='string')  # string, int, float, bool, json
    description = Column(Text)
    category = Column(String(50), index=True)  # pipeline, service, notification, etc.
    is_sensitive = Column(Boolean, default=False)  # 是否为敏感信息（如密码）
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<SystemConfig(key='{self.key}', category='{self.category}')>"


class WorkerStatus(Base):
    """工作进程状态数据模型"""
    __tablename__ = 'worker_status'
    
    id = Column(Integer, primary_key=True)
    worker_id = Column(String(100), unique=True, nullable=False, index=True)
    worker_type = Column(String(50), nullable=False, index=True)  # douban_scraper, zlibrary_service, calibre_service
    status = Column(String(50), nullable=False, index=True)  # idle, busy, error, offline
    current_task_id = Column(Integer, ForeignKey('processing_tasks.id'))
    last_heartbeat = Column(DateTime, index=True)
    error_message = Column(Text)
    worker_info = Column(JSON)  # 工作进程的额外信息
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    current_task = relationship("ProcessingTask")
    
    def __repr__(self):
        return f"<WorkerStatus(worker_id='{self.worker_id}', type='{self.worker_type}', status='{self.status}')>"
