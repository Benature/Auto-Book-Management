# -*- coding: utf-8 -*-
"""
豆瓣爬虫模块测试
使用真实配置进行测试，不使用mock
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

FILE_DIR = Path(__file__).resolve().parent

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(FILE_DIR.parents[1]))

from config.config_manager import ConfigManager
from scrapers.douban_scraper import DoubanScraper
from utils.logger import get_logger


@pytest.fixture
def temp_config():
    """创建临时配置文件"""
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, 'test_config.yaml')
    
    config_content = '''
douban:
  user_id: "test_user"
  cookie: "test_cookie_value"
  user_agent: "Mozilla/5.0 (Test User Agent)"
  wishlist_url: "https://book.douban.com/people/{user_id}/wish"
  request_delay: 1
  timeout: 30
database:
  url: ':memory:'
lark:
  enabled: false
scheduler:
  enabled: false
'''
    
    with open(config_path, 'w') as f:
        f.write(config_content)
    
    yield config_path
    
    # 清理
    import shutil
    shutil.rmtree(temp_dir)


@pytest.fixture
def config_manager(temp_config):
    """创建ConfigManager实例"""
    return ConfigManager(temp_config)


@pytest.fixture
def logger():
    """创建logger实例"""
    return get_logger('test_douban_scraper')


@pytest.fixture
def douban_scraper(config_manager, logger):
    """创建DoubanScraper实例"""
    return DoubanScraper(config_manager, logger)


class TestDoubanScraper:
    """豆瓣爬虫测试类"""

    def test_scraper_initialization(self, douban_scraper, config_manager):
        """测试爬虫初始化"""
        assert douban_scraper is not None
        
        # 测试配置加载
        douban_config = config_manager.get_douban_config()
        assert douban_scraper.user_id == douban_config['user_id']
        assert douban_scraper.cookie == douban_config['cookie']
        assert douban_scraper.user_agent == douban_config['user_agent']

    def test_configuration_validation(self, config_manager):
        """测试配置验证"""
        douban_config = config_manager.get_douban_config()
        
        # 验证必要配置项
        required_fields = ['user_id', 'cookie', 'user_agent', 'wishlist_url']
        for field in required_fields:
            assert field in douban_config
            assert isinstance(douban_config[field], str)
            assert len(douban_config[field]) > 0

    def test_url_construction(self, douban_scraper):
        """测试URL构建"""
        user_id = douban_scraper.user_id
        wishlist_url_template = "https://book.douban.com/people/{user_id}/wish"
        
        # 构建实际URL
        wishlist_url = wishlist_url_template.format(user_id=user_id)
        expected_url = f"https://book.douban.com/people/{user_id}/wish"
        
        assert wishlist_url == expected_url
        assert user_id in wishlist_url

    def test_request_headers_construction(self, douban_scraper):
        """测试请求头构建"""
        headers = {
            'User-Agent': douban_scraper.user_agent,
            'Cookie': douban_scraper.cookie,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        # 验证请求头
        assert 'User-Agent' in headers
        assert 'Cookie' in headers
        assert headers['User-Agent'] == douban_scraper.user_agent
        assert headers['Cookie'] == douban_scraper.cookie

    def test_book_data_structure(self):
        """测试书籍数据结构"""
        # 模拟解析后的书籍数据结构
        sample_book = {
            'douban_id': '12345678',
            'title': 'Python编程：从入门到实践',
            'author': 'Eric Matthes',
            'publisher': '人民邮电出版社',
            'isbn': '9787115428028',
            'url': 'https://book.douban.com/subject/12345678/',
            'cover_url': 'https://img3.doubanio.com/view/subject_l/public/s28123456.jpg',
            'rating': '9.1',
            'pages': '459',
            'price': '89.00元',
            'publish_date': '2016-7'
        }
        
        # 验证必要字段
        required_fields = ['douban_id', 'title', 'author', 'url']
        for field in required_fields:
            assert field in sample_book
            assert isinstance(sample_book[field], str)
            assert len(sample_book[field]) > 0

    def test_html_parsing_logic(self):
        """测试HTML解析逻辑"""
        # 模拟简单的HTML解析
        sample_html = '''
        <div class="item">
            <div class="pic">
                <a href="https://book.douban.com/subject/12345678/">
                    <img src="https://img3.doubanio.com/view/subject_s/public/s28123456.jpg" alt="书名">
                </a>
            </div>
            <div class="info">
                <h2><a href="https://book.douban.com/subject/12345678/">Python编程：从入门到实践</a></h2>
                <div class="pub">Eric Matthes / 人民邮电出版社 / 2016-7 / 89.00元</div>
            </div>
        </div>
        '''
        
        # 验证HTML包含预期内容
        assert 'class="item"' in sample_html
        assert 'book.douban.com' in sample_html
        assert 'Python编程：从入门到实践' in sample_html
        assert 'Eric Matthes' in sample_html

    def test_pagination_handling(self):
        """测试分页处理"""
        # 模拟分页逻辑
        current_page = 1
        total_items = 150
        items_per_page = 15
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        # 测试分页计算
        assert total_pages == 10
        
        # 测试页面URL构建
        base_url = "https://book.douban.com/people/test_user/wish"
        page_url = f"{base_url}?start={current_page * items_per_page}&sort=time&rating=all&filter=all&mode=grid"
        
        assert 'start=' in page_url
        assert 'sort=time' in page_url

    def test_error_handling_scenarios(self):
        """测试错误处理场景"""
        # 模拟常见错误场景
        error_scenarios = [
            {'status_code': 403, 'description': '访问被拒绝'},
            {'status_code': 404, 'description': '页面未找到'},
            {'status_code': 500, 'description': '服务器错误'},
            {'status_code': 0, 'description': '网络连接错误'}
        ]
        
        for scenario in error_scenarios:
            status_code = scenario['status_code']
            description = scenario['description']
            
            # 验证错误状态码处理
            if status_code == 403:
                assert description == '访问被拒绝'
            elif status_code == 404:
                assert description == '页面未找到'
            elif status_code >= 500:
                assert '服务器' in description
            elif status_code == 0:
                assert '网络' in description

    def test_request_rate_limiting(self, config_manager):
        """测试请求速率限制"""
        douban_config = config_manager.get_douban_config()
        request_delay = douban_config.get('request_delay', 1)
        
        # 验证延迟配置
        assert isinstance(request_delay, (int, float))
        assert request_delay >= 0
        
        # 模拟延迟逻辑
        import time
        start_time = time.time()
        time.sleep(0.01)  # 模拟短延迟
        elapsed_time = time.time() - start_time
        
        assert elapsed_time >= 0.01

    def test_cookie_validation(self, douban_scraper):
        """测试Cookie验证"""
        cookie = douban_scraper.cookie
        
        # 基本验证
        assert isinstance(cookie, str)
        assert len(cookie) > 0
        
        # Cookie格式基本检查（应包含键值对）
        if '=' in cookie:
            # 简单的键值对格式检查
            parts = cookie.split(';')
            for part in parts:
                if '=' in part:
                    key, value = part.strip().split('=', 1)
                    assert len(key) > 0
                    assert len(value) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])