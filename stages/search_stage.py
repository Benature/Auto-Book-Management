# -*- coding: utf-8 -*-
"""
搜索阶段

负责在Z-Library中搜索书籍并保存结果。
"""

from typing import Any, Dict, List

from core.pipeline import (BaseStage, NetworkError, ProcessingError,
                           ResourceNotFoundError)
from core.state_manager import BookStateManager
from db.models import BookStatus, DoubanBook, DownloadQueue, ZLibraryBook
from services.zlibrary_service import ZLibraryService
from services.calibre_service import CalibreService


class SearchStage(BaseStage):
    """搜索处理阶段"""

    def __init__(self, state_manager: BookStateManager,
                 zlibrary_service: ZLibraryService,
                 calibre_service: CalibreService,
                 min_match_score: float = 0.6):
        """
        初始化搜索阶段
        
        Args:
            state_manager: 状态管理器
            zlibrary_service: Z-Library服务实例
            calibre_service: Calibre服务实例
            min_match_score: 最低匹配分数阈值
        """
        super().__init__("search", state_manager)
        self.zlibrary_service = zlibrary_service
        self.calibre_service = calibre_service
        self.min_match_score = min_match_score
        # 跟踪当前处理是否找到符合阈值的结果
        self._found_qualifying_results = False
        # 跟踪当前处理是否在Calibre中已存在
        self._calibre_exists = False

    def can_process(self, book: DoubanBook) -> bool:
        """
        检查是否可以处理该书籍
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否可以处理
        """
        # 接受DETAIL_COMPLETE和SEARCH_QUEUED状态的书籍
        can_process = book.status in [BookStatus.DETAIL_COMPLETE, BookStatus.SEARCH_QUEUED]
        self.logger.info(f"处理书籍: {book.title}, 状态: {book.status}, 可处理: {can_process}")
        return can_process

    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍 - 先检查Calibre，再搜索Z-Library
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        # 重置标志位
        self._found_qualifying_results = False
        self._calibre_exists = False
        
        try:
            # 首先检查Calibre中是否已存在
            self.logger.info(f"检查Calibre中是否存在: {book.title}")
            calibre_match = self.calibre_service.find_best_match(
                title=book.title,
                author=book.author,
                isbn=book.isbn
            )
            
            if calibre_match:
                self.logger.info(f"书籍在Calibre中已存在: {book.title}, ID: {calibre_match.get('calibre_id')}")
                self._calibre_exists = True
                return True
            
            self.logger.info(f"Calibre中未找到，开始搜索Z-Library: {book.title}")

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
            
            # 检查是否有符合阈值的结果并成功添加到下载队列
            queue_added = self._add_best_match_to_queue(book)
            
            # 设置标志位，用于决定下一状态
            self._found_qualifying_results = queue_added
            
            if not queue_added:
                self.logger.warning(f"没有符合最低匹配分数({self.min_match_score})的搜索结果: {book.title}")
            
            # 始终返回True，让任务调度器认为处理成功
            # 实际的下一状态由get_next_status根据_found_qualifying_results决定
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
            # 如果在Calibre中已存在，直接跳过
            if self._calibre_exists:
                return BookStatus.SKIPPED_EXISTS
            # 根据是否找到符合阈值的结果决定状态
            elif self._found_qualifying_results:
                return BookStatus.SEARCH_COMPLETE
            else:
                return BookStatus.SEARCH_NO_RESULTS
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
                    zlibrary_id = result.get('zlibrary_id', '')
                    if not zlibrary_id:
                        self.logger.warning(f"搜索结果缺少zlibrary_id，跳过: {result.get('title', 'Unknown')}")
                        continue
                    
                    # 检查是否已存在
                    existing = session.query(ZLibraryBook).filter(
                        ZLibraryBook.zlibrary_id == zlibrary_id,
                        ZLibraryBook.douban_id == book.douban_id).first()

                    if existing:
                        self.logger.debug(f"Z-Library书籍已存在，跳过: {zlibrary_id} for {book.douban_id}")
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

            return saved_count

        except Exception as e:
            self.logger.error(f"保存搜索结果失败: {str(e)}")
            return 0

    def _add_best_match_to_queue(self, book: DoubanBook) -> bool:
        """
        选择最佳匹配结果并添加到下载队列
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否成功添加到队列
        """
        try:
            with self.state_manager.get_session() as session:
                # 检查是否已在下载队列中
                existing_queue_item = session.query(DownloadQueue).filter(
                    DownloadQueue.douban_book_id == book.id).first()
                
                if existing_queue_item:
                    self.logger.info(f"书籍已在下载队列中: {book.title}")
                    return True
                
                # 获取所有搜索结果，按匹配分数降序排列
                zlibrary_books = session.query(ZLibraryBook).filter(
                    ZLibraryBook.douban_id == book.douban_id,
                    ZLibraryBook.is_available.is_(True),
                    ZLibraryBook.match_score >= self.min_match_score
                ).order_by(ZLibraryBook.match_score.desc()).all()
                
                if not zlibrary_books:
                    self.logger.warning(f"未找到符合最低匹配分数({self.min_match_score})的结果: {book.title}")
                    return False
                
                # 选择最佳匹配（最高分数）
                best_match = zlibrary_books[0]
                
                # 考虑格式优先级进行微调
                format_priority = {'epub': 3, 'mobi': 2, 'pdf': 1, 'azw3': 2, 'txt': 0}
                best_candidate = best_match
                
                # 如果有多个高分结果（分差小于0.1），选择格式更优的
                for zlib_book in zlibrary_books[:3]:  # 只考虑前3个结果
                    if (best_match.match_score - zlib_book.match_score) <= 0.1:
                        current_format_score = format_priority.get(zlib_book.extension.lower() if zlib_book.extension else '', 0)
                        best_format_score = format_priority.get(best_candidate.extension.lower() if best_candidate.extension else '', 0)
                        
                        if current_format_score > best_format_score:
                            best_candidate = zlib_book
                
                # 创建下载队列项
                queue_item = DownloadQueue(
                    douban_book_id=book.id,
                    zlibrary_book_id=best_candidate.id,
                    download_url=best_candidate.download_url or best_candidate.url,
                    priority=int(best_candidate.match_score * 100),  # 将匹配分数转为优先级
                    status='queued'
                )
                
                session.add(queue_item)
                # session的commit在get_session上下文管理器中自动处理
                
                self.logger.info(f"添加最佳匹配到下载队列: {book.title}, "
                               f"匹配分数: {best_candidate.match_score:.3f}, "
                               f"格式: {best_candidate.extension}")
                return True
                
        except Exception as e:
            self.logger.error(f"添加到下载队列失败: {str(e)}")
            return False
