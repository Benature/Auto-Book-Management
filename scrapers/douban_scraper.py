# -*- coding: utf-8 -*-
"""
豆瓣爬虫

负责爬取豆瓣「想读」书单。
"""

import requests
from bs4 import BeautifulSoup
import time
import re
import random
from typing import List, Dict, Any, Optional, Tuple

from utils.logger import get_logger
from db.models import BookStatus
import http.client
from rich.progress import Progress

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59'
]


class DoubanScraper:
    """豆瓣爬虫类"""

    def __init__(self,
                 cookie: str,
                 user_agent: str = None,
                 max_pages: int = None,
                 user_id: int | str = None,
                 proxy: str = None):
        """
        初始化爬虫
        
        Args:
            cookie: 豆瓣网站 Cookie
            user_agent: 用户代理字符串
            max_pages: 最大爬取页数，0 表示不限制
            proxy: 代理服务器地址，格式为 http://host:port 或 socks5://host:port
        """
        self.logger = get_logger("douban_scraper")
        self.cookie = cookie
        self.max_pages = max_pages
        self.proxy = proxy

        assert cookie is not None, "cookie 不可为空"
        self.user_id = self.get_user_id(user_id, cookie)
        self.base_url = f"https://book.douban.com/people/{user_id}/"

        self.session = requests.Session()
        if self.proxy:
            self.session.proxies = {'http': self.proxy, 'https': self.proxy}
        self.session.headers.update({
            'Cookie':
            cookie,
            'User-Agent':
            user_agent or random.choice(USER_AGENTS),
            'Accept':
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language':
            'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding':
            'gzip, deflate, br',
            'Connection':
            'keep-alive',
            'Cache-Control':
            'max-age=0',
            'Sec-Ch-Ua':
            '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'Sec-Ch-Ua-Mobile':
            '?0',
            'Sec-Ch-Ua-Platform':
            '"macOS"',
            'Sec-Fetch-Dest':
            'document',
            'Sec-Fetch-Mode':
            'navigate',
            'Sec-Fetch-Site':
            'same-origin',
            'Sec-Fetch-User':
            '?1',
            'Upgrade-Insecure-Requests':
            '1',
            'Referer':
            self.base_url
        })

        # self.headers = {
        #     'Cookie': cookie,
        #     'Accept':
        #     'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        #     'Referer': self.base_url
        # }
        self.session = requests.Session()
        # self.session.headers.update(self.headers)

    def get_user_id(self, user_id: str, cookie: str) -> str:
        if user_id is not None:
            return str(user_id)
        user_id = None
        if 'dbcl2=' in cookie:
            match = re.search(r'dbcl2=([^;]+)', cookie)
            if match:
                user_id = match.group(1).split(':')[0].strip("'\"")
        assert user_id, "cookie 缺少 user_id 信息（dbcl2）"
        return str(user_id)

    def get_wish_list(self) -> List[Dict[str, Any]]:
        """
        获取「想读」书单
        
        Returns:
            List[Dict[str, Any]]: 书籍信息列表
        """
        self.logger.info("开始爬取豆瓣「想读」书单")
        books = []
        page = 0
        has_next = True

        with Progress() as progress:
            page_task = progress.add_task(
                "页进度", total=self.max_pages if self.max_pages else None)
            item_task = progress.add_task(f"第{page}页条目")
            while has_next and (self.max_pages is None or self.max_pages == 0
                                or page < self.max_pages):
                page += 1
                url = f"https://book.douban.com/people/{self.user_id}/wish?start={(page-1)*15}&sort=time&rating=all&filter=all&mode=grid"
                try:
                    self.logger.info(f"爬取第 {page} 页: {url}")
                    # 随机延迟 3-7 秒
                    time.sleep(random.uniform(3, 7))
                    # 更新 User-Agent
                    self.session.headers.update(
                        {'User-Agent': random.choice(USER_AGENTS)})
                    response = self.session.get(url, timeout=15)
                    response.raise_for_status()
                    text = response.text
                except requests.RequestException as e:
                    self.logger.error(f"请求失败: {str(e)}")
                    break

                soup = BeautifulSoup(text, 'lxml')
                items = soup.select('.subject-item')

                if not items:
                    self.logger.info(f"第 {page} 页没有找到书籍，爬取结束")
                    has_next = False
                    break

                progress.update(item_task, total=len(items), completed=0)
                for item in items:
                    book_info = self.parse_book_info(item)
                    if book_info:
                        books.append(book_info)
                    progress.update(item_task, advance=1)
                # progress.remove_task(item_task)

                next_link = soup.select_one('span.next a')
                has_next = next_link is not None

                progress.update(page_task, advance=1)

                # 避免请求过于频繁
                time.sleep(random.uniform(1.5, 3.5))

        self.logger.info(f"爬取完成，共获取 {len(books)} 本书")
        return books

    def parse_book_info(self, item: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        解析书籍信息
        
        Args:
            item: BeautifulSoup 解析的书籍条目
            
        Returns:
            Optional[Dict[str, Any]]: 书籍信息字典，解析失败则返回 None
        """
        try:
            # 获取书名和链接
            title_element = item.select_one('div.info h2 a')
            if not title_element:
                return None

            title = title_element.get_text(strip=True)
            douban_url = title_element['href']
            douban_id = re.search(r'/subject/(\d+)/', douban_url).group(1)

            # 获取作者、出版社等信息
            pub_element = item.select_one('div.pub')
            pub_text = pub_element.get_text(strip=True) if pub_element else ''

            # 尝试解析作者、译者、出版社、出版日期
            author = ''
            translator = ''
            publisher = ''
            publish_date = ''

            if pub_text:
                # 通常格式为: 作者 / 译者 / 出版社 / 出版日期
                parts = [p.strip() for p in pub_text.split('/')]
                if len(parts) >= 1:
                    author = parts[0]
                if len(parts) >= 2 and '译' in parts[1]:
                    translator = parts[1]
                    parts.pop(1)  # 移除译者部分
                if len(parts) >= 2:
                    publisher = parts[-2]
                if len(parts) >= 3:
                    publish_date = parts[-1]

            # 获取评分
            rating_element = item.select_one('span.rating_nums')
            rating = float(rating_element.get_text(
                strip=True)) if rating_element else None

            # 获取封面图片
            cover_element = item.select_one('div.pic img')
            cover_url = cover_element['src'] if cover_element else ''

            # 构建书籍信息字典
            book_info = {
                'title': title,
                'author': author,
                'translator': translator,
                'publisher': publisher,
                'publish_date': publish_date,
                'douban_id': douban_id,
                'douban_url': douban_url,
                'douban_rating': rating,
                'cover_url': cover_url,
                'status': BookStatus.NEW
            }

            # 获取详细信息（ISBN 等）
            # detailed_info = self.get_book_detail(douban_url)
            # if detailed_info:
            #     book_info.update(detailed_info)

            return book_info

        except Exception as e:
            self.logger.error(f"解析书籍信息失败: {str(e)}")
            return None

    def get_book_detail(self,
                        book_douban_url: str) -> Optional[Dict[str, Any]]:
        """
        获取书籍详细信息
        
        Args:
            book_douban_url: 豆瓣书籍 URL
            
        Returns:
            Optional[Dict[str, Any]]: 书籍详细信息字典，获取失败则返回 None
        """
        try:
            self.logger.debug(f"获取书籍详情: {book_douban_url}")
            # 随机延迟 2-5 秒
            time.sleep(random.uniform(2, 5))
            # 更新 User-Agent
            self.headers['User-Agent'] = random.choice(USER_AGENTS)
            response = requests.get(book_douban_url,
                                    headers=self.headers,
                                    timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')

            # 获取 ISBN
            isbn = ''
            info_text = soup.select_one('#info').get_text() if soup.select_one(
                '#info') else ''
            isbn_match = re.search(r'ISBN:\s*(\d+)', info_text)
            if isbn_match:
                isbn = isbn_match.group(1)

            # 获取原作名
            original_title = ''
            original_title_match = re.search(r'原作名:\s*([^\n]+)', info_text)
            if original_title_match:
                original_title = original_title_match.group(1).strip()

            # 获取副标题
            subtitle = ''
            subtitle_match = re.search(r'副标题:\s*([^\n]+)', info_text)
            if subtitle_match:
                subtitle = subtitle_match.group(1).strip()

            # 获取内容简介
            description = ''
            intro_element = soup.select_one('div.intro')
            if intro_element:
                description = intro_element.get_text(strip=True)

            # 避免请求过于频繁
            time.sleep(random.uniform(0.8, 2.0))

            return {
                'isbn': isbn,
                'original_title': original_title,
                'subtitle': subtitle,
                'description': description,
                'status': BookStatus.WITH_DETAIL,
            }

        except Exception as e:
            self.logger.error(f"获取书籍详情失败: {str(e)}")
            return None

    def run(self) -> List[Dict[str, Any]]:
        """
        执行爬虫任务
        
        Returns:
            List[Dict[str, Any]]: 爬取的书籍信息列表
        """
        self.logger.info("开始执行豆瓣爬虫任务")
        start_time = time.time()

        try:
            books = self.get_wish_list()
            elapsed_time = time.time() - start_time
            self.logger.info(
                f"爬虫任务完成，耗时 {elapsed_time:.2f} 秒，获取 {len(books)} 本书")
            return books
        except Exception as e:
            elapsed_time = time.time() - start_time
            self.logger.error(f"爬虫任务失败，耗时 {elapsed_time:.2f} 秒: {str(e)}")
            return []
