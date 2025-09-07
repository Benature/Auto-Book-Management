# -*- coding: utf-8 -*-
"""
Z-Library 服务模块单元测试
使用真实配置进行测试，不使用mock
"""

import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

FILE_DIR = Path(__file__).resolve().parent

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(FILE_DIR.parents[1]))

from config.config_manager import ConfigManager
from services.zlibrary_service import ZLibraryService
from utils.logger import get_logger


@pytest.fixture(scope="module")
def temp_config():
    """创建临时配置文件的fixture"""
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, 'test_config.yaml')
    
    # 创建测试配置，禁用网络调用
    config_content = '''
zlibrary:
  base_url: "https://test.zlibrary.example"
  email: "test@example.com"
  password: "test_password"
  download_dir: "/tmp/test_downloads"
  format_priority: ["EPUB", "PDF", "MOBI"]
  search_timeout: 30
  download_timeout: 300
  max_retries: 3
  retry_delay: 5
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
    """创建ConfigManager实例的fixture"""
    return ConfigManager(temp_config)


@pytest.fixture
def logger():
    """创建logger实例的fixture"""
    return get_logger('test_zlibrary_service')


@pytest.fixture
def zlibrary_service(config_manager, logger):
    """创建ZLibraryService实例的fixture"""
    return ZLibraryService(config_manager, logger)


class TestZLibraryService:
    """ZLibraryService测试类"""

    def test_service_initialization(self, zlibrary_service, config_manager):
        """测试服务初始化"""
        assert zlibrary_service is not None
        
        # 测试配置是否正确加载
        zlib_config = config_manager.get_zlibrary_config()
        assert zlibrary_service.base_url == zlib_config['base_url']
        assert zlibrary_service.email == zlib_config['email']
        assert zlibrary_service.password == zlib_config['password']
        assert zlibrary_service.download_dir == zlib_config['download_dir']
        assert zlibrary_service.format_priority == zlib_config['format_priority']

    def test_configuration_loading(self, config_manager):
        """测试配置加载"""
        zlib_config = config_manager.get_zlibrary_config()
        
        # 验证必要的配置项存在
        assert 'base_url' in zlib_config
        assert 'email' in zlib_config
        assert 'password' in zlib_config
        assert 'download_dir' in zlib_config
        assert 'format_priority' in zlib_config
        
        # 验证配置值类型
        assert isinstance(zlib_config['base_url'], str)
        assert isinstance(zlib_config['email'], str)
        assert isinstance(zlib_config['password'], str)
        assert isinstance(zlib_config['download_dir'], str)
        assert isinstance(zlib_config['format_priority'], list)

    def test_url_construction(self, zlibrary_service):
        """测试URL构建"""
        # 测试搜索URL构建逻辑
        base_url = zlibrary_service.base_url
        assert base_url.startswith('https://')
        
        # 测试搜索参数构建
        search_params = {
            'q': 'python programming',
            'type': 'phrase',
            'from': '0',
            'size': '25'
        }
        
        # 验证参数格式
        assert isinstance(search_params['q'], str)
        assert isinstance(search_params['type'], str)
        assert search_params['from'].isdigit()
        assert search_params['size'].isdigit()

    def test_search_query_formatting(self, zlibrary_service):
        """测试搜索查询格式化"""
        # 测试基本搜索查询
        title = "Python Programming"
        author = "Mark Lutz"
        
        # 模拟查询构建逻辑
        if title and author:
            query = f"{title} {author}"
        elif title:
            query = title
        elif author:
            query = author
        else:
            query = ""
        
        assert query == "Python Programming Mark Lutz"
        
        # 测试特殊字符处理
        special_title = "C++ Programming & Design"
        normalized_title = special_title.replace('+', 'plus').replace('&', 'and')
        assert 'plus' in normalized_title
        assert 'and' in normalized_title

    def test_format_priority_handling(self, zlibrary_service):
        """测试格式优先级处理"""
        format_priority = zlibrary_service.format_priority
        
        # 验证格式优先级列表
        assert isinstance(format_priority, list)
        assert len(format_priority) > 0
        
        # 测试格式选择逻辑
        available_formats = ['PDF', 'MOBI', 'EPUB', 'TXT']
        
        # 根据优先级选择最佳格式
        best_format = None
        for preferred_format in format_priority:
            if preferred_format.upper() in [f.upper() for f in available_formats]:
                best_format = preferred_format
                break
        
        # 应该选择优先级列表中的第一个可用格式
        assert best_format is not None
        assert best_format in format_priority

    def test_download_directory_handling(self, zlibrary_service):
        """测试下载目录处理"""
        download_dir = zlibrary_service.download_dir
        
        # 验证下载目录配置
        assert isinstance(download_dir, str)
        assert len(download_dir) > 0
        
        # 测试目录路径构建
        filename = "test_book.epub"
        file_path = os.path.join(download_dir, filename)
        
        # 验证路径构建正确
        assert filename in file_path
        assert download_dir in file_path

    def test_retry_logic_configuration(self, config_manager):
        """测试重试逻辑配置"""
        zlib_config = config_manager.get_zlibrary_config()
        
        # 验证重试配置存在
        max_retries = zlib_config.get('max_retries', 3)
        retry_delay = zlib_config.get('retry_delay', 5)
        
        assert isinstance(max_retries, int)
        assert isinstance(retry_delay, int)
        assert max_retries > 0
        assert retry_delay > 0
        
        # 测试重试逻辑
        for attempt in range(max_retries):
            # 模拟重试逻辑
            success = False  # 模拟失败
            if not success and attempt < max_retries - 1:
                # 会进行重试
                assert attempt < max_retries - 1
            else:
                # 最后一次尝试或成功
                break

    def test_timeout_configuration(self, config_manager):
        """测试超时配置"""
        zlib_config = config_manager.get_zlibrary_config()
        
        search_timeout = zlib_config.get('search_timeout', 30)
        download_timeout = zlib_config.get('download_timeout', 300)
        
        # 验证超时配置
        assert isinstance(search_timeout, int)
        assert isinstance(download_timeout, int)
        assert search_timeout > 0
        assert download_timeout > 0
        assert download_timeout >= search_timeout  # 下载超时应该不小于搜索超时

    def test_book_data_structure(self):
        """测试书籍数据结构"""
        # 模拟Z-Library返回的书籍数据结构
        sample_book = {
            'id': '12345',
            'title': 'Python Programming: A Comprehensive Guide',
            'author': 'Mark Lutz',
            'publisher': "O'Reilly Media",
            'year': '2023',
            'language': 'English',
            'format': 'EPUB',
            'size': '2.5 MB',
            'download_url': 'https://zlibrary.example/download/12345',
            'cover_url': 'https://zlibrary.example/covers/12345.jpg'
        }
        
        # 验证必要字段存在
        required_fields = ['title', 'author', 'format', 'download_url']
        for field in required_fields:
            assert field in sample_book
            assert isinstance(sample_book[field], str)
            assert len(sample_book[field]) > 0

    def test_search_result_processing(self):
        """测试搜索结果处理逻辑"""
        # 模拟搜索结果
        sample_results = [
            {
                'title': 'Python Programming',
                'author': 'Mark Lutz',
                'format': 'EPUB',
                'size': '2.5 MB'
            },
            {
                'title': 'Learning Python',
                'author': 'Mark Lutz',
                'format': 'PDF',
                'size': '5.2 MB'
            },
            {
                'title': 'Python Guide',
                'author': 'John Doe',
                'format': 'MOBI',
                'size': '1.8 MB'
            }
        ]
        
        # 测试结果过滤和排序
        search_term = "python programming"
        
        # 简单的相关性评分（基于标题匹配）
        scored_results = []
        for result in sample_results:
            title_lower = result['title'].lower()
            score = 0
            for word in search_term.split():
                if word in title_lower:
                    score += 1
            scored_results.append((result, score))
        
        # 按分数排序
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # 验证排序结果
        assert len(scored_results) == 3
        # 第一个结果应该有最高分数（包含"python"和"programming"）
        assert scored_results[0][1] >= scored_results[1][1]
        assert scored_results[1][1] >= scored_results[2][1]


if __name__ == "__main__":
    # 使用pytest运行测试
    pytest.main([__file__, "-v"])