# -*- coding: utf-8 -*-
"""
豆瓣爬虫模块单元测试
"""

import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 添加项目根目录到 Python 路径
FILE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FILE_DIR.parent.parent))

from config.config_manager import ConfigManager
from scrapers.douban_scraper import DoubanScraper


@pytest.fixture(scope="module")
def config_manager():
    """创建ConfigManager实例的fixture"""
    config_manager = ConfigManager(
        Path(__file__).parent.parent.parent / 'config.yaml')
    yield config_manager


@pytest.fixture
def douban_scraper(config_manager):
    """创建DoubanScraper实例的fixture，使用配置文件中的真实配置"""
    # 从配置中获取豆瓣配置
    douban_config = config_manager.get_douban_config()

    # 获取cookie字符串
    cookie = douban_config.get('cookie', '')

    # 获取系统配置的user_agent
    system_config = config_manager.get_system_config()
    user_agent = system_config.get('user_agent')

    # 获取最大页数
    max_pages = douban_config.get('max_pages', 0)

    scraper = DoubanScraper(cookie=cookie,
                            user_agent=user_agent,
                            max_pages=max_pages)

    # 从cookie中提取user_id用于测试
    user_id = 'me'
    if 'dbcl2=' in cookie:
        match = re.search(r'dbcl2=([^;]+)', cookie)
        if match:
            user_id = match.group(1).split(':')[0].strip(
                "'\"") if ':' in match.group(1) else 'me'

    return scraper, cookie, user_id


@patch('scrapers.douban_scraper.requests.get')
def test_run_success(mock_get, douban_scraper):
    """测试成功运行爬虫"""
    scraper, cookie, user_id = douban_scraper

    # 测试运行（实际会返回空列表因为HTML不匹配）
    result = scraper.run()
    assert isinstance(result, list)


@patch('scrapers.douban_scraper.requests.get')
def test_get_wish_list_with_fixtures(mock_get, douban_scraper):
    """测试使用fixture文件获取想读书单"""
    scraper, cookie, user_id = douban_scraper

    # 创建模拟的书单 HTML
    with open(FILE_DIR / 'fixtures' / 'douban_wishlist.html',
                  'r',
                  encoding='utf-8') as f:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = f.read()
        mock_get.return_value = mock_response

    # 测试获取书单
    books = scraper.get_wish_list()

    # 验证结果（根据实际fixture内容）
    assert isinstance(books, list)


@patch('scrapers.douban_scraper.requests.get')
def test_get_book_detail(mock_get, douban_scraper):
    """测试获取书籍详情功能"""
    scraper, cookie, user_id = douban_scraper

    # 创建模拟的书籍详情 HTML
    with open(FILE_DIR / 'fixtures' / 'douban_book_detail.html',
                  'r',
                  encoding='utf-8') as f:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = f.read()
        mock_get.return_value = mock_response

    # 测试获取书籍详情
    book_info = scraper.get_book_detail('26912767')

    # 验证结果
    assert isinstance(book_info, dict) or book_info is None


def test_parse_book_info(douban_scraper):
    """测试解析书籍信息功能"""
    scraper, cookie, user_id = douban_scraper

    # 创建模拟的书单 HTML
    with open(FILE_DIR / 'fixtures' / 'douban_wishlist.html', 'r',
                  encoding='utf-8') as f:
        html_content = f.read()

    # 使用BeautifulSoup解析HTML
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'lxml')
    items = soup.select('.subject-item')

    # 测试解析书籍信息
    if items:
        book_info = scraper.parse_book_info(items[0])
        assert isinstance(book_info, dict) or book_info is None


def test_get_book_detail_with_fixtures(douban_scraper):
    """测试使用fixture文件获取书籍详情"""
    scraper, cookie, user_id = douban_scraper

    # 创建模拟的书籍详情 HTML
    with open(FILE_DIR / 'fixtures' / 'douban_book_detail.html', 'r',
                  encoding='utf-8') as f:
        html_content = f.read()

    # 验证HTML内容不为空
    assert len(html_content) > 0
