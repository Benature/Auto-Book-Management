# -*- coding: utf-8 -*-
"""
Calibre 服务

负责通过 calibredb 命令与 Calibre 交互，查询和上传书籍。
"""

import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional, Tuple

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
        self.timeout = 120  # 2 分钟超时

    def _execute_calibredb_command(
            self,
            args: List[str],
            cwd: Optional[str] = None) -> Tuple[str, str, int]:
        """
        执行 calibredb 命令

        Args:
            args: 命令参数列表
            cwd: 工作目录（可选）

        Returns:
            Tuple[str, str, int]: stdout, stderr, return_code
        """
        # 构建完整命令
        cmd = ['calibredb'] + args

        # 添加认证参数
        if self.server_url:
            cmd.extend(['--library-path', self.server_url])
        if self.username:
            cmd.extend(['--username', self.username])
        if self.password:
            cmd.extend(['--password', self.password])

        # 添加超时参数
        cmd.extend(['--timeout', str(self.timeout)])

        self.logger.debug(f"执行 calibredb 命令: {' '.join(cmd[:3])} ...")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 10  # 给命令额外的超时缓冲
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as e:
            self.logger.error(f"calibredb 命令超时: {' '.join(cmd[:3])}")
            raise Exception(f"命令执行超时: {e}")
        except Exception as e:
            self.logger.error(f"执行 calibredb 命令失败: {str(e)}")
            raise Exception(f"命令执行失败: {e}")

    def _parse_search_results(self, book_ids_str: str) -> List[int]:
        """
        解析搜索结果中的书籍 ID

        Args:
            book_ids_str: calibredb search 返回的书籍 ID 字符串

        Returns:
            List[int]: 书籍 ID 列表
        """
        if not book_ids_str.strip():
            return []

        try:
            # calibredb search 返回逗号分隔的 ID 列表
            book_ids = [
                int(book_id.strip()) for book_id in book_ids_str.split(',')
                if book_id.strip()
            ]
            return book_ids
        except ValueError as e:
            self.logger.error(f"解析书籍 ID 失败: {book_ids_str}, 错误: {str(e)}")
            return []

    def _parse_book_list(self, json_output: str) -> List[Dict[str, Any]]:
        """
        解析 calibredb list 的 JSON 输出

        Args:
            json_output: calibredb list --for-machine 的输出

        Returns:
            List[Dict[str, Any]]: 书籍信息列表
        """
        try:
            books_data = json.loads(json_output)
            books = []

            for book_data in books_data:
                # 处理 authors 字段 - 确保是列表格式
                authors_data = book_data.get('authors', [])
                if isinstance(authors_data, str):
                    # 如果是字符串，按 ' & ' 分割成列表
                    authors_list = [author.strip() for author in authors_data.split(' & ')]
                elif isinstance(authors_data, list):
                    authors_list = authors_data
                else:
                    authors_list = []
                
                book_info = {
                    'calibre_id': book_data.get('id', 0),
                    'title': book_data.get('title', ''),
                    'authors': authors_list,
                    'author': ', '.join(authors_list),
                    'publisher': book_data.get('publisher', ''),
                    'identifiers': book_data.get('identifiers', {}),
                    'isbn': book_data.get('identifiers', {}).get('isbn', ''),
                    'formats': book_data.get('formats', []),
                    'cover_url': '',  # calibredb 不直接提供封面 URL
                    'raw_data': book_data
                }
                books.append(book_info)

            return books
        except json.JSONDecodeError as e:
            self.logger.error(f"解析 JSON 输出失败: {str(e)}")
            return []
        except Exception as e:
            self.logger.error(f"处理书籍列表失败: {str(e)}")
            return []

    def search_book(self,
                    title: str,
                    author: Optional[str] = None,
                    isbn: Optional[str] = None,
                    verbose: bool = False) -> List[Dict[str, Any]]:
        """
        搜索书籍

        Args:
            title: 书名
            author: 作者（可选）
            isbn: ISBN（可选）
            verbose: 是否打印 calibredb 命令（可选）

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            # 构建搜索查询
            query_parts = []

            # 如果有 ISBN，优先使用 ISBN 搜索
            if isbn:
                self.logger.info(f"使用 ISBN 搜索: {isbn}")
                query_parts.append(f"identifier:isbn:{isbn}")
            else:
                # 使用标题和作者搜索
                if title:
                    # 对标题进行处理，移除副标题和特殊字符
                    clean_title = re.sub(r'[:\(\)\[\]\{\}].*$', '',
                                         title).strip()
                    # 使用模糊匹配
                    query_parts.append(f'title:~"{clean_title}"')

                if author:
                    query_parts.append(f'author:~"{author}"')

            if not query_parts:
                self.logger.warning("搜索查询为空")
                return []

            search_query = " and ".join(query_parts)
            self.logger.info(f"搜索书籍: {search_query}")

            # 执行搜索命令
            search_args = ['search', search_query]

            if verbose:
                command = ['calibredb'] + search_args
                if self.server_url:
                    command.extend(['--library-path', self.server_url])
                if self.username:
                    command.extend(['--username', self.username])
                if self.password:
                    command.extend(['--password', '***'])  # 不显示真实密码
                print(f"calibredb 命令: {' '.join(command)}")

            stdout, stderr, returncode = self._execute_calibredb_command(
                search_args)

            if returncode != 0:
                self.logger.error(f"搜索命令失败: {stderr}")
                return []

            # 解析搜索结果
            book_ids = self._parse_search_results(stdout)

            if not book_ids:
                self.logger.info(f"未找到匹配的书籍: {search_query}")
                return []

            self.logger.info(f"搜索成功，找到 {len(book_ids)} 个结果")

            # 获取书籍详细信息
            return self._get_books_info(book_ids)

        except Exception as e:
            self.logger.error(f"搜索书籍失败: {str(e)}")
            return []

    def _get_books_info(self, book_ids: List[int]) -> List[Dict[str, Any]]:
        """
        批量获取书籍详细信息

        Args:
            book_ids: 书籍 ID 列表

        Returns:
            List[Dict[str, Any]]: 书籍详细信息列表
        """
        if not book_ids:
            return []

        try:
            # 构建 ID 搜索查询
            id_query = " or ".join([f"id:{book_id}" for book_id in book_ids])

            # 使用 calibredb list 获取详细信息
            list_args = [
                'list', '--for-machine', '--fields', 'all', '--search',
                id_query
            ]

            stdout, stderr, returncode = self._execute_calibredb_command(
                list_args)

            if returncode != 0:
                self.logger.error(f"获取书籍信息失败: {stderr}")
                return []

            return self._parse_book_list(stdout)

        except Exception as e:
            self.logger.error(f"批量获取书籍信息失败: {str(e)}")
            return []

    def get_book_info(self, book_id: int) -> Optional[Dict[str, Any]]:
        """
        获取单个书籍详细信息

        Args:
            book_id: 书籍 ID

        Returns:
            Optional[Dict[str, Any]]: 书籍详细信息，获取失败则返回 None
        """
        books = self._get_books_info([book_id])
        return books[0] if books else None

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
        try:
            # 搜索书籍
            books = self.search_book(title, author, isbn)
            if not books:
                return None

            # 如果只有一个结果，直接返回
            if len(books) == 1:
                return books[0]

            # 多个结果时，计算最佳匹配
            best_match = None
            best_score = 0.0

            for book in books:
                score = self._calculate_match_score(book, title, author, isbn)
                if score > best_score and score >= self.match_threshold:
                    best_score = score
                    best_match = book

            if best_match:
                self.logger.info(f"找到最佳匹配: {best_match['title']} "
                                 f"(匹配度: {best_score:.2f})")
            else:
                self.logger.info(f"未找到满足阈值的匹配书籍 "
                                 f"(阈值: {self.match_threshold})")

            return best_match

        except Exception as e:
            self.logger.error(f"查找最佳匹配失败: {str(e)}")
            return None

    def _calculate_match_score(self, book: Dict[str, Any], title: str,
                               author: Optional[str],
                               isbn: Optional[str]) -> float:
        """
        计算书籍匹配分数

        Args:
            book: 书籍信息
            title: 目标书名
            author: 目标作者
            isbn: 目标ISBN

        Returns:
            float: 匹配分数 (0.0-1.0)
        """
        score = 0.0

        # ISBN 匹配权重最高
        if isbn and book.get('isbn'):
            if isbn == book['isbn']:
                score += 0.6

        # 标题匹配
        if title and book.get('title'):
            title_similarity = self._calculate_similarity(title, book['title'])
            score += title_similarity * 0.3

        # 作者匹配
        if author and book.get('author'):
            author_similarity = self._calculate_similarity(
                author, book['author'])
            score += author_similarity * 0.1

        return min(score, 1.0)

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
        try:
            if not os.path.exists(file_path):
                self.logger.error(f"文件不存在: {file_path}")
                return None

            self.logger.info(f"上传书籍文件: {file_path}")

            # 构建 calibredb add 命令
            add_args = ['add', file_path]

            # 添加元数据参数
            if metadata:
                if metadata.get('title'):
                    add_args.extend(['--title', metadata['title']])

                if metadata.get('authors'):
                    authors = metadata['authors']
                    if isinstance(authors, list):
                        authors_str = ', '.join(authors)
                    else:
                        authors_str = str(authors)
                    add_args.extend(['--authors', authors_str])

                if metadata.get('isbn'):
                    add_args.extend(['--isbn', metadata['isbn']])

                if metadata.get('tags'):
                    tags = metadata['tags']
                    if isinstance(tags, list):
                        tags_str = ', '.join(tags)
                    else:
                        tags_str = str(tags)
                    add_args.extend(['--tags', tags_str])

                if metadata.get('series'):
                    add_args.extend(['--series', metadata['series']])

                if metadata.get('series_index'):
                    add_args.extend(
                        ['--series-index',
                         str(metadata['series_index'])])

                # 处理标识符
                if metadata.get('identifiers'):
                    identifiers = metadata['identifiers']
                    for key, value in identifiers.items():
                        if value:
                            add_args.extend(['--identifier', f'{key}:{value}'])

            # 设置自动合并策略：如果存在重复，合并到现有记录
            add_args.extend(['--automerge', 'overwrite'])

            # 执行添加命令
            stdout, stderr, returncode = self._execute_calibredb_command(
                add_args)

            if returncode != 0:
                self.logger.error(f"上传书籍失败: {stderr}")
                return None

            # 从输出中提取书籍 ID
            # calibredb add 的输出格式通常是 "Added book ids: 123"
            book_id = self._extract_book_id_from_add_output(stdout)

            if book_id:
                self.logger.info(f"成功上传书籍: {os.path.basename(file_path)}, "
                                 f"Calibre ID: {book_id}")
                
                # 检查是否需要更新 ISBN：如果上传时没有提供 ISBN，尝试从 Calibre 获取
                self._update_isbn_if_empty(book_id, metadata)
                
                return book_id
            else:
                self.logger.warning(f"无法从输出中提取书籍 ID: {stdout}")
                return None

        except Exception as e:
            self.logger.error(f"上传书籍失败: {str(e)}")
            return None

    def _extract_book_id_from_add_output(self, output: str) -> Optional[int]:
        """
        从 calibredb add 输出中提取书籍 ID

        Args:
            output: calibredb add 的输出

        Returns:
            Optional[int]: 提取到的书籍 ID，提取失败则返回 None
        """
        try:
            # 查找各种可能的输出格式
            patterns = [
                r'Added book ids?:\s*(\d+)',           # 英文: Added book ids: 123
                r'Book id of imported book:\s*(\d+)',   # 英文: Book id of imported book: 123
                r'已加入的书籍id:\s*(\d+)',              # 中文: 已加入的书籍id: 1420
                r'书籍id:\s*(\d+)',                     # 简化中文: 书籍id: 1420
                r'id:\s*(\d+)',                        # 更简化: id: 1420
            ]
            
            for pattern in patterns:
                match = re.search(pattern, output, re.IGNORECASE)
                if match:
                    return int(match.group(1))

            return None
        except Exception as e:
            self.logger.error(f"解析书籍 ID 失败: {str(e)}")
            return None

    def _update_isbn_if_empty(self, book_id: int, original_metadata: Optional[Dict[str, Any]]) -> None:
        """
        如果原始元数据中 ISBN 为空，尝试从 Calibre 获取 ISBN 并更新数据库
        
        Args:
            book_id: Calibre 中的书籍 ID
            original_metadata: 上传时使用的原始元数据
        """
        try:
            # 检查原始元数据中是否有 ISBN
            has_original_isbn = (
                original_metadata and 
                original_metadata.get('isbn') and 
                str(original_metadata['isbn']).strip()
            )
            
            if has_original_isbn:
                # 原始数据有 ISBN，无需更新
                return
            
            # 从 Calibre 获取书籍信息
            book_info = self.get_book_info(book_id)
            if not book_info:
                self.logger.warning(f"无法从 Calibre 获取书籍信息: {book_id}")
                return
            
            # 检查 Calibre 中是否有 ISBN 信息
            calibre_isbn = None
            
            # 先检查 ISBN 字段
            if book_info.get('isbn'):
                calibre_isbn = str(book_info['isbn']).strip()
            
            # 如果没有，检查 identifiers 中的 isbn
            if not calibre_isbn and book_info.get('identifiers'):
                identifiers = book_info['identifiers']
                if isinstance(identifiers, dict) and identifiers.get('isbn'):
                    calibre_isbn = str(identifiers['isbn']).strip()
            
            if not calibre_isbn:
                self.logger.debug(f"Calibre 中也没有 ISBN 信息: {book_id}")
                return
            
            # 获取豆瓣书籍信息并更新 ISBN
            douban_id = None
            if original_metadata and original_metadata.get('identifiers'):
                douban_id = original_metadata['identifiers'].get('douban')
            
            if douban_id:
                self._update_douban_book_isbn(douban_id, calibre_isbn)
                self.logger.info(f"已从 Calibre 更新豆瓣书籍 ISBN: {douban_id} -> {calibre_isbn}")
            
        except Exception as e:
            self.logger.error(f"更新 ISBN 时出错: {str(e)}")
    
    def _update_douban_book_isbn(self, douban_id: str, isbn: str) -> None:
        """
        更新豆瓣书籍的 ISBN（占位方法，实际逻辑在 UploadStage 中实现）
        
        Args:
            douban_id: 豆瓣书籍 ID
            isbn: 新的 ISBN
        """
        # 实际的 ISBN 更新逻辑在 UploadStage._update_isbn_from_calibre 中实现
        # 这里保留方法是为了保持接口完整性
        self.logger.debug(f"ISBN 更新请求: douban_id={douban_id}, isbn={isbn}")
        self.logger.debug("实际 ISBN 更新将在 UploadStage 中处理")

    def update_book_isbn(self, book_id: int, isbn: str) -> bool:
        """
        更新 Calibre 中书籍的 ISBN

        Args:
            book_id: 书籍 ID
            isbn: 新的 ISBN

        Returns:
            bool: 更新是否成功
        """
        try:
            self.logger.info(f"更新 Calibre 书籍 ISBN: ID={book_id}, ISBN={isbn}")

            # 使用 calibredb set_metadata 命令更新 ISBN
            set_args = [
                'set_metadata',
                str(book_id),
                '--field', f'isbn:{isbn}'
            ]

            stdout, stderr, returncode = self._execute_calibredb_command(
                set_args)

            if returncode != 0:
                self.logger.error(f"更新 ISBN 失败: {stderr}")
                return False

            self.logger.info(f"成功更新书籍 ISBN: ID={book_id}, ISBN={isbn}")
            return True

        except Exception as e:
            self.logger.error(f"更新书籍 ISBN 失败: {str(e)}")
            return False
