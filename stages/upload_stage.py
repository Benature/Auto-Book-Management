# -*- coding: utf-8 -*-
"""
上传阶段

负责将下载的书籍文件上传到Calibre。
"""

import os
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.pipeline import AuthError, BaseStage, NetworkError, ProcessingError
from core.state_manager import BookStateManager
from db.models import BookStatus, DoubanBook, DownloadRecord
from services.calibre_service import CalibreService


class UploadStage(BaseStage):
    """上传处理阶段"""
    
    def __init__(
        self, 
        state_manager: BookStateManager, 
        calibre_service: CalibreService
    ):
        """
        初始化上传阶段
        
        Args:
            state_manager: 状态管理器
            calibre_service: Calibre服务实例
        """
        super().__init__("upload", state_manager)
        self.calibre_service = calibre_service
    
    def can_process(self, book: DoubanBook) -> bool:
        """
        检查是否可以处理该书籍
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否可以处理
        """
        return book.status in [BookStatus.DOWNLOAD_COMPLETE, BookStatus.UPLOAD_QUEUED]
    
    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍 - 上传到Calibre
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        try:
            self.logger.info(f"上传书籍到Calibre: {book.title}")
            
            # 检查Calibre中是否已存在该书籍
            existing_book = self._check_book_exists_in_calibre(book)
            if existing_book:
                self.logger.info(f"书籍已存在于Calibre中: {book.title}")
                return True
            
            # 获取下载记录信息
            download_info = self._get_download_record_info(book)
            if not download_info:
                self.logger.error(f"未找到成功的下载记录: {book.title}")
                raise ProcessingError(f"未找到成功的下载记录: {book.title}", retryable=False)
            
            # 验证文件存在
            if not os.path.exists(download_info['file_path']):
                self.logger.error(f"下载文件不存在: {download_info['file_path']}")
                raise ProcessingError(f"下载文件不存在: {download_info['file_path']}", retryable=False)
            
            # 准备元数据
            metadata = self._prepare_metadata_from_info(book, download_info)
            
            # 上传到Calibre
            calibre_id = self.calibre_service.upload_book(
                file_path=download_info['file_path'],
                metadata=metadata
            )
            
            if not calibre_id:
                raise ProcessingError(f"Calibre上传失败: {book.title}")
            
            # 更新下载记录
            with self.state_manager.get_session() as session:
                # 在新会话中重新获取下载记录对象
                record = session.query(DownloadRecord).get(download_info['id'])
                if record:
                    record.calibre_id = calibre_id
                    session.commit()
            
            self.logger.info(f"成功上传到Calibre: {book.title}, Calibre ID: {calibre_id}")
            return True
            
        except ProcessingError:
            # 重新抛出ProcessingError
            raise
        except Exception as e:
            self.logger.error(f"上传书籍失败: {str(e)}")
            
            # 判断错误类型
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"网络错误: {str(e)}")
            elif "auth" in str(e).lower() or "unauthorized" in str(e).lower():
                raise AuthError(f"认证错误: {str(e)}")
            else:
                raise ProcessingError(f"上传失败: {str(e)}")
    
    def get_next_status(self, success: bool) -> BookStatus:
        """
        获取处理完成后的下一状态
        
        Args:
            success: 处理是否成功
            
        Returns:
            BookStatus: 下一状态
        """
        if success:
            return BookStatus.UPLOAD_COMPLETE
        else:
            return BookStatus.UPLOAD_FAILED
    
    def _check_book_exists_in_calibre(self, book: DoubanBook) -> Optional[Dict[str, Any]]:
        """
        检查书籍是否已存在于Calibre中
        
        Args:
            book: 书籍对象
            
        Returns:
            Optional[Dict[str, Any]]: 存在的书籍信息，不存在则返回None
        """
        try:
            return self.calibre_service.find_best_match(
                title=book.title,
                author=book.author,
                isbn=book.isbn
            )
        except Exception as e:
            self.logger.warning(f"检查Calibre中书籍存在性时出错: {str(e)}")
            return None
    
    def _get_successful_download_record_id(self, book: DoubanBook) -> Optional[int]:
        """
        获取成功的下载记录ID
        
        Args:
            book: 书籍对象
            
        Returns:
            Optional[int]: 成功的下载记录ID
        """
        with self.state_manager.get_session() as session:
            record = session.query(DownloadRecord).filter(
                DownloadRecord.book_id == book.id,
                DownloadRecord.status == "success",
                DownloadRecord.file_path.isnot(None)
            ).order_by(DownloadRecord.created_at.desc()).first()
            
            return record.id if record else None
    
    def _get_download_record_info(self, book: DoubanBook) -> Optional[Dict[str, Any]]:
        """
        获取成功的下载记录信息（不返回对象）
        
        Args:
            book: 书籍对象
            
        Returns:
            Optional[Dict[str, Any]]: 下载记录信息
        """
        with self.state_manager.get_session() as session:
            record = session.query(DownloadRecord).filter(
                DownloadRecord.book_id == book.id,
                DownloadRecord.status == "success",
                DownloadRecord.file_path.isnot(None)
            ).order_by(DownloadRecord.created_at.desc()).first()
            
            if record:
                return {
                    'id': record.id,
                    'file_path': record.file_path,
                    'file_format': record.file_format,
                    'file_size': record.file_size
                }
            return None
    
    def _prepare_metadata_from_info(self, book: DoubanBook, download_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        从下载信息准备上传用的元数据
        
        Args:
            book: 书籍对象
            download_info: 下载记录信息字典
            
        Returns:
            Dict[str, Any]: 元数据字典
        """
        metadata = {
            'title': book.title,
            'authors': [book.author] if book.author else [],
            'isbn': book.isbn,
            'publisher': book.publisher,
            'pubdate': book.publish_date,
            'tags': ['豆瓣', 'Z-Library'],
            'comments': book.description,
            'rating': book.douban_rating
        }
        
        # 添加原标题和副标题
        if book.original_title:
            metadata['title_sort'] = book.original_title
        
        if book.subtitle:
            metadata['title'] = f"{book.title}: {book.subtitle}"
        
        # 添加封面URL（如果有）
        if book.cover_url:
            metadata['cover_url'] = book.cover_url
        
        # 添加豆瓣相关信息
        metadata['identifiers'] = {
            'douban': book.douban_id
        }
        
        if book.isbn:
            metadata['identifiers']['isbn'] = book.isbn
        
        return metadata

    def _prepare_metadata(self, book: DoubanBook, download_record: DownloadRecord) -> Dict[str, Any]:
        """
        准备上传用的元数据
        
        Args:
            book: 书籍对象
            download_record: 下载记录
            
        Returns:
            Dict[str, Any]: 元数据字典
        """
        metadata = {
            'title': book.title,
            'authors': [book.author] if book.author else [],
            'isbn': book.isbn,
            'publisher': book.publisher,
            'pubdate': book.publish_date,
            'tags': ['豆瓣', 'Z-Library'],
            'comments': book.description,
            'rating': book.douban_rating
        }
        
        # 添加原标题和副标题
        if book.original_title:
            metadata['title_sort'] = book.original_title
        
        if book.subtitle:
            metadata['title'] = f"{book.title}: {book.subtitle}"
        
        # 添加封面URL（如果有）
        if book.cover_url:
            metadata['cover_url'] = book.cover_url
        
        # 添加豆瓣相关信息
        metadata['identifiers'] = {
            'douban': book.douban_id
        }
        
        if book.isbn:
            metadata['identifiers']['isbn'] = book.isbn
        
        return metadata