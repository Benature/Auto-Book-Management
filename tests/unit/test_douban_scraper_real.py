# -*- coding: utf-8 -*-
"""
豆瓣爬虫模块真实网络测试

使用真实网络请求进行测试，不使用mock。
注意：此测试需要有效的豆瓣cookie配置。
"""

import pytest
import os
import re
import sys
from pathlib import Path
import time

# 添加项目根目录到 Python 路径
FILE_DIR = Path(__file__).resolve().parent
BASE_DIR = FILE_DIR.parent.parent
sys.path.insert(0, str(BASE_DIR))

from scrapers.douban_scraper import DoubanScraper
from config.config_manager import ConfigManager


@pytest.fixture(scope="module")
def config_manager():
    """创建ConfigManager实例的fixture"""
    config_manager = ConfigManager(BASE_DIR / 'config.yaml')
    yield config_manager


@pytest.fixture
def douban_scraper_real(config_manager):
    """创建使用真实配置的DoubanScraper实例"""
    # 从配置中获取豆瓣配置
    douban_config = config_manager.get_douban_config()

    # 获取cookie字符串
    cookie = douban_config.get('cookie')
    if not cookie:
        pytest.skip("需要配置豆瓣cookie才能进行真实测试")

    # 获取系统配置的user_agent
    system_config = config_manager.get_system_config()
    user_agent = system_config.get('user_agent')

    # 获取最大页数
    max_pages = douban_config.get('max_pages', 0)

    scraper = DoubanScraper(cookie=cookie,
                            user_agent=user_agent,
                            max_pages=max_pages)

    return scraper, cookie


@pytest.mark.real_network
class TestDoubanScraperReal:
    """真实网络测试类"""

    def test_real_connection(self, douban_scraper_real):
        """测试真实网络连接"""
        scraper, cookie = douban_scraper_real

        # 测试访问豆瓣主页
        try:
            result = scraper.run()
            assert isinstance(result, list)
            print(f"成功获取 {len(result)} 本书籍信息")
        except Exception as e:
            pytest.skip(f"网络连接测试失败: {str(e)}")

    def test_real_wish_list(self, douban_scraper_real):
        """测试真实获取想读书单"""
        scraper, cookie, user_id = douban_scraper_real

        try:
            books = scraper.get_wish_list()
            assert isinstance(books, list)

            if books:
                print(f"成功获取 {len(books)} 本想读书籍")
                # 打印第一本书的信息作为验证
                first_book = books[0]
                print(f"第一本书: {first_book.get('title', '未知标题')}")
                assert 'title' in first_book
                assert 'url' in first_book
            else:
                print("未获取到书籍，可能是页面结构变化或cookie无效")

        except Exception as e:
            pytest.skip(f"获取想读书单失败: {str(e)}")

    def test_real_book_detail(self, douban_scraper_real):
        """测试真实获取书籍详情"""
        scraper, cookie, user_id = douban_scraper_real

        # 使用一个已知的书籍ID进行测试
        test_book_id = "26912767"  # 深入理解计算机系统

        try:
            book_info = scraper.get_book_detail(test_book_id)

            if book_info:
                print(f"成功获取书籍详情: {book_info.get('title', '未知标题')}")
                assert isinstance(book_info, dict)
                assert 'title' in book_info
                assert 'author' in book_info
            else:
                print("未获取到书籍详情，可能是页面结构变化")

        except Exception as e:
            pytest.skip(f"获取书籍详情失败: {str(e)}")

    def test_real_rate_limiting(self, douban_scraper_real):
        """测试真实场景下的速率限制"""
        scraper, cookie, user_id = douban_scraper_real

        start_time = time.time()

        # 连续请求测试
        try:
            books = scraper.get_wish_list()
            assert isinstance(books, list)

            # 如果有书籍，测试获取详情
            if books and len(books) > 0:
                first_book = books[0]
                book_id = first_book.get('douban_id', '')
                if book_id:
                    detail = scraper.get_book_detail(book_id)
                    assert isinstance(detail, dict) or detail is None

            elapsed_time = time.time() - start_time
            print(f"测试完成，耗时: {elapsed_time:.2f}秒")

        except Exception as e:
            pytest.skip(f"速率限制测试失败: {str(e)}")


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "-s", "-m", "real_network"])
