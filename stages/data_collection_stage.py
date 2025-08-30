# -*- coding: utf-8 -*-
"""
数据收集阶段

负责从豆瓣获取书籍详细信息。
"""

import time
import random
from typing import Dict, Any
from sqlalchemy.orm import Session

from db.models import BookStatus, DoubanBook
from core.pipeline import BaseStage, ProcessingError, NetworkError, AuthError
from core.state_manager import BookStateManager
from scrapers.douban_scraper import DoubanScraper, DoubanAccessDeniedException


class DataCollectionStage(BaseStage):
    """数据收集处理阶段"""
    
    def __init__(self, state_manager: BookStateManager, douban_scraper: DoubanScraper):
        """
        初始化数据收集阶段
        
        Args:
            state_manager: 状态管理器
            douban_scraper: 豆瓣爬虫实例
        """
        super().__init__("data_collection", state_manager)
        self.douban_scraper = douban_scraper
    
    def can_process(self, book: DoubanBook) -> bool:
        """
        检查是否可以处理该书籍
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 是否可以处理
        """
        return book.status == BookStatus.NEW
    
    def process(self, book: DoubanBook) -> bool:
        """
        处理书籍 - 获取详细信息
        
        Args:
            book: 书籍对象
            
        Returns:
            bool: 处理是否成功
        """
        try:
            self.logger.info(f"获取书籍详细信息: {book.title}")
            
            # 检查是否已有足够的基本信息
            if book.isbn and book.douban_url:
                self.logger.info(f"书籍已有基本信息，跳过详细信息获取: {book.title}")
                return True
            
            # 获取详细信息
            if not book.douban_url:
                self.logger.error(f"书籍缺少豆瓣URL: {book.title}")
                raise ProcessingError("书籍缺少豆瓣URL", "data_missing", retryable=False)
            
            # 豆瓣请求前添加3-5秒随机延迟，避免被限制
            delay = random.uniform(3.0, 5.0)
            self.logger.info(f"豆瓣请求延迟 {delay:.2f} 秒")
            time.sleep(delay)
            
            detail_info = self.douban_scraper.get_book_detail(book.douban_url)
            
            if not detail_info:
                self.logger.warning(f"未获取到书籍详细信息: {book.title}")
                # 这种情况下仍然可以继续后续流程
                return True
            
            # 更新书籍信息
            if detail_info.get('isbn'):
                book.isbn = detail_info['isbn']
            if detail_info.get('original_title'):
                book.original_title = detail_info['original_title']
            if detail_info.get('subtitle'):
                book.subtitle = detail_info['subtitle']
            if detail_info.get('description'):
                book.description = detail_info['description']
            
            # 生成搜索用的标题和作者
            book.search_title = self._prepare_search_title(book)
            book.search_author = self._prepare_search_author(book)
            
            # 使用状态管理器的会话处理提交
            
            self.logger.info(f"成功获取书籍详细信息: {book.title}")
            return True
            
        except DoubanAccessDeniedException as e:
            self.logger.warning(f"豆瓣访问被拒绝，跳过详细信息获取: {str(e)}")
            # 豆瓣403错误时，跳过详细信息获取但仍然准备搜索信息，以便进行Z-Library搜索
            book.search_title = self._prepare_search_title(book)
            book.search_author = self._prepare_search_author(book)
            self.logger.info(f"已准备搜索信息，跳过详细信息获取: {book.title}")
            return True
            
        except Exception as e:
            self.logger.error(f"获取书籍详细信息失败: {str(e)}")
            # 判断是否为网络错误
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                raise NetworkError(f"网络错误: {str(e)}")
            else:
                raise ProcessingError(f"获取详细信息失败: {str(e)}")
    
    def get_next_status(self, success: bool) -> BookStatus:
        """
        获取处理完成后的下一状态
        
        Args:
            success: 处理是否成功
            
        Returns:
            BookStatus: 下一状态
        """
        if success:
            return BookStatus.DETAIL_COMPLETE
        else:
            return BookStatus.FAILED_PERMANENT
    
    def _prepare_search_title(self, book: DoubanBook) -> str:
        """
        准备搜索用的标题
        
        Args:
            book: 书籍对象
            
        Returns:
            str: 搜索标题
        """
        title = book.title or ""
        
        # 移除常见的标点符号和括号内容
        import re
        
        # 移除括号及其内容
        title = re.sub(r'[（\(].*?[）\)]', '', title)
        
        # 移除冒号后的副标题
        if '：' in title:
            title = title.split('：')[0]
        if ':' in title:
            title = title.split(':')[0]
        
        # 清理空白字符
        title = title.strip()
        
        return title
    
    def _prepare_search_author(self, book: DoubanBook) -> str:
        """
        准备搜索用的作者
        
        Args:
            book: 书籍对象
            
        Returns:
            str: 搜索作者
        """
        author = book.author or ""
        
        # 移除译者信息等
        import re
        
        # 移除 [国别] 标识
        author = re.sub(r'\[.*?\]', '', author)
        
        # 取第一个作者（如果有多个）
        if '/' in author:
            author = author.split('/')[0]
        if '、' in author:
            author = author.split('、')[0]
        
        # 清理空白字符
        author = author.strip()
        
        return author