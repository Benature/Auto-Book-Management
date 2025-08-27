# -*- coding: utf-8 -*-
"""
Calibre 服务

负责与 Calibre Content Server 交互，查询和上传书籍。
"""

import requests
from requests.auth import HTTPBasicAuth
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime
import re
from urllib.parse import urljoin

from utils.logger import get_logger


class CalibreService:
    """Calibre 服务类"""

    def __init__(self,
                 server_url: str,
                 username: str,
                 password: str,
                 match_threshold: float = 0.6):
        """
        初始化 Calibre 服务
        
        Args:
            server_url: Calibre Content Server URL
            username: 用户名
            password: 密码
            match_threshold: 匹配阈值，0.0-1.0，值越高要求匹配度越精确
        """
        self.logger = get_logger("calibre_service")
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.password = password
        self.match_threshold = match_threshold
        self.auth = HTTPBasicAuth(username, password)
        self.session = requests.Session()
        self.session.auth = self.auth



    def search_book(self,
                    title: str,
                    author: Optional[str] = None,
                    isbn: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        搜索书籍
        
        Args:
            title: 书名
            author: 作者（可选）
            isbn: ISBN（可选）
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            # 构建搜索查询
            query = []

            # 如果有 ISBN，优先使用 ISBN 搜索
            if isbn:
                self.logger.info(f"使用 ISBN 搜索: {isbn}")
                query.append(f"identifier:isbn:{isbn}")
            else:
                # 使用标题和作者搜索
                if title:
                    # 对标题进行处理，移除副标题和特殊字符
                    clean_title = re.sub(r'[:\(\)\[\]\{\}].*$', '',
                                         title).strip()
                    query.append(f"title:~\"{clean_title}\"")

                if author:
                    query.append(f"author:~\"{author}\"")

            search_query = " and ".join(query)
            self.logger.info(f"搜索书籍: {search_query}")

            # 发送搜索请求
            url = f"{self.server_url}/ajax/search?query={search_query}&library_id=default"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('total', 0) > 0 and 'book_ids' in data:
                book_ids = data['book_ids']
                self.logger.info(f"搜索成功，找到 {len(book_ids)} 个结果")

                # 获取书籍详细信息
                books = []
                for book_id in book_ids:
                    book_info = self.get_book_info(book_id)
                    if book_info:
                        books.append(book_info)

                return books
            else:
                self.logger.info(f"未找到匹配的书籍: {search_query}")
                return []

        except Exception as e:
            self.logger.error(f"搜索书籍失败: {str(e)}")
            return []

    def get_book_info(self, book_id: int) -> Optional[Dict[str, Any]]:
        """
        获取书籍详细信息
        
        Args:
            book_id: 书籍 ID
            
        Returns:
            Optional[Dict[str, Any]]: 书籍详细信息，获取失败则返回 None
        """
        try:
            url = f"{self.server_url}/ajax/book/{book_id}/default"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data:
                # 提取书籍信息
                book_info = {
                    'calibre_id': book_id,
                    'title': data.get('title', ''),
                    'authors': data.get('authors', []),
                    'author': ', '.join(data.get('authors', [])),
                    'publisher': data.get('publisher', ''),
                    'identifiers': data.get('identifiers', {}),
                    'isbn': data.get('identifiers', {}).get('isbn', ''),
                    'formats': data.get('formats', []),
                    'cover_url':
                    f"{self.server_url}/get/cover/{book_id}/default",
                    'raw_data': data  # 保存原始数据，以便后续使用
                }
                return book_info
            else:
                self.logger.warning(f"获取书籍信息失败: ID {book_id}")
                return None

        except Exception as e:
            self.logger.error(f"获取书籍信息失败: ID {book_id}, 错误: {str(e)}")
            return None

    def find_best_match(
            self,
            title: str,
            author: Optional[str] = None,
            isbn: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        找到最佳匹配的书籍
        
        Args:
            title: 书名
            author: 作者（可选）
            isbn: ISBN（可选）
            
        Returns:
            Optional[Dict[str, Any]]: 最佳匹配的书籍，如果没有找到则返回 None
        """
        # TODO: Calibre接口未完全开发完成，临时返回None（表示未找到匹配书籍）
        self.logger.info(f"Calibre临时查询: {title} - {author} - {isbn} (临时返回未找到)")
        return None

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        计算两个字符串的相似度
        
        Args:
            str1: 第一个字符串
            str2: 第二个字符串
            
        Returns:
            float: 相似度，0.0-1.0
        """
        # 简单的 Jaccard 相似度计算
        set1 = set(str1.split())
        set2 = set(str2.split())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))

        return intersection / union if union > 0 else 0.0

    def upload_book(
            self,
            file_path: str,
            metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        上传书籍
        
        Args:
            file_path: 书籍文件路径
            metadata: 书籍元数据（可选）
            
        Returns:
            Optional[int]: 上传成功后的书籍 ID，上传失败则返回 None
        """
        # TODO: Calibre接口未完全开发完成，临时返回None（表示上传失败）
        self.logger.info(f"Calibre临时上传: {file_path} (临时返回上传失败)")
        return None
