# -*- coding: utf-8 -*-
"""
下载阶段

负责从Z-Library下载书籍文件。
"""

import os
from typing import Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session

from db.models import BookStatus, DoubanBook, ZLibraryBook, DownloadRecord
from core.pipeline import BaseStage, ProcessingError, NetworkError, ResourceNotFoundError
from core.state_manager import BookStateManager
from services.zlibrary_service_v2 import ZLibraryServiceV2


class DownloadStage(BaseStage):
    """下载处理阶段"""
    
    def __init__(
        self, 
        state_manager: BookStateManager, 
        zlibrary_service: ZLibraryServiceV2,
        download_dir: str = "data/downloads"
    ):
        """
        初始化下载阶段
        
        Args:
            state_manager: 状态管理器
            zlibrary_service: Z-Library V2服务实例
            download_dir: 下载目录
        """
        super().__init__("download", state_manager)
        self.zlibrary_service = zlibrary_service
        self.download_dir = Path(download_dir)
        
        # 确保下载目录存在
        os.makedirs(self.download_dir, exist_ok=True)
    
    def can_process(self, book: DoubanBook) -> bool:
        """
        检查是否可以处理该书籍
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否可以处理
        """
        return book.status in [BookStatus.SEARCH_COMPLETE, BookStatus.DOWNLOAD_QUEUED]
    
    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍 - 下载文件
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        try:
            self.logger.info(f"下载书籍: {book.title}")
            
            # 检查是否已有成功的下载记录
            with self.state_manager.get_session() as session:
                existing_download = session.query(DownloadRecord).filter(
                    DownloadRecord.book_id == book.id,
                    DownloadRecord.status == "success"
                ).first()
            
            if existing_download and existing_download.file_path and os.path.exists(existing_download.file_path):
                self.logger.info(f"书籍已下载: {book.title}, 路径: {existing_download.file_path}")
                return True
            
            # 获取最佳的Z-Library书籍版本
            best_zlibrary_book_data = self._select_best_zlibrary_book(book)
            
            if not best_zlibrary_book_data:
                self.logger.error(f"未找到可用的Z-Library书籍版本: {book.title}")
                raise ResourceNotFoundError(f"未找到可用的Z-Library书籍版本: {book.title}")
            
            # 执行下载
            file_path = self._download_book(book, best_zlibrary_book_data)
            
            if not file_path:
                raise ProcessingError(f"下载失败: {book.title}")
            
            # 创建下载记录
            with self.state_manager.get_session() as session:
                download_record = DownloadRecord(
                    book_id=book.id,
                    zlibrary_id=best_zlibrary_book_data['zlibrary_id'],
                    file_format=best_zlibrary_book_data['extension'],
                    file_size=self._get_file_size(file_path),
                    file_path=file_path,
                    download_url=best_zlibrary_book_data.get('url', ''),
                    status="success"
                )
                
                session.add(download_record)
                # session的commit在get_session上下文管理器中自动处理
            
            self.logger.info(f"成功下载书籍: {book.title}, 路径: {file_path}")
            return True
            
        except ResourceNotFoundError:
            # 资源未找到，不需要重试
            raise
        except Exception as e:
            self.logger.error(f"下载书籍失败: {str(e)}")
            
            # 创建失败的下载记录
            with self.state_manager.get_session() as session:
                download_record = DownloadRecord(
                    book_id=book.id,
                    status="failed",
                    error_message=str(e)
                )
                session.add(download_record)
                # session的commit在get_session上下文管理器中自动处理
            
            # 判断错误类型
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"网络错误: {str(e)}")
            elif "not found" in str(e).lower() or "404" in str(e).lower():
                raise ResourceNotFoundError(f"资源未找到: {str(e)}")
            else:
                raise ProcessingError(f"下载失败: {str(e)}")
    
    def get_next_status(self, success: bool) -> BookStatus:
        """
        获取处理完成后的下一状态
        
        Args:
            success: 处理是否成功
            
        Returns:
            BookStatus: 下一状态
        """
        if success:
            return BookStatus.DOWNLOAD_COMPLETE
        else:
            return BookStatus.DOWNLOAD_FAILED
    
    def _select_best_zlibrary_book(self, book: DoubanBook) -> Optional[Dict[str, Any]]:
        """
        选择最佳的Z-Library书籍版本
        
        Args:
            book: 书籍对象
            
        Returns:
            Optional[Dict[str, Any]]: 最佳书籍版本的数据字典
        """
        # 获取所有可用的版本，并在会话内提取所需数据
        with self.state_manager.get_session() as session:
            zlibrary_books = session.query(ZLibraryBook).filter(
                ZLibraryBook.douban_id == book.douban_id,
                ZLibraryBook.is_available == True
            ).all()
            
            if not zlibrary_books:
                return None
            
            # 在会话内提取所有书籍数据
            books_data = []
            for zlib_book in zlibrary_books:
                book_data = {
                    'id': zlib_book.id,
                    'zlibrary_id': zlib_book.zlibrary_id,
                    'title': zlib_book.title,
                    'authors': zlib_book.authors,
                    'extension': zlib_book.extension,
                    'size': zlib_book.size,
                    'url': zlib_book.url,
                    'download_url': zlib_book.download_url,
                    'match_score': zlib_book.match_score,
                    'douban_id': zlib_book.douban_id,
                    'is_available': zlib_book.is_available
                }
                books_data.append(book_data)
        
        # 格式优先级（假设从配置获取）
        format_priority = ['epub', 'mobi', 'pdf', 'azw3', 'txt']
        
        # 按格式优先级排序
        for preferred_format in format_priority:
            for book_data in books_data:
                if book_data['extension'] and book_data['extension'].lower() == preferred_format.lower():
                    self.logger.info(f"选择格式 {preferred_format}: {book_data['title']}")
                    return book_data
        
        # 如果没有匹配的优先格式，返回第一个
        self.logger.warning(f"未找到优先格式，使用默认: {books_data[0]['extension']}")
        return books_data[0]
    
    def _download_book(self, book: DoubanBook, zlibrary_book_data: Dict[str, Any]) -> Optional[str]:
        """
        下载书籍文件
        
        Args:
            book: 豆瓣书籍对象
            zlibrary_book_data: Z-Library书籍数据字典
            
        Returns:
            Optional[str]: 下载的文件路径
        """
        try:
            # 构造book_info用于下载
            book_info = {
                'zlibrary_id': zlibrary_book_data['zlibrary_id'],
                'title': zlibrary_book_data['title'] or book.title,
                'authors': zlibrary_book_data['authors'] or book.author,
                'extension': zlibrary_book_data['extension'],
                'douban_id': book.douban_id
            }
            
            # 使用ZLibraryServiceV2下载
            file_path = self.zlibrary_service.download_book(book_info, str(self.download_dir))
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"下载书籍文件失败: {str(e)}")
            raise
    
    def _get_file_size(self, file_path: str) -> int:
        """
        获取文件大小
        
        Args:
            file_path: 文件路径
            
        Returns:
            int: 文件大小（字节）
        """
        try:
            return os.path.getsize(file_path)
        except Exception:
            return 0