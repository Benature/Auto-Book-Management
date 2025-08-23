# -*- coding: utf-8 -*-

"""
豆瓣爬虫模块单元测试
"""

import unittest
from unittest.mock import patch, MagicMock
import json
import os
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from scrapers.douban_scraper import DoubanScraper


class TestDoubanScraper(unittest.TestCase):
    """豆瓣爬虫测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.cookies = {
            'bid': 'test_bid',
            'dbcl2': 'test_dbcl2',
            'ck': 'test_ck'
        }
        self.user_id = 'test_user_id'
        self.scraper = DoubanScraper(
            cookies=self.cookies,
            user_id=self.user_id,
            max_books=10,
            request_delay=0.01  # 测试时使用较短的延迟
        )
    
    @patch('scrapers.douban_scraper.requests.get')
    def test_test_connection(self, mock_get):
        """测试连接测试功能"""
        # 模拟成功响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><title>豆瓣读书</title></html>'
        mock_get.return_value = mock_response
        
        # 测试连接成功
        result = self.scraper.test_connection()
        self.assertTrue(result)
        mock_get.assert_called_once_with(
            'https://book.douban.com/',
            cookies=self.cookies,
            headers=self.scraper.headers,
            timeout=10
        )
        
        # 模拟失败响应
        mock_get.reset_mock()
        mock_response.status_code = 403
        result = self.scraper.test_connection()
        self.assertFalse(result)
    
    @patch('scrapers.douban_scraper.requests.get')
    def test_get_wish_list(self, mock_get):
        """测试获取想读书单功能"""
        # 模拟书单页面响应
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        
        # 创建模拟的书单 HTML
        with open(os.path.join(os.path.dirname(__file__), 'fixtures/douban_wishlist.html'), 'r', encoding='utf-8') as f:
            mock_list_response.text = f.read()
        
        # 模拟书籍详情页面响应
        mock_detail_response = MagicMock()
        mock_detail_response.status_code = 200
        
        # 创建模拟的书籍详情 HTML
        with open(os.path.join(os.path.dirname(__file__), 'fixtures/douban_book_detail.html'), 'r', encoding='utf-8') as f:
            mock_detail_response.text = f.read()
        
        # 设置 mock_get 在不同调用时返回不同的响应
        mock_get.side_effect = [mock_list_response, mock_detail_response]
        
        # 测试获取书单
        books = self.scraper.get_wish_list()
        
        # 验证结果
        self.assertEqual(len(books), 1)  # 模拟数据中只有一本书
        book = books[0]
        self.assertEqual(book['title'], '深入理解计算机系统')
        self.assertEqual(book['author'], '[美] Randal E. Bryant / David O'Hallaron')
        self.assertEqual(book['douban_id'], '26912767')
        self.assertEqual(book['isbn'], '9787111544937')
    
    @patch('scrapers.douban_scraper.requests.get')
    def test_get_book_details(self, mock_get):
        """测试获取书籍详情功能"""
        # 模拟书籍详情页面响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        # 创建模拟的书籍详情 HTML
        with open(os.path.join(os.path.dirname(__file__), 'fixtures/douban_book_detail.html'), 'r', encoding='utf-8') as f:
            mock_response.text = f.read()
        
        mock_get.return_value = mock_response
        
        # 测试获取书籍详情
        book_url = 'https://book.douban.com/subject/26912767/'
        book_info = self.scraper.get_book_details(book_url)
        
        # 验证结果
        self.assertEqual(book_info['title'], '深入理解计算机系统')
        self.assertEqual(book_info['author'], '[美] Randal E. Bryant / David O'Hallaron')
        self.assertEqual(book_info['isbn'], '9787111544937')
        self.assertEqual(book_info['publisher'], '机械工业出版社')
        self.assertEqual(book_info['publish_date'], '2016-11')
    
    @patch('scrapers.douban_scraper.requests.get')
    def test_parse_book_list(self, mock_get):
        """测试解析书单功能"""
        # 创建模拟的书单 HTML
        with open(os.path.join(os.path.dirname(__file__), 'fixtures/douban_wishlist.html'), 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 测试解析书单
        book_items = self.scraper._parse_book_list(html_content)
        
        # 验证结果
        self.assertEqual(len(book_items), 1)  # 模拟数据中只有一本书
        self.assertEqual(book_items[0]['title'], '深入理解计算机系统')
        self.assertEqual(book_items[0]['url'], 'https://book.douban.com/subject/26912767/')
        self.assertEqual(book_items[0]['cover_url'], 'https://img2.doubanio.com/view/subject/s/public/s29195878.jpg')
    
    @patch('scrapers.douban_scraper.requests.get')
    def test_parse_book_details(self, mock_get):
        """测试解析书籍详情功能"""
        # 创建模拟的书籍详情 HTML
        with open(os.path.join(os.path.dirname(__file__), 'fixtures/douban_book_detail.html'), 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # 测试解析书籍详情
        book_info = self.scraper._parse_book_details(html_content)
        
        # 验证结果
        self.assertEqual(book_info['title'], '深入理解计算机系统')
        self.assertEqual(book_info['author'], '[美] Randal E. Bryant / David O'Hallaron')
        self.assertEqual(book_info['isbn'], '9787111544937')
        self.assertEqual(book_info['publisher'], '机械工业出版社')
        self.assertEqual(book_info['publish_date'], '2016-11')


if __name__ == '__main__':
    # 创建测试数据目录
    fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
    os.makedirs(fixtures_dir, exist_ok=True)
    
    # 创建模拟的书单 HTML 文件
    wishlist_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>豆瓣读书 - 想读</title>
    </head>
    <body>
        <ul class="interest-list">
            <li class="subject-item">
                <div class="pic">
                    <a href="https://book.douban.com/subject/26912767/">
                        <img src="https://img2.doubanio.com/view/subject/s/public/s29195878.jpg" alt="深入理解计算机系统">
                    </a>
                </div>
                <div class="info">
                    <h2 class="title">
                        <a href="https://book.douban.com/subject/26912767/">深入理解计算机系统</a>
                    </h2>
                    <div class="pub">[美] Randal E. Bryant / David O'Hallaron / 机械工业出版社 / 2016-11</div>
                </div>
            </li>
        </ul>
    </body>
    </html>
    '''
    
    with open(os.path.join(fixtures_dir, 'douban_wishlist.html'), 'w', encoding='utf-8') as f:
        f.write(wishlist_html)
    
    # 创建模拟的书籍详情 HTML 文件
    book_detail_html = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>深入理解计算机系统 (豆瓣)</title>
    </head>
    <body>
        <div id="wrapper">
            <h1>深入理解计算机系统</h1>
            <div id="info">
                作者: [美] Randal E. Bryant / David O'Hallaron<br>
                出版社: 机械工业出版社<br>
                出版年: 2016-11<br>
                ISBN: 9787111544937
            </div>
        </div>
    </body>
    </html>
    '''
    
    with open(os.path.join(fixtures_dir, 'douban_book_detail.html'), 'w', encoding='utf-8') as f:
        f.write(book_detail_html)
    
    unittest.main()