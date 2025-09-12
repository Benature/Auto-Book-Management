# -*- coding: utf-8 -*-
"""
Z-Library 服务

分离搜索和下载功能，提供更好的错误处理。
"""

import nest_asyncio

nest_asyncio.apply()

import asyncio
import difflib
import json
import os
import random
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import zlibrary

from core.pipeline import NetworkError, ProcessingError, ResourceNotFoundError
from utils.logger import get_logger


class ZLibrarySearchService:
    """Z-Library搜索服务 - 专门负责搜索功能"""

    def __init__(self,
                 email: str,
                 password: str,
                 proxy_list: List[str] = None,
                 min_delay: float = 1.0,
                 max_delay: float = 3.0):
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

        # 不在初始化时立即连接，改为延迟连接
        # self.ensure_connected()

        # 搜索策略
        self.search_strategies = [{
            'name':
            'ISBN搜索',
            'priority':
            1,
            'build_query':
            self._build_isbn_query,
            'condition':
            lambda t, a, i, p: bool(i and i.strip())
        }, {
            'name':
            '书名+作者+出版社搜索',
            'priority':
            2,
            'build_query':
            self._build_full_query,
            'condition':
            lambda t, a, i, p: bool(t and a and p)
        }, {
            'name': '书名+作者搜索',
            'priority': 3,
            'build_query': self._build_title_author_query,
            'condition': lambda t, a, i, p: bool(t and a)
        }, {
            'name': '仅书名搜索',
            'priority': 4,
            'build_query': self._build_title_query,
            'condition': lambda t, a, i, p: bool(t)
        }]

    def ensure_connected(self) -> bool:
        """确保客户端已连接，支持重试机制"""
        max_retries = 3
        base_delay = 2.0
        
        for attempt in range(1, max_retries + 1):
            try:
                if self.lib is None:
                    self.logger.info(f'开始登陆Zlibrary (尝试 {attempt}/{max_retries})')
                    self.lib = zlibrary.AsyncZlib(proxy_list=self.proxy_list)
                    asyncio.run(self.lib.login(self.__email, self.__password))
                    self.logger.info('Zlibrary登录成功')
                # 无论是新创建连接还是已有连接，都应该返回True
                return True
                
            except Exception as e:
                error_msg = str(e)
                self.consecutive_errors += 1
                
                if attempt < max_retries:
                    retry_delay = base_delay * (2 ** (attempt - 1))  # 指数退避
                    self.logger.warning(f"Z-Library连接失败，{retry_delay}秒后重试第{attempt + 1}次: {error_msg}")
                    time.sleep(retry_delay)
                    # 重置lib以便下次重新连接
                    self.lib = None
                    continue
                else:
                    self.logger.error(f"Z-Library连接失败，已重试{max_retries}次: {error_msg}")
                    raise NetworkError(f"Z-Library连接失败（重试{max_retries}次后失败）: {error_msg}")
        
        return False

    def search_books(self,
                     title: str = None,
                     author: str = None,
                     isbn: str = None,
                     publisher: str = None) -> List[Dict[str, Any]]:
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
        self.logger.info(
            f"开始渐进式搜索: 书名='{title}', 作者='{author}', ISBN='{isbn}', 出版社='{publisher}'"
        )

        # 获取适用的搜索策略
        applicable_strategies = self._get_applicable_strategies(
            title, author, isbn, publisher)

        if not applicable_strategies:
            raise ProcessingError("搜索参数不足，没有适用的搜索策略")

        # 按优先级执行搜索
        last_network_error = None

        for strategy in applicable_strategies:
            try:
                results = self._execute_search_strategy(strategy)
                if results:
                    self.consecutive_errors = 0  # 重置错误计数
                    return results

            except (NetworkError, asyncio.TimeoutError) as e:
                # 网络错误，记录但继续尝试其他策略
                last_network_error = e
                self.logger.error(f"策略 {strategy['priority']} 网络错误: {str(e)}")
                self.consecutive_errors += 1
                # 网络错误不需要额外延迟，_execute_search_strategy已经处理了
                continue

            except (ResourceNotFoundError, ProcessingError) as e:
                # 资源不存在或处理错误，继续尝试其他策略
                self.logger.warning(f"策略 {strategy['priority']} 失败: {str(e)}")
                continue

            except Exception as e:
                # 其他未知错误
                traceback.print_exc()
                self.logger.error(
                    f"策略 {strategy['priority']} 发生未知错误: {str(e)}")
                self.consecutive_errors += 1
                self._smart_delay(base_min=3.0,
                                  base_max=6.0,
                                  request_type="error")
                continue

        # 所有策略都失败
        if last_network_error:
            # 如果有网络错误，优先抛出网络错误
            self.logger.error("所有搜索策略都因网络错误失败")
            raise last_network_error
        else:
            # 否则表示没有找到匹配结果
            self.logger.warning("所有搜索策略都未找到结果")
            raise ResourceNotFoundError("未找到匹配的书籍")

    def _get_applicable_strategies(self, title: str, author: str, isbn: str,
                                   publisher: str) -> List[Dict[str, Any]]:
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

    async def _async_search_books(self, q, count: int = 10):
        # 确保已连接和登录（使用同步方法确保重试机制）
        if not self.ensure_connected():
            raise NetworkError("无法连接到Z-Library服务")

        paginator = await self.lib.search(q=q)
        await paginator.next()

        books_info = []
        for res in paginator.result:
            zlib_id = res.get('id')
            _book = await res.fetch()
            if 'id' not in _book:
                _book['id'] = zlib_id
            books_info.append(_book)
            # # TODO:
            # return books_info
        return books_info

    def _execute_search_strategy(
            self, strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """执行单个搜索策略，包含重试机制"""
        self.logger.info(f"尝试策略 {strategy['priority']}: {strategy['name']}")
        self.logger.info(f"搜索查询: {strategy['query']}")

        max_retries = 3
        base_delay = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                # 智能延迟
                self._smart_delay(request_type="search")
                self.request_count += 1

                # 执行搜索
                first_set = asyncio.run(
                    self._async_search_books(strategy['query']))

                # 搜索成功，重置错误计数
                self.consecutive_errors = 0
                break

            except Exception as e:
                error_msg = str(e)
                is_connection_reset = ("Connection reset by peer" in error_msg
                                       or "[Errno 54]" in error_msg
                                       or "ClientOSError" in str(type(e)))

                if is_connection_reset and attempt < max_retries:
                    # 连接重置错误，可以重试
                    retry_delay = base_delay * (2**(attempt - 1))  # 指数退避
                    self.logger.warning(
                        f"遇到连接重置错误，{retry_delay}秒后进行第{attempt + 1}次尝试: {error_msg}"
                    )
                    self.consecutive_errors += 1
                    time.sleep(retry_delay)
                    continue
                elif is_connection_reset:
                    # 重试次数用完，抛出网络错误
                    self.logger.error(
                        f"连接重置错误重试{max_retries}次后仍失败: {error_msg}")
                    raise NetworkError(
                        f"连接重置错误（重试{max_retries}次后失败）: {error_msg}")
                else:
                    # 其他类型的错误直接抛出
                    self.logger.error(f"搜索过程中遇到非网络错误: {error_msg}")
                    raise
        else:
            # for循环没有break，说明重试用完了
            raise NetworkError("搜索重试次数用完")

        if not first_set:
            self.logger.info(f"搜索无结果")
            return []

        # 处理结果
        processed_results = self._process_search_results(first_set)

        self.logger.info(
            f"策略 '{strategy['name']}' 找到 {len(processed_results)} 个结果")

        return processed_results

    def _process_authors(self, author_info):
        if isinstance(author_info, str):
            return author_info
        if isinstance(author_info, list):
            return ";;".join(
                [self._process_authors(_info) for _info in author_info])
        if isinstance(author_info, dict):
            return author_info['author']

    def _process_search_results(self,
                                results: List[Any]) -> List[Dict[str, Any]]:
        """处理搜索结果"""
        processed_results = []

        for i, result in enumerate(results):
            # 提取书籍信息
            book_info = {
                'zlibrary_id': result.get('id'),
                'title': result.get('name'),
                'authors': self._process_authors(result.get('authors', '')),
                'extension': result.get('extension', '').lower(),
                'size': result.get('size'),
                'isbn': result.get('isbn', ''),
                'url': result.get('url', ''),
                'cover': result.get('cover', ''),
                'description': result.get('description', ''),
                'edition': result.get('edition', ''),
                'categories': result.get('categories', ''),
                'categories_url': result.get('categories_url', ''),
                'download_url': result.get('download_url', ''),
                'publisher': result.get('publisher', ''),
                'year': result.get('year', ''),
                'language': result.get('language', ''),
                'rating': result.get('rating', ''),
                'quality': result.get('quality', ''),
                'raw_json': json.dumps(result, ensure_ascii=False)
            }

            processed_results.append(book_info)

        return processed_results

    def calculate_match_score(self, douban_book: Dict[str, str],
                              zlibrary_book: Dict[str, str]) -> float:
        """
        计算豆瓣书籍和Z-Library书籍的匹配度得分
        
        Args:
            douban_book: 豆瓣书籍信息字典，包含title, author, publisher, year等
            zlibrary_book: Z-Library书籍信息字典
            
        Returns:
            float: 匹配度得分，范围0.0-1.0
        """
        score = 0.0

        # 1. 书名相似度 (权重: 0.4)
        title_score = self._calculate_text_similarity(
            douban_book.get('title', ''), zlibrary_book.get('title', ''))
        score += title_score * 0.4

        # 2. 作者相似度 (权重: 0.3)
        douban_author = douban_book.get('author', '')
        zlibrary_authors = zlibrary_book.get('authors', '').replace(';;', ' ')
        author_score = self._calculate_text_similarity(douban_author,
                                                       zlibrary_authors)
        score += author_score * 0.3

        # 3. 出版社相似度 (权重: 0.15)
        publisher_score = self._calculate_text_similarity(
            douban_book.get('publisher', ''),
            zlibrary_book.get('publisher', ''))
        score += publisher_score * 0.15

        # 4. 年份匹配 (权重: 0.1)
        year_score = self._calculate_year_similarity(
            douban_book.get('publish_date', ''), zlibrary_book.get('year', ''))
        score += year_score * 0.1

        # 5. ISBN完全匹配奖励 (权重: 0.05)
        isbn_score = self._calculate_isbn_similarity(
            douban_book.get('isbn', ''), zlibrary_book.get('isbn', ''))
        score += isbn_score * 0.05

        return min(1.0, score)  # 确保不超过1.0

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度"""
        if not text1 or not text2:
            return 0.0

        # 预处理：转换为小写，移除标点符号和多余空格
        text1 = re.sub(r'[^\w\s]', ' ', text1.lower()).strip()
        text2 = re.sub(r'[^\w\s]', ' ', text2.lower()).strip()

        if text1 == text2:
            return 1.0

        # 使用difflib计算序列相似度
        similarity = difflib.SequenceMatcher(None, text1, text2).ratio()
        return similarity

    def _calculate_year_similarity(self, date_str: str,
                                   year_str: str) -> float:
        """计算年份相似度"""
        if not date_str or not year_str:
            return 0.0

        try:
            # 从日期字符串中提取年份
            douban_year = re.search(r'\d{4}', date_str)
            if douban_year:
                douban_year = int(douban_year.group())
                zlibrary_year = int(year_str)

                # 年份完全匹配
                if douban_year == zlibrary_year:
                    return 1.0
                # 年份相差1年内
                elif abs(douban_year - zlibrary_year) <= 1:
                    return 0.8
                # 年份相差2年内
                elif abs(douban_year - zlibrary_year) <= 2:
                    return 0.6
                else:
                    return 0.0
        except (ValueError, AttributeError):
            return 0.0

        return 0.0

    def _calculate_isbn_similarity(self, isbn1: str, isbn2: str) -> float:
        """计算ISBN相似度"""
        if not isbn1 or not isbn2:
            return 0.0

        # 移除ISBN中的非数字字符
        isbn1_clean = re.sub(r'[^\d]', '', isbn1)
        isbn2_clean = re.sub(r'[^\d]', '', isbn2)

        if isbn1_clean and isbn2_clean and isbn1_clean == isbn2_clean:
            return 1.0

        return 0.0

    def _build_isbn_query(self,
                          title: str = None,
                          author: str = None,
                          isbn: str = None,
                          publisher: str = None) -> str:
        """构建ISBN搜索查询"""
        return f"isbn:{isbn.strip()}"

    def _build_full_query(self,
                          title: str = None,
                          author: str = None,
                          isbn: str = None,
                          publisher: str = None) -> str:
        """构建书名+作者+出版社搜索查询"""
        parts = [title.strip(), author.strip(), publisher.strip()]
        return ' '.join(parts)

    def _build_title_author_query(self,
                                  title: str = None,
                                  author: str = None,
                                  isbn: str = None,
                                  publisher: str = None) -> str:
        """构建书名+作者搜索查询"""
        parts = [title.strip(), author.strip()]
        return ' '.join(parts)

    def _build_title_query(self,
                           title: str = None,
                           author: str = None,
                           isbn: str = None,
                           publisher: str = None) -> str:
        """构建仅书名搜索查询"""
        return title.strip()

    def _smart_delay(self,
                     base_min: float = None,
                     base_max: float = None,
                     request_type: str = "normal"):
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

    def __init__(self,
                 email: str,
                 password: str,
                 proxy_list: List[str] = None,
                 format_priority: List[str] = None,
                 min_delay: float = 2.0,
                 max_delay: float = 5.0,
                 max_retries: int = 3):
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
        """确保客户端已连接，支持重试机制"""
        max_retries = 3
        base_delay = 2.0
        
        for attempt in range(1, max_retries + 1):
            try:
                if self.lib is None:
                    self.logger.info(f'开始登陆Zlibrary (尝试 {attempt}/{max_retries})')
                    self.lib = zlibrary.AsyncZlib(proxy_list=self.proxy_list)
                    asyncio.run(self.lib.login(self.__email, self.__password))
                    self.logger.info('Zlibrary登录成功')
                # 无论是新创建连接还是已有连接，都应该返回True
                return True
                
            except Exception as e:
                error_msg = str(e)
                self.consecutive_errors += 1
                
                if attempt < max_retries:
                    retry_delay = base_delay * (2 ** (attempt - 1))  # 指数退避
                    self.logger.warning(f"Z-Library连接失败，{retry_delay}秒后重试第{attempt + 1}次: {error_msg}")
                    time.sleep(retry_delay)
                    # 重置lib以便下次重新连接
                    self.lib = None
                    continue
                else:
                    self.logger.error(f"Z-Library连接失败，已重试{max_retries}次: {error_msg}")
                    raise NetworkError(f"Z-Library连接失败（重试{max_retries}次后失败）: {error_msg}")
        
        return False

    def download_book(self, book_info: Dict[str, Any],
                      output_dir: str) -> Optional[str]:
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

        # 暂时构建默认文件名（如果响应头中没有文件名会使用这个）
        title = book_info.get('title', 'Unknown')
        authors = book_info.get('authors', 'Unknown')
        extension = book_info.get('extension', 'epub')

        # 处理作者字段
        if ';;' in authors:
            author = authors.split(';;')[0]  # 取第一个作者
        else:
            author = authors

        default_file_name = f"{title} - {author}.{extension}"
        default_file_name = self._sanitize_filename(default_file_name)

        self.logger.info(f"开始下载: {title}")

        # # 获取书籍ID
        # book_id = book_info.get('zlibrary_id') or book_info.get('id')

        # # 如果ID为空或为'None'字符串，尝试从type:download_url中提取
        # if not book_id or book_id == 'None':
        #     download_url = book_info.get('download_url', '')
        #     if download_url:
        #         # 从 URL 中提取 ID，格式类似 https://z-library.sk/dl/25295952/7c99fd
        #         import re
        #         match = re.search(r'/dl/(\d+)/', download_url)
        #         if match:
        #             book_id = match.group(1)
        #             self.logger.info(f"从下载链接提取到ID: {book_id}")

        # if not book_id or book_id == 'None':
        #     raise ProcessingError("书籍信息中缺少ID，且无法从下载链接提取")

        # 执行下载，支持重试
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"下载尝试 {title} {attempt}/{self.max_retries}")

                # 智能延迟
                self._smart_delay(request_type="download")
                self.request_count += 1

                # 获取下载链接（优先使用book_info中的，否则使用zlibrary API获取）
                download_url = book_info.get('download_url')
                if not download_url:
                    self.logger.info(f"未找到 {title} 直接下载链接，尝试使用Z-Library API获取")
                    # 这里可以添加通过zlibrary API获取下载链接的逻辑
                    raise ProcessingError(f"{title} 书籍信息中缺少下载链接")

                # 使用requests下载文件
                headers = {
                    'User-Agent':
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    # 'Referer':
                    # 'https://z-library.sk/',
                    # 'Accept':
                    # 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                }

                self.logger.info(f"使用链接下载: {download_url}")

                headers['Cookie'] = "; ".join(
                    [f"{k}={v}" for k, v in self.lib.cookies.items()] +
                    ["switchLanguage=zh", "siteLanguage=zh"])

                # 配置代理
                proxies = None
                if self.proxy_list:
                    proxy_url = random.choice(self.proxy_list)
                    proxies = {'http': proxy_url, 'https': proxy_url}
                    self.logger.info(f"使用代理: {proxy_url}")

                # 使用 AsyncZlib 的 cookies
                # cookies = None
                # if self.lib and hasattr(self.lib,
                #                         'cookies') and self.lib.cookies:
                #     try:
                #         # 将 aiohttp cookies 转换为 requests 可用的格式
                #         cookies = {}
                #         if hasattr(self.lib.cookies, '_cookies'):
                #             for domain_cookies in self.lib.cookies._cookies.values(
                #             ):
                #                 for path_cookies in domain_cookies.values():
                #                     for cookie in path_cookies.values():
                #                         cookies[cookie.key] = cookie.value
                #         self.logger.info(
                #             f"使用 AsyncZlib cookies，共 {len(cookies)} 个")
                #     except Exception as e:
                #         self.logger.warning(
                #             f"获取 AsyncZlib cookies 失败: {str(e)}")
                #         cookies = None

                response = requests.get(
                    download_url,
                    headers=headers,
                    # cookies=cookies,
                    proxies=proxies,
                    stream=True,
                    timeout=30)

                # 检查响应状态
                if response.status_code != 200:
                    raise ProcessingError(
                        f"下载失败，HTTP状态码: {response.status_code}")

                # 检查内容类型
                content_type = response.headers.get('content-type', '')
                self.logger.info(f"响应内容类型: {content_type}")

                # 检查文件大小
                content_length = response.headers.get('content-length')
                if content_length:
                    self.logger.info(f"文件大小: {int(content_length):,} bytes")

                # 尝试从响应头获取原始文件名
                content_disposition = response.headers.get(
                    'content-disposition', '')
                original_filename = self._extract_filename_from_content_disposition(
                    content_disposition)

                if original_filename:
                    self.logger.info(f"使用响应头中的原始文件名: {original_filename}")
                    file_name = self._sanitize_filename(original_filename)
                else:
                    self.logger.info(f"响应头中没有文件名，使用默认文件名: {default_file_name}")
                    file_name = default_file_name

                file_path = output_path / file_name

                # 保存文件
                downloaded_size = 0
                with open(str(file_path), 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)

                self.logger.info(f"下载完成，实际大小: {downloaded_size:,} bytes")

                self.consecutive_errors = 0
                self.logger.info(f"下载成功: {file_path}")
                return str(file_path)

            except Exception as e:
                # traceback.print_exc()
                error_msg = str(e)
                is_connection_reset = ("Connection reset by peer" in error_msg
                                       or "[Errno 54]" in error_msg
                                       or "ClientOSError" in str(type(e)))

                self.consecutive_errors += 1

                if is_connection_reset:
                    self.logger.warning(
                        f"下载尝试 {attempt} 遇到连接重置错误: {error_msg}")
                else:
                    self.logger.error(f"下载尝试 {attempt} 失败: {error_msg}")

                if attempt < self.max_retries:
                    # 根据错误类型选择延迟时间
                    if is_connection_reset:
                        # 连接重置错误，使用指数退避
                        retry_delay = 2.0 * (2**(attempt - 1))
                        self.logger.info(f"连接重置错误，{retry_delay}秒后重试")
                        time.sleep(retry_delay)
                    else:
                        # 其他错误，使用原有延迟
                        self._smart_delay(base_min=5.0,
                                          base_max=10.0,
                                          request_type="error")
                else:
                    # 最后一次尝试失败，判断错误类型
                    if is_connection_reset:
                        raise NetworkError(
                            f"连接重置错误（重试{self.max_retries}次后失败）: {error_msg}")
                    elif "not found" in error_msg.lower(
                    ) or "404" in error_msg:
                        raise ResourceNotFoundError(f"书籍文件不存在: {error_msg}")
                    else:
                        raise ProcessingError(f"下载失败: {error_msg}")

        return None

    # 已删除 _save_download_result，直接使用requests下载

    def _extract_filename_from_content_disposition(
            self, content_disposition: str) -> Optional[str]:
        """从 Content-Disposition 头中提取文件名"""
        if not content_disposition:
            return None

        # 匹配 filename="xxx" 或 filename*=UTF-8''xxx 格式
        import re

        # 首先尝试匹配 filename*=UTF-8''xxx 格式（RFC 5987）
        match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition,
                          re.IGNORECASE)
        if match:
            import urllib.parse
            try:
                filename = urllib.parse.unquote(match.group(1))
                return filename
            except:
                pass

        # 然后尝试匹配 filename="xxx" 或 filename=xxx 格式
        match = re.search(r'filename[^;=\n]*=(([\'"])([^\'"]*?)\2|([^;\n]*))',
                          content_disposition, re.IGNORECASE)
        if match:
            filename = match.group(3) or match.group(4)
            if filename:
                return filename.strip()

        return None

    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名"""
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in illegal_chars:
            filename = filename.replace(char, '_')

        # 限制长度
        if len(filename) > 200:
            name_parts = filename.split('.')
            extension = name_parts[-1] if len(name_parts) > 1 else ''
            base_name = '.'.join(
                name_parts[:-1]) if len(name_parts) > 1 else filename
            base_name = base_name[:200 - len(extension) - 1]
            filename = f"{base_name}.{extension}" if extension else base_name

        return filename

    def _smart_delay(self,
                     base_min: float = None,
                     base_max: float = None,
                     request_type: str = "normal"):
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


class ZLibraryService:
    """Z-Library 服务 - 整合搜索和下载服务"""

    def __init__(self,
                 email: str,
                 password: str,
                 proxy_list: List[str] = None,
                 format_priority: List[str] = None,
                 download_dir: str = "data/downloads"):
        """
        初始化Z-Library服务
        
        Args:
            email: Z-Library 账号
            password: 密码
            proxy_list: 代理列表
            format_priority: 格式优先级
            download_dir: 下载目录
        """
        self.logger = get_logger("zlibrary_service")

        # 初始化子服务
        self.search_service = ZLibrarySearchService(email=email,
                                                    password=password,
                                                    proxy_list=proxy_list)

        self.download_service = ZLibraryDownloadService(
            email=email,
            password=password,
            proxy_list=proxy_list,
            format_priority=format_priority)

        self.download_dir = download_dir

    def search_books(self,
                     title: str = None,
                     author: str = None,
                     isbn: str = None,
                     publisher: str = None) -> List[Dict[str, Any]]:
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
        return self.search_service.search_books(title=title,
                                                author=author,
                                                isbn=isbn,
                                                publisher=publisher)

    def download_book(self,
                      book_info: Dict[str, Any],
                      output_dir: str = None) -> Optional[str]:
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

    def get_download_limits(self) -> Dict[str, int]:
        """
        获取Z-Library下载限制信息
        
        Returns:
            Dict[str, int]: 包含下载限制信息的字典
                - daily_amount: 每日总限额
                - daily_allowed: 每日允许下载
                - daily_remaining: 每日剩余下载次数 
                - daily_reset: 下次重置时间戳
        """
        try:
            # 确保下载服务连接
            self.download_service.ensure_connected()
            
            # 获取限制信息
            limits = asyncio.run(self.download_service.lib.profile.get_limits())
            
            self.logger.info(f"获取下载限制: {limits}")
            
            return limits
            
        except Exception as e:
            self.logger.error(f"获取下载限制失败: {str(e)}")
            # 返回默认值，避免阻塞流程
            return {
                'daily_amount': 0,
                'daily_allowed': 0,  
                'daily_remaining': 0,
                'daily_reset': 0
            }

    def check_download_available(self) -> bool:
        """
        检查是否有可用的下载次数
        
        Returns:
            bool: 是否可以下载
        """
        limits = self.get_download_limits()
        remaining = limits.get('daily_remaining', 0)
        
        self.logger.info(f"下载限制检查: 剩余次数 {remaining}")
        
        return remaining > 0

    # 已删除 search_and_download 方法，完全分离 search 和 download 步骤


    def calculate_match_score(self, douban_book: Dict[str, str],
                              zlibrary_book: Dict[str, str]) -> float:
        """
        计算豆瓣书籍和Z-Library书籍的匹配度得分
        
        Args:
            douban_book: 豆瓣书籍信息字典
            zlibrary_book: Z-Library书籍信息字典
            
        Returns:
            float: 匹配度得分，范围0.0-1.0
        """
        return self.search_service.calculate_match_score(
            douban_book, zlibrary_book)
