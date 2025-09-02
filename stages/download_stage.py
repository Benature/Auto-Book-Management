# -*- coding: utf-8 -*-
"""
下载阶段

负责从Z-Library下载书籍文件。
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.pipeline import (BaseStage, NetworkError, ProcessingError,
                           ResourceNotFoundError)
from core.state_manager import BookStateManager
from db.models import (BookStatus, DoubanBook, DownloadQueue, DownloadRecord,
                       ZLibraryBook)
from services.zlibrary_service import ZLibraryService


class DownloadStage(BaseStage):
    """下载处理阶段"""
    
    def __init__(
        self, 
        state_manager: BookStateManager, 
        zlibrary_service: ZLibraryService,
        download_dir: str = "data/downloads"
    ):
        """
        初始化下载阶段
        
        Args:
            state_manager: 状态管理器
            zlibrary_service: Z-Library服务实例
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
        with self.state_manager.get_session() as session:
            # 重新查询数据库获取最新状态，避免使用缓存的book对象
            fresh_book = session.query(DoubanBook).get(book.id)
            if not fresh_book:
                self.logger.warning(f"无法找到书籍: ID {book.id}")
                return False
            
            current_status = fresh_book.status
            self.logger.info(f"检查书籍处理能力: {book.title}, 数据库状态: {current_status.value}, 传入状态: {book.status.value}")
            
            # 检查书籍状态是否符合处理条件
            # 只有DOWNLOAD_QUEUED状态的书籍才能被下载阶段处理
            if current_status != BookStatus.DOWNLOAD_QUEUED:
                self.logger.warning(f"无法处理书籍: {book.title}, 状态: {current_status.value}")
                return False
                
            # 检查下载队列中是否有该书籍的待处理项
            queue_item = session.query(DownloadQueue).filter(
                DownloadQueue.douban_book_id == book.id,
                DownloadQueue.status == 'queued'
            ).first()
            
            has_queued_item = queue_item is not None
            self.logger.info(f"下载队列检查: {book.title}, 队列中有待处理项: {has_queued_item}")
            
            return has_queued_item
    
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
            
            # 从下载队列获取任务
            queue_item_data = self._get_queue_item(book)
            
            if not queue_item_data:
                self.logger.error(f"未找到下载队列项: {book.title}")
                raise ResourceNotFoundError(f"未找到下载队列项: {book.title}")
            
            # 将队列项标记为正在下载
            self._update_queue_status(queue_item_data['queue_id'], 'downloading')
            
            # 执行下载
            file_path = self._download_book(book, queue_item_data)
            
            if not file_path:
                raise ProcessingError(f"下载失败: {book.title}")
            
            # 创建下载记录并更新队列状态
            with self.state_manager.get_session() as session:
                download_record = DownloadRecord(
                    book_id=book.id,
                    zlibrary_id=queue_item_data['zlibrary_id'],
                    file_format=queue_item_data['extension'],
                    file_size=self._get_file_size(file_path),
                    file_path=file_path,
                    download_url=queue_item_data.get('download_url', ''),
                    status="success"
                )
                
                session.add(download_record)
                # session的commit在get_session上下文管理器中自动处理
            
            # 标记队列项为完成
            self._update_queue_status(queue_item_data['queue_id'], 'completed')
            
            self.logger.info(f"成功下载书籍: {book.title}, 路径: {file_path}")
            return True
            
        except ResourceNotFoundError:
            # 资源未找到，不需要重试
            raise
        except Exception as e:
            self.logger.error(f"下载书籍失败: {str(e)}")
            
            # 创建失败的下载记录并更新队列状态
            with self.state_manager.get_session() as session:
                download_record = DownloadRecord(
                    book_id=book.id,
                    status="failed",
                    error_message=str(e)
                )
                session.add(download_record)
                # session的commit在get_session上下文管理器中自动处理
            
            # 标记队列项为失败
            queue_item_data = self._get_queue_item(book)
            if queue_item_data:
                self._update_queue_status(queue_item_data['queue_id'], 'failed', str(e))
            
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
    
    def _get_queue_item(self, book: DoubanBook) -> Optional[Dict[str, Any]]:
        """
        获取下载队列项
        
        Args:
            book: 书籍对象
            
        Returns:
            Optional[Dict[str, Any]]: 队列项数据字典
        """
        with self.state_manager.get_session() as session:
            queue_item = session.query(DownloadQueue).filter(
                DownloadQueue.douban_book_id == book.id,
                DownloadQueue.status.in_(['queued', 'downloading'])
            ).first()
            
            if not queue_item:
                return None
            
            # 获取关联的ZLibraryBook数据
            zlibrary_book = session.query(ZLibraryBook).filter(
                ZLibraryBook.id == queue_item.zlibrary_book_id
            ).first()
            
            if not zlibrary_book:
                return None
            
            return {
                'queue_id': queue_item.id,
                'zlibrary_id': zlibrary_book.zlibrary_id,
                'title': zlibrary_book.title,
                'authors': zlibrary_book.authors,
                'extension': zlibrary_book.extension,
                'size': zlibrary_book.size,
                'url': zlibrary_book.url,
                'download_url': queue_item.download_url,
                'priority': queue_item.priority,
                'status': queue_item.status
            }
    
    def _update_queue_status(self, queue_id: int, status: str, error_message: str = None):
        """
        更新队列项状态
        
        Args:
            queue_id: 队列项ID
            status: 新状态
            error_message: 错误信息（可选）
        """
        with self.state_manager.get_session() as session:
            queue_item = session.query(DownloadQueue).filter(
                DownloadQueue.id == queue_id
            ).first()
            
            if queue_item:
                queue_item.status = status
                if error_message:
                    queue_item.error_message = error_message
                # session的commit在get_session上下文管理器中自动处理
    
    def _download_book(self, book: DoubanBook, queue_item_data: Dict[str, Any]) -> Optional[str]:
        """
        下载书籍文件
        
        Args:
            book: 豆瓣书籍对象  
            queue_item_data: 队列项数据字典
            
        Returns:
            Optional[str]: 下载的文件路径
        """
        try:
            # 构造book_info用于下载
            book_info = {
                'zlibrary_id': queue_item_data['zlibrary_id'],
                'title': queue_item_data['title'] or book.title,
                'authors': queue_item_data['authors'] or book.author,
                'extension': queue_item_data['extension'],
                'douban_id': book.douban_id
            }
            
            # 使用ZLibraryService下载
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