# -*- coding: utf-8 -*-

"""
Z-Library 服务

负责与 Z-Library 交互，搜索和下载书籍。
"""

import os
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from datetime import datetime
import shutil

# 导入 zlibrary 包
from zlibrary import ZLibrary

from utils.logger import get_logger


class ZLibraryService:
    """Z-Library 服务类"""
    
    def __init__(self, username: str, password: str, format_priority: List[str], download_dir: str, max_retries: int = 3):
        """
        初始化 Z-Library 服务
        
        Args:
            username: Z-Library 账号
            password: 密码
            format_priority: 下载格式优先级列表
            download_dir: 下载目录
            max_retries: 最大重试次数
        """
        self.logger = get_logger("zlibrary_service")
        self.username = username
        self.password = password
        self.format_priority = format_priority
        self.download_dir = Path(download_dir)
        self.max_retries = max_retries
        self.client = None
        
        # 确保下载目录存在
        os.makedirs(self.download_dir, exist_ok=True)
    
    def connect(self) -> bool:
        """
        连接到 Z-Library
        
        Returns:
            bool: 连接是否成功
        """
        try:
            self.logger.info(f"正在连接 Z-Library，用户名: {self.username}")
            self.client = ZLibrary()
            login_result = self.client.login(self.username, self.password)
            
            if login_result:
                self.logger.info("Z-Library 连接成功")
                return True
            else:
                self.logger.error("Z-Library 登录失败，请检查账号和密码")
                return False
                
        except Exception as e:
            self.logger.error(f"Z-Library 连接失败: {str(e)}")
            return False
    
    def ensure_connected(self) -> bool:
        """
        确保已连接到 Z-Library
        
        Returns:
            bool: 是否已连接
        """
        if self.client is None:
            return self.connect()
        return True
    
    def search_book(self, title: str, author: str = None, isbn: str = None) -> List[Dict[str, Any]]:
        """
        搜索书籍
        
        Args:
            title: 书名
            author: 作者（可选）
            isbn: ISBN（可选）
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        if not self.ensure_connected():
            return []
        
        try:
            # 构建搜索查询
            query = title
            if author:
                query = f"{title} {author}"
            
            # 如果有 ISBN，优先使用 ISBN 搜索
            if isbn:
                self.logger.info(f"使用 ISBN 搜索: {isbn}")
                isbn_results = self.client.search(isbn)
                if isbn_results and len(isbn_results) > 0:
                    self.logger.info(f"ISBN 搜索成功，找到 {len(isbn_results)} 个结果")
                    return self._process_search_results(isbn_results)
            
            # 使用标题和作者搜索
            self.logger.info(f"搜索书籍: {query}")
            results = self.client.search(query)
            
            if results and len(results) > 0:
                self.logger.info(f"搜索成功，找到 {len(results)} 个结果")
                return self._process_search_results(results)
            else:
                self.logger.warning(f"未找到匹配的书籍: {query}")
                return []
                
        except Exception as e:
            self.logger.error(f"搜索书籍失败: {str(e)}")
            return []
    
    def _process_search_results(self, results: List[Any]) -> List[Dict[str, Any]]:
        """
        处理搜索结果
        
        Args:
            results: 原始搜索结果
            
        Returns:
            List[Dict[str, Any]]: 处理后的搜索结果列表
        """
        processed_results = []
        
        for result in results:
            try:
                # 提取书籍信息
                book_info = {
                    'zlibrary_id': result.id,
                    'title': result.title,
                    'author': result.author,
                    'file_format': result.extension.lower() if hasattr(result, 'extension') else '',
                    'file_size': result.size_in_bytes if hasattr(result, 'size_in_bytes') else 0,
                    'download_url': result.get_download_url() if hasattr(result, 'get_download_url') else '',
                    'language': result.language if hasattr(result, 'language') else '',
                    'year': result.year if hasattr(result, 'year') else '',
                    'pages': result.pages if hasattr(result, 'pages') else 0,
                    'publisher': result.publisher if hasattr(result, 'publisher') else '',
                    'raw_result': result  # 保存原始结果对象，以便后续使用
                }
                processed_results.append(book_info)
            except Exception as e:
                self.logger.error(f"处理搜索结果失败: {str(e)}")
        
        return processed_results
    
    def find_best_format(self, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        根据格式优先级找到最佳格式的书籍
        
        Args:
            results: 搜索结果列表
            
        Returns:
            Optional[Dict[str, Any]]: 最佳格式的书籍，如果没有找到则返回 None
        """
        if not results:
            return None
        
        # 按格式优先级排序
        for format_type in self.format_priority:
            for result in results:
                if result['file_format'].lower() == format_type.lower():
                    self.logger.info(f"找到最佳格式: {format_type}, 书籍: {result['title']}")
                    return result
        
        # 如果没有找到优先格式，返回第一个结果
        self.logger.warning(f"未找到优先格式 {self.format_priority}，使用默认格式: {results[0]['file_format']}")
        return results[0]
    
    def download_book(self, book_info: Dict[str, Any], output_dir: Optional[str] = None) -> Optional[str]:
        """
        下载书籍
        
        Args:
            book_info: 书籍信息
            output_dir: 输出目录，默认使用实例化时指定的下载目录
            
        Returns:
            Optional[str]: 下载的文件路径，下载失败则返回 None
        """
        if not self.ensure_connected():
            return None
        
        if output_dir is None:
            output_dir = self.download_dir
        else:
            output_dir = Path(output_dir)
            os.makedirs(output_dir, exist_ok=True)
        
        # 获取原始结果对象
        raw_result = book_info.get('raw_result')
        if not raw_result:
            self.logger.error("下载失败: 缺少原始结果对象")
            return None
        
        # 构建文件名
        file_name = f"{book_info['title']}_{book_info['author']}.{book_info['file_format']}"
        # 替换文件名中的非法字符
        file_name = self._sanitize_filename(file_name)
        file_path = output_dir / file_name
        
        self.logger.info(f"开始下载书籍: {book_info['title']}")
        
        # 尝试下载，最多重试指定次数
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(f"下载尝试 {attempt}/{self.max_retries}")
                
                # 使用 zlibrary 包的下载方法
                download_result = self.client.download(raw_result, str(file_path))
                
                if download_result and os.path.exists(file_path):
                    self.logger.info(f"下载成功: {file_path}")
                    return str(file_path)
                else:
                    self.logger.warning(f"下载失败，尝试 {attempt}/{self.max_retries}")
                    time.sleep(2)  # 等待一段时间再重试
            except Exception as e:
                self.logger.error(f"下载过程中出错 (尝试 {attempt}/{self.max_retries}): {str(e)}")
                time.sleep(2)  # 等待一段时间再重试
        
        self.logger.error(f"下载失败，已达到最大重试次数 {self.max_retries}")
        return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除非法字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            str: 清理后的文件名
        """
        # 替换文件名中的非法字符
        illegal_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 限制文件名长度
        if len(filename) > 200:
            name_parts = filename.split('.')
            extension = name_parts[-1] if len(name_parts) > 1 else ''
            base_name = '.'.join(name_parts[:-1]) if len(name_parts) > 1 else filename
            base_name = base_name[:200 - len(extension) - 1]
            filename = f"{base_name}.{extension}" if extension else base_name
        
        return filename