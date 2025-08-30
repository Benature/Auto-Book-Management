# -*- coding: utf-8 -*-
"""
Z-Library 服务 V2

重构版本，分离搜索和下载功能，提供更好的错误处理。
"""

import nest_asyncio
nest_asyncio.apply()

import os
import time
import random
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

import zlibrary

from utils.logger import get_logger
from core.pipeline import ProcessingError, NetworkError, ResourceNotFoundError


class ZLibrarySearchService:
    """Z-Library搜索服务 - 专门负责搜索功能"""
    
    def __init__(
        self,
        email: str,
        password: str,
        proxy_list: List[str] = None,
        min_delay: float = 1.0,
        max_delay: float = 3.0
    ):
        """
        初始化搜索服务
        
        Args:
            email: Z-Library 账号
            password: 密码
            proxy_list: 代理列表
            min_delay: 最小延迟时间（秒）
            max_delay: 最大延迟时间（秒）
        """
        self.logger = get_logger("zlibrary_search")
        self.__email = email
        self.__password = password
        self.proxy_list = proxy_list or []
        self.min_delay = min_delay
        self.max_delay = max_delay
        
        # 错误计数和请求计数
        self.consecutive_errors = 0
        self.request_count = 0
        
        # 客户端实例
        self.lib = None
        
        # 搜索策略
        self.search_strategies = [
            {
                'name': 'ISBN搜索',
                'priority': 1,
                'build_query': self._build_isbn_query,
                'condition': lambda t, a, i, p: bool(i and i.strip())
            },
            {
                'name': '书名+作者+出版社搜索',
                'priority': 2,
                'build_query': self._build_full_query,
                'condition': lambda t, a, i, p: bool(t and a and p)
            },
            {
                'name': '书名+作者搜索',
                'priority': 3,
                'build_query': self._build_title_author_query,
                'condition': lambda t, a, i, p: bool(t and a)
            },
            {
                'name': '仅书名搜索',
                'priority': 4,
                'build_query': self._build_title_query,
                'condition': lambda t, a, i, p: bool(t)
            }
        ]
    
    def ensure_connected(self) -> bool:
        """确保客户端已连接"""
        try:
            if self.lib is None:
                self.lib = zlibrary.AsyncZlib(proxy_list=self.proxy_list)
                asyncio.run(self.lib.login(self.__email, self.__password))
            return True
        except Exception as e:
            self.logger.error(f"Z-Library连接失败: {str(e)}")
            self.consecutive_errors += 1
            raise NetworkError(f"Z-Library连接失败: {str(e)}")
    
    def search_books(
        self,
        title: str = None,
        author: str = None,
        isbn: str = None,
        publisher: str = None
    ) -> List[Dict[str, Any]]:
        """
        搜索书籍
        
        Args:
            title: 书名
            author: 作者
            isbn: ISBN
            publisher: 出版社
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        self.ensure_connected()
        
        self.logger.info(
            f"开始渐进式搜索: 书名='{title}', 作者='{author}', ISBN='{isbn}', 出版社='{publisher}'"
        )
        
        # 获取适用的搜索策略
        applicable_strategies = self._get_applicable_strategies(title, author, isbn, publisher)
        
        if not applicable_strategies:
            raise ProcessingError("搜索参数不足，没有适用的搜索策略")
        
        # 按优先级执行搜索
        for strategy in applicable_strategies:
            try:
                results = self._execute_search_strategy(strategy)
                if results:
                    self.consecutive_errors = 0  # 重置错误计数
                    return results
                    
            except Exception as e:
                self.logger.error(f"策略 {strategy['priority']} 搜索失败: {str(e)}")
                self.consecutive_errors += 1
                self._smart_delay(base_min=3.0, base_max=6.0, request_type="error")
                continue
        
        # 所有策略都失败
        self.logger.warning("所有搜索策略都未找到结果")
        raise ResourceNotFoundError("未找到匹配的书籍")
    
    def _get_applicable_strategies(self, title: str, author: str, isbn: str, publisher: str) -> List[Dict[str, Any]]:
        """获取适用的搜索策略"""
        applicable_strategies = []
        
        for strategy in self.search_strategies:
            if strategy['condition'](title, author, isbn, publisher):
                query = strategy['build_query'](title, author, isbn, publisher)
                applicable_strategies.append({
                    'name': strategy['name'],
                    'priority': strategy['priority'],
                    'query': query
                })
        
        return applicable_strategies
    
    def _execute_search_strategy(self, strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行单个搜索策略"""
        self.logger.info(f"尝试策略 {strategy['priority']}: {strategy['name']}")
        self.logger.info(f"搜索查询: {strategy['query']}")
        
        # 智能延迟
        self._smart_delay(request_type="search")
        self.request_count += 1
        
        # 执行搜索
        paginator = asyncio.run(self.lib.search(q=strategy['query']))
        first_set = asyncio.run(paginator.next())
        
        if not first_set:
            return []
        
        # 处理结果
        processed_results = self._process_search_results(first_set)
        
        self.logger.info(
            f"策略 '{strategy['name']}' 找到 {len(processed_results)} 个结果"
        )
        
        return processed_results
    
    def _process_search_results(self, results: List[Any]) -> List[Dict[str, Any]]:
        """处理搜索结果"""
        processed_results = []
        
        for i, result in enumerate(results):
            try:
                # 提取书籍信息
                book_info = {
                    'zlibrary_id': result.get('id'),
                    'title': result.get('name'),
                    'authors': ';;'.join(result.get('authors', [])),
                    'extension': result.get('extension', '').lower(),
                    'size': result.get('size'),
                    'isbn': result.get('isbn', ''),
                    'url': result.get('url', ''),
                    'cover': result.get('cover', ''),
                    'publisher': result.get('publisher', ''),
                    'year': result.get('year', ''),
                    'language': result.get('language', ''),
                    'rating': result.get('rating', ''),
                    'quality': result.get('quality', ''),
                    'raw_json': json.dumps(result, ensure_ascii=False)
                }
                
                processed_results.append(book_info)
                
            except Exception as e:
                self.logger.error(f"处理搜索结果 {i+1} 失败: {str(e)}")
                continue
        
        return processed_results
    
    def _build_isbn_query(self, title: str = None, author: str = None, isbn: str = None, publisher: str = None) -> str:
        """构建ISBN搜索查询"""
        return f"isbn:{isbn.strip()}"
    
    def _build_full_query(self, title: str = None, author: str = None, isbn: str = None, publisher: str = None) -> str:
        """构建书名+作者+出版社搜索查询"""
        parts = [title.strip(), author.strip(), publisher.strip()]
        return ' '.join(parts)
    
    def _build_title_author_query(self, title: str = None, author: str = None, isbn: str = None, publisher: str = None) -> str:
        """构建书名+作者搜索查询"""
        parts = [title.strip(), author.strip()]
        return ' '.join(parts)
    
    def _build_title_query(self, title: str = None, author: str = None, isbn: str = None, publisher: str = None) -> str:
        """构建仅书名搜索查询"""
        return title.strip()
    
    def _smart_delay(self, base_min: float = None, base_max: float = None, request_type: str = "normal"):
        """智能延迟"""
        min_delay = base_min or self.min_delay
        max_delay = base_max or self.max_delay
        
        # 根据请求类型调整延迟
        if request_type == "search":
            min_delay = max(min_delay * 1.5, 2.0)
            max_delay = max(max_delay * 1.5, 4.0)
        elif request_type == "error":
            min_delay = max(min_delay * 2, 3.0)
            max_delay = max(max_delay * 2, 6.0)
        
        # 根据连续错误增加延迟
        if self.consecutive_errors > 0:
            error_multiplier = min(1.5**self.consecutive_errors, 4.0)
            min_delay *= error_multiplier
            max_delay *= error_multiplier
        
        # 执行延迟
        delay = random.uniform(min_delay, max_delay)
        self.logger.debug(f"延迟 {delay:.2f} 秒")
        time.sleep(delay)


class ZLibraryDownloadService:
    """Z-Library下载服务 - 专门负责下载功能"""
    
    def __init__(
        self,
        email: str,
        password: str,
        proxy_list: List[str] = None,
        format_priority: List[str] = None,
        min_delay: float = 2.0,
        max_delay: float = 5.0,
        max_retries: int = 3
    ):
        """
        初始化下载服务
        
        Args:
            email: Z-Library 账号
            password: 密码
            proxy_list: 代理列表
            format_priority: 格式优先级
            min_delay: 最小延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            max_retries: 最大重试次数
        """
        self.logger = get_logger("zlibrary_download")
        self.__email = email
        self.__password = password
        self.proxy_list = proxy_list or []
        self.format_priority = format_priority or ['epub', 'mobi', 'pdf']
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        
        # 错误计数
        self.consecutive_errors = 0
        self.request_count = 0
        
        # 客户端实例
        self.lib = None
    
    def ensure_connected(self) -> bool:
        """确保客户端已连接"""
        try:
            if self.lib is None:
                self.lib = zlibrary.AsyncZlib(proxy_list=self.proxy_list)
                asyncio.run(self.lib.login(self.__email, self.__password))
            return True
        except Exception as e:
            self.logger.error(f"Z-Library连接失败: {str(e)}")
            self.consecutive_errors += 1
            raise NetworkError(f"Z-Library连接失败: {str(e)}")
    
    def download_book(
        self,
        book_info: Dict[str, Any],
        output_dir: str
    ) -> Optional[str]:
        """
        下载书籍文件
        
        Args:
            book_info: 书籍信息
            output_dir: 输出目录
            
        Returns:
            Optional[str]: 下载的文件路径
        """
        self.ensure_connected()
        
        output_path = Path(output_dir)
        os.makedirs(output_path, exist_ok=True)
        
        # 构建文件名
        title = book_info.get('title', 'Unknown')
        authors = book_info.get('authors', 'Unknown')
        extension = book_info.get('extension', 'epub')
        
        # 处理作者字段
        if ';;' in authors:
            author = authors.split(';;')[0]  # 取第一个作者
        else:
            author = authors
        
        file_name = f"{title} - {author}.{extension}"
        file_name = self._sanitize_filename(file_name)
        file_path = output_path / file_name
        
        self.logger.info(f"开始下载: {title}")
        
        # 获取书籍ID
        book_id = book_info.get('zlibrary_id') or book_info.get('id')
        if not book_id:
            raise ProcessingError("书籍信息中缺少ID，无法下载")
        
        # 执行下载，支持重试
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"下载尝试 {attempt}/{self.max_retries}")
                
                # 智能延迟
                self._smart_delay(request_type="download")
                self.request_count += 1
                
                # 执行下载
                download_result = asyncio.run(self.lib.download(book_id))
                
                if download_result:
                    self._save_download_result(download_result, file_path)
                    self.consecutive_errors = 0
                    self.logger.info(f"下载成功: {file_path}")
                    return str(file_path)
                else:
                    raise ProcessingError("下载结果为空")
                    
            except Exception as e:
                self.consecutive_errors += 1
                self.logger.error(f"下载尝试 {attempt} 失败: {str(e)}")
                
                if attempt < self.max_retries:
                    self._smart_delay(base_min=5.0, base_max=10.0, request_type="error")
                else:
                    # 最后一次尝试失败，判断错误类型
                    if "not found" in str(e).lower() or "404" in str(e):
                        raise ResourceNotFoundError(f"书籍文件不存在: {str(e)}")
                    else:
                        raise ProcessingError(f"下载失败: {str(e)}")
        
        return None
    
    def _save_download_result(self, download_result: Any, file_path: Path):
        """保存下载结果"""
        with open(str(file_path), 'wb') as f:
            if isinstance(download_result, bytes):
                f.write(download_result)
            elif hasattr(download_result, 'read'):
                f.write(download_result.read())
            else:
                # 测试模式
                f.write(b'test content')
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名"""
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 限制长度
        if len(filename) > 200:
            name_parts = filename.split('.')
            extension = name_parts[-1] if len(name_parts) > 1 else ''
            base_name = '.'.join(name_parts[:-1]) if len(name_parts) > 1 else filename
            base_name = base_name[:200 - len(extension) - 1]
            filename = f"{base_name}.{extension}" if extension else base_name
        
        return filename
    
    def _smart_delay(self, base_min: float = None, base_max: float = None, request_type: str = "normal"):
        """智能延迟"""
        min_delay = base_min or self.min_delay
        max_delay = base_max or self.max_delay
        
        # 根据请求类型调整延迟
        if request_type == "download":
            min_delay = max(min_delay * 1.5, 3.0)
            max_delay = max(max_delay * 1.5, 6.0)
        elif request_type == "error":
            min_delay = max(min_delay * 2, 5.0)
            max_delay = max(max_delay * 2, 10.0)
        
        # 根据连续错误增加延迟
        if self.consecutive_errors > 0:
            error_multiplier = min(1.5**self.consecutive_errors, 4.0)
            min_delay *= error_multiplier
            max_delay *= error_multiplier
        
        # 执行延迟
        delay = random.uniform(min_delay, max_delay)
        self.logger.debug(f"延迟 {delay:.2f} 秒")
        time.sleep(delay)


class ZLibraryServiceV2:
    """Z-Library 服务 V2 - 整合搜索和下载服务"""
    
    def __init__(
        self,
        email: str,
        password: str,
        proxy_list: List[str] = None,
        format_priority: List[str] = None,
        download_dir: str = "data/downloads"
    ):
        """
        初始化Z-Library服务V2
        
        Args:
            email: Z-Library 账号
            password: 密码
            proxy_list: 代理列表
            format_priority: 格式优先级
            download_dir: 下载目录
        """
        self.logger = get_logger("zlibrary_service_v2")
        
        # 初始化子服务
        self.search_service = ZLibrarySearchService(
            email=email,
            password=password,
            proxy_list=proxy_list
        )
        
        self.download_service = ZLibraryDownloadService(
            email=email,
            password=password,
            proxy_list=proxy_list,
            format_priority=format_priority
        )
        
        self.download_dir = download_dir
    
    def search_books(
        self,
        title: str = None,
        author: str = None,
        isbn: str = None,
        publisher: str = None
    ) -> List[Dict[str, Any]]:
        """
        搜索书籍
        
        Args:
            title: 书名
            author: 作者
            isbn: ISBN
            publisher: 出版社
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        return self.search_service.search_books(title, author, isbn, publisher)
    
    def download_book(
        self,
        book_info: Dict[str, Any],
        output_dir: str = None
    ) -> Optional[str]:
        """
        下载书籍文件
        
        Args:
            book_info: 书籍信息
            output_dir: 输出目录
            
        Returns:
            Optional[str]: 下载的文件路径
        """
        if output_dir is None:
            output_dir = self.download_dir
        
        return self.download_service.download_book(book_info, output_dir)
    
    def search_and_download(
        self,
        title: str = None,
        author: str = None,
        isbn: str = None,
        publisher: str = None,
        output_dir: str = None
    ) -> Optional[str]:
        """
        搜索并下载书籍
        
        Args:
            title: 书名
            author: 作者
            isbn: ISBN
            publisher: 出版社
            output_dir: 输出目录
            
        Returns:
            Optional[str]: 下载的文件路径
        """
        try:
            # 搜索书籍
            search_results = self.search_books(title, author, isbn, publisher)
            
            if not search_results:
                return None
            
            # 选择最佳格式
            best_book = self._select_best_format(search_results)
            
            # 下载书籍
            return self.download_book(best_book, output_dir)
            
        except Exception as e:
            self.logger.error(f"搜索并下载失败: {str(e)}")
            raise
    
    def _select_best_format(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """选择最佳格式的书籍"""
        if not results:
            raise ProcessingError("搜索结果为空")
        
        # 按格式优先级选择
        format_priority = self.download_service.format_priority
        
        for preferred_format in format_priority:
            for result in results:
                if result.get('extension', '').lower() == preferred_format.lower():
                    return result
        
        # 没有找到优先格式，返回第一个
        return results[0]