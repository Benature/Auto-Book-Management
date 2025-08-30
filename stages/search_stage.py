# -*- coding: utf-8 -*-
"""
搜索阶段

负责在Z-Library中搜索书籍并保存结果。
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session

from db.models import BookStatus, DoubanBook, ZLibraryBook, DownloadQueue
from core.pipeline import BaseStage, ProcessingError, NetworkError, ResourceNotFoundError
from core.state_manager import BookStateManager
from services.zlibrary_service_v2 import ZLibraryServiceV2


class SearchStage(BaseStage):
    """搜索处理阶段"""

    def __init__(self, state_manager: BookStateManager,
                 zlibrary_service: ZLibraryServiceV2):
        """
        初始化搜索阶段
        
        Args:
            state_manager: 状态管理器
            zlibrary_service: Z-Library服务实例
        """
        super().__init__("search", state_manager)
        self.zlibrary_service = zlibrary_service

    def can_process(self, book: DoubanBook) -> bool:
        """
        检查是否可以处理该书籍，并进行必要的状态预处理
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否可以处理
        """
        return True
        # 如果是DETAIL_COMPLETE状态，先转换为SEARCH_QUEUED
        if book.status == BookStatus.DETAIL_COMPLETE:
            self.state_manager.transition_status(book.id,
                                                 BookStatus.SEARCH_QUEUED,
                                                 "准备开始搜索")
            # 刷新book对象状态
            book.status = BookStatus.SEARCH_QUEUED

        return book.status == BookStatus.SEARCH_QUEUED

    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍 - 搜索Z-Library
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        try:
            self.logger.info(f"搜索Z-Library: {book.title}")

            # 检查是否已有搜索结果
            with self.state_manager.get_session() as session:
                existing_results = session.query(ZLibraryBook).filter(
                    ZLibraryBook.douban_id == book.douban_id).count()

                if existing_results > 0:
                    self.logger.info(f"书籍已有Z-Library搜索结果: {book.title}")
                    return True

            # 执行搜索
            search_results = self.zlibrary_service.search_books(
                title=book.search_title or book.title,
                author=book.search_author or book.author,
                isbn=book.isbn)

            if not search_results:
                self.logger.warning(f"Z-Library未找到匹配书籍: {book.title}")
                raise ResourceNotFoundError(f"Z-Library未找到匹配书籍: {book.title}")

            # 保存搜索结果到数据库
            saved_count = self._save_search_results(book, search_results)

            if saved_count == 0:
                self.logger.warning(f"未能保存任何搜索结果: {book.title}")
                raise ProcessingError(f"未能保存搜索结果: {book.title}")

            self.logger.info(f"成功搜索并保存 {saved_count} 个结果: {book.title}")
            return True

        except ResourceNotFoundError:
            # 资源未找到，不需要重试
            raise
        except NetworkError as e:
            # 网络错误（包括连接重置），将状态回退到SEARCH_QUEUED以便重试
            error_msg = str(e)
            if "连接重置错误" in error_msg or "Connection reset by peer" in error_msg:
                self.logger.warning(
                    f"连接重置错误，将书籍状态回退到SEARCH_QUEUED: {book.title}")
                # 回退状态到SEARCH_QUEUED
                self.state_manager.transition_status(
                    book.id, BookStatus.SEARCH_QUEUED,
                    f"连接重置错误，回退状态重新排队: {error_msg}")
                # 不抛出异常，让pipeline继续处理其他书籍
                return False
            else:
                # 其他网络错误正常处理
                raise
        except Exception as e:
            self.logger.error(f"搜索书籍失败: {str(e)}")
            # 判断错误类型
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"网络错误: {str(e)}")
            elif "login" in str(e).lower() or "auth" in str(e).lower():
                raise ProcessingError(f"认证错误: {str(e)}",
                                      "auth",
                                      retryable=False)
            else:
                raise ProcessingError(f"搜索失败: {str(e)}")

    def get_next_status(self, success: bool) -> BookStatus:
        """
        获取处理完成后的下一状态
        
        Args:
            success: 处理是否成功
            
        Returns:
            BookStatus: 下一状态
        """
        if success:
            return BookStatus.SEARCH_COMPLETE
        else:
            return BookStatus.SEARCH_NO_RESULTS

    def _save_search_results(self, book: DoubanBook,
                             search_results: List[Dict[str, Any]]) -> int:
        """
        保存搜索结果到数据库
        
        Args:
            book: 书籍对象
            search_results: 搜索结果列表
            
        Returns:
            int: 保存的记录数量
        """
        saved_count = 0

        try:
            with self.state_manager.get_session() as session:
                for result in search_results:
                    # 检查是否已存在
                    existing = session.query(ZLibraryBook).filter(
                        ZLibraryBook.zlibrary_id == result.get('zlibrary_id'),
                        ZLibraryBook.douban_id == book.douban_id).first()

                    if existing:
                        continue

                    # 计算匹配度得分
                    douban_info = {
                        'title': book.title or '',
                        'author': book.author or '',
                        'publisher': book.publisher or '',
                        'publish_date': book.publish_date or '',
                        'isbn': book.isbn or ''
                    }
                    match_score = self.zlibrary_service.calculate_match_score(
                        douban_info, result)

                    # 创建Z-Library书籍记录（包含新字段）
                    zlibrary_book = ZLibraryBook(
                        zlibrary_id=result.get('zlibrary_id', ''),
                        douban_id=book.douban_id,
                        title=result.get('title', ''),
                        authors=result.get('authors', ''),
                        publisher=result.get('publisher', ''),
                        year=result.get('year', ''),
                        edition=result.get('edition', ''),
                        language=result.get('language', ''),
                        isbn=result.get('isbn', ''),
                        extension=result.get('extension', ''),
                        size=result.get('size', ''),
                        url=result.get('url', ''),
                        cover=result.get('cover', ''),
                        description=result.get('description', ''),
                        categories=result.get('categories', ''),
                        categories_url=result.get('categories_url', ''),
                        download_url=result.get('download_url', ''),
                        rating=result.get('rating', ''),
                        quality=result.get('quality', ''),
                        match_score=match_score,
                        raw_json=result.get('raw_json', '{}'),
                        is_available=True)

                    session.add(zlibrary_book)
                    saved_count += 1

                # session的commit在get_session上下文管理器中自动处理
                if saved_count > 0:
                    self.logger.info(f"保存了 {saved_count} 个Z-Library搜索结果")

                    # 为当前豆瓣书籍选择匹配度最高的Z-Library书籍并添加到下载队列
                    self._add_best_match_to_download_queue(book, session)

            return saved_count

        except Exception as e:
            self.logger.error(f"保存搜索结果失败: {str(e)}")
            return 0

    def _add_best_match_to_download_queue(self, book: DoubanBook,
                                          session: Session):
        """
        为豆瓣书籍选择匹配度最高的Z-Library书籍并添加到下载队列
        
        Args:
            book: 豆瓣书籍对象
            session: 数据库会话
        """
        try:
            # 获取该豆瓣书籍的所有Z-Library搜索结果，按匹配度降序排列
            best_match = session.query(ZLibraryBook).filter(
                ZLibraryBook.douban_id == book.douban_id,
                ZLibraryBook.download_url != '',  # 确保有下载链接
                ZLibraryBook.download_url.is_not(None)).order_by(
                    ZLibraryBook.match_score.desc()).first()

            if not best_match:
                self.logger.warning(f"未找到有效的Z-Library下载链接: {book.title}")
                return

            # 检查下载队列中是否已存在该豆瓣书籍
            existing_queue_item = session.query(DownloadQueue).filter(
                DownloadQueue.douban_book_id == book.id).first()

            if existing_queue_item:
                # 如果已存在，检查是否需要更新为更高匹配度的结果
                existing_zlibrary_book = session.query(ZLibraryBook).filter(
                    ZLibraryBook.id ==
                    existing_queue_item.zlibrary_book_id).first()

                if existing_zlibrary_book and best_match.match_score > existing_zlibrary_book.match_score:
                    # 更新为更好的匹配结果
                    existing_queue_item.zlibrary_book_id = best_match.id
                    existing_queue_item.download_url = best_match.download_url
                    self.logger.info(
                        f"更新下载队列中的最佳匹配: {book.title} (得分: {best_match.match_score:.3f})"
                    )
                else:
                    self.logger.debug(f"下载队列中已有更好或相同的匹配: {book.title}")
            else:
                # 创建新的下载队列项
                download_queue_item = DownloadQueue(
                    douban_book_id=book.id,
                    zlibrary_book_id=best_match.id,
                    download_url=best_match.download_url,
                    priority=self._calculate_download_priority(best_match),
                    status='queued')

                session.add(download_queue_item)
                self.logger.info(
                    f"添加到下载队列: {book.title} -> {best_match.title} (得分: {best_match.match_score:.3f}, 格式: {best_match.extension})"
                )

        except Exception as e:
            self.logger.error(f"添加到下载队列失败: {str(e)}")

    def _calculate_download_priority(self, zlibrary_book: ZLibraryBook) -> int:
        """
        计算下载优先级
        
        Args:
            zlibrary_book: Z-Library书籍对象
            
        Returns:
            int: 优先级数值，越高越优先
        """
        priority = 0

        # 基础匹配度优先级 (0-100)
        priority += int(zlibrary_book.match_score * 100)

        # 文件格式优先级
        format_priority = {
            'epub': 50,
            'mobi': 40,
            'azw3': 35,
            'pdf': 20,
            'djvu': 10
        }
        priority += format_priority.get(zlibrary_book.extension.lower(), 0)

        # 文件质量优先级
        if zlibrary_book.quality:
            quality_priority = {'high': 30, 'medium': 20, 'low': 10}
            priority += quality_priority.get(zlibrary_book.quality.lower(), 0)

        return priority
