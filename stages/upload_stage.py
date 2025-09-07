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
        with self.state_manager.get_session() as session:
            # 重新查询数据库获取最新状态，避免使用缓存的book对象
            fresh_book = session.query(DoubanBook).get(book.id)
            if not fresh_book:
                self.logger.warning(f"无法找到书籍: ID {book.id}")
                return False
            
            current_status = fresh_book.status
            
            # 接受DOWNLOAD_COMPLETE、UPLOAD_QUEUED和UPLOAD_ACTIVE状态的书籍
            can_process = current_status in [BookStatus.DOWNLOAD_COMPLETE, BookStatus.UPLOAD_QUEUED, BookStatus.UPLOAD_ACTIVE]
            self.logger.info(f"处理书籍: {book.title}, 数据库状态: {current_status.value}, 传入状态: {book.status.value}, 可处理: {can_process}")
            
            # 如果状态不符合处理条件，记录警告
            if not can_process:
                self.logger.warning(f"无法处理书籍: {book.title}, 状态: {current_status.value}")
            
            return can_process

    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍 - 上传到Calibre

        Args:
            book: 书籍对象

        Returns:
            bool: 处理是否成功
        """
        # 先检查是否可以处理这本书籍
        if not self.can_process(book):
            raise ProcessingError(f"无法处理书籍: {book.title}, 状态不匹配")
        
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
                raise ProcessingError(
                    f"未找到成功的下载记录: {book.title}", retryable=False)

            # 验证文件存在
            if not os.path.exists(download_info['file_path']):
                self.logger.error(
                    f"下载文件不存在: {download_info['file_path']}")
                raise ProcessingError(
                    f"下载文件不存在: {download_info['file_path']}",
                    retryable=False)

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
                record = session.query(DownloadRecord).get(
                    download_info['id'])
                if record:
                    record.calibre_id = calibre_id
                    session.commit()

            # 检查并更新 Calibre 的 ISBN（如果 Calibre 的 ISBN 为空）
            self._update_isbn_to_calibre(book, calibre_id, metadata)

            self.logger.info(
                f"成功上传到Calibre: {book.title}, Calibre ID: {calibre_id}")
            return True

        except ProcessingError:
            # 重新抛出ProcessingError
            raise
        except Exception as e:
            self.logger.error(f"上传书籍失败: {str(e)}")
            
            # 特殊处理：如果是状态不匹配错误（can_process返回False导致的），直接跳过
            if "状态不匹配" in str(e):
                self.logger.warning(f"书籍状态不符合上传阶段处理条件，跳过: {book.title}")
                raise ProcessingError(f"状态不匹配: {str(e)}", retryable=False)
            # 判断错误类型
            elif "timeout" in str(e).lower() or "connection" in str(e).lower():
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

    def _check_book_exists_in_calibre(self, book: DoubanBook) -> Optional[
            Dict[str, Any]]:
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

    def _get_successful_download_record_id(self, book: DoubanBook) -> Optional[
            int]:
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

    def _get_download_record_info(self, book: DoubanBook) -> Optional[
            Dict[str, Any]]:
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

    def _prepare_metadata_from_info(self, book: DoubanBook,
                                    download_info: Dict[str, Any]) -> Dict[
                                        str, Any]:
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

    def _update_isbn_to_calibre(self, book: DoubanBook, calibre_id: int,
                                metadata: Dict[str, Any]) -> None:
        """
        检查并更新 Calibre 的 ISBN 信息（仅单向：豆瓣 -> Calibre）

        Args:
            book: 豆瓣书籍对象
            calibre_id: Calibre 书籍 ID
            metadata: 上传时使用的元数据
        """
        try:
            # 检查豆瓣书籍是否有 ISBN
            douban_isbn = book.isbn.strip() if book.isbn else None
            if not douban_isbn:
                # 豆瓣没有 ISBN，不做任何操作
                self.logger.debug(f"豆瓣书籍没有 ISBN，跳过更新: {book.title}")
                return

            # 从 Calibre 获取书籍信息
            book_info = self.calibre_service.get_book_info(calibre_id)
            if not book_info:
                self.logger.warning(
                    f"无法从 Calibre 获取书籍信息: {calibre_id}")
                return

            # 获取 Calibre 的 ISBN 信息
            calibre_isbn = self._extract_calibre_isbn(book_info)

            # 只在 Calibre 没有 ISBN 时才更新
            if not calibre_isbn:
                success = self._update_calibre_isbn(calibre_id, douban_isbn)
                if success:
                    self.logger.info(
                        f"已将豆瓣 ISBN 填写到 Calibre: "
                        f"{book.title} (ISBN: {douban_isbn})")
                else:
                    self.logger.warning(
                        f"更新 Calibre ISBN 失败: {book.title}")
            else:
                # Calibre 已有 ISBN，检查是否一致
                if calibre_isbn == douban_isbn:
                    self.logger.debug(
                        f"豆瓣和Calibre的ISBN一致: {book.title} (ISBN: {douban_isbn})")
                else:
                    self.logger.info(
                        f"Calibre已有不同的ISBN，保持不变: {book.title} "
                        f"(豆瓣: {douban_isbn}, Calibre: {calibre_isbn})")

        except Exception as e:
            self.logger.error(f"更新 Calibre ISBN 时出错: {str(e)}")

    def _extract_calibre_isbn(self, book_info: Dict[str, Any]) -> Optional[str]:
        """
        从 Calibre 书籍信息中提取 ISBN

        Args:
            book_info: Calibre 书籍信息

        Returns:
            Optional[str]: 提取到的 ISBN，没有则返回 None
        """
        # 先检查 isbn 字段
        if book_info.get('isbn'):
            isbn = str(book_info['isbn']).strip()
            if isbn:
                return isbn

        # 如果没有，检查 identifiers 中的 isbn
        if book_info.get('identifiers'):
            identifiers = book_info['identifiers']
            if isinstance(identifiers, dict) and identifiers.get('isbn'):
                isbn = str(identifiers['isbn']).strip()
                if isbn:
                    return isbn

        return None

    def _update_calibre_isbn(self, calibre_id: int, isbn: str) -> bool:
        """
        更新 Calibre 中书籍的 ISBN

        Args:
            calibre_id: Calibre 书籍 ID
            isbn: 要设置的 ISBN

        Returns:
            bool: 更新是否成功
        """
        try:
            # 使用 calibredb set_metadata 命令更新 ISBN
            return self.calibre_service.update_book_isbn(calibre_id, isbn)
        except Exception as e:
            self.logger.error(f"更新 Calibre ISBN 失败: {str(e)}")
            return False

