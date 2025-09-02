# -*- coding: utf-8 -*-
"""
Z-Library 服务模块单元测试
"""

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

FILE_DIR = Path(__file__).resolve().parent

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(FILE_DIR.parents[1]))

from config.config_manager import ConfigManager
from services.zlibrary_service import ZLibraryService


@pytest.fixture(scope="module")
def config_manager():
    """创建ConfigManager实例的fixture"""
    config_manager = ConfigManager(FILE_DIR.parents[1] / 'config.yaml')
    yield config_manager


@pytest.fixture
def zlibrary_service(config_manager):
    """创建ZLibraryService实例的fixture"""
    zlibrary_config = config_manager.get_zlibrary_config()
    email = zlibrary_config['username']
    password = zlibrary_config['password']
    download_dir = zlibrary_config['download_dir']
    preferred_formats = zlibrary_config['format_priority']

    # 创建测试下载目录
    os.makedirs(download_dir, exist_ok=True)

    service = ZLibraryService(email=email,
                              password=password,
                              download_dir=download_dir,
                              format_priority=preferred_formats)

    yield service, email, password, download_dir, preferred_formats

    # 清理测试下载目录
    if os.path.exists(download_dir):
        for file in os.listdir(download_dir):
            os.remove(os.path.join(download_dir, file))
        os.rmdir(download_dir)


# @patch('services.zlibrary_service.AsyncZlib')
# def test_init(mock_zlib_client, zlibrary_service):
#     """测试初始化功能"""
#     service, email, password, download_dir, preferred_formats = zlibrary_service

#     # 验证初始化参数
#     assert service.username == email
#     assert service.password == password
#     assert service.download_dir == Path(download_dir)
#     assert service.format_priority == preferred_formats

#     # 验证 AsyncZlib 被正确初始化
#     mock_zlib_client.assert_called_once_with()





@patch('services.zlibrary_service.AsyncZlib')
def test_search_books(mock_zlib_client, zlibrary_service):
    """测试搜索书籍功能"""
    service, _, _, _, _ = zlibrary_service

    # 模拟搜索结果
    mock_search_results = [{
        'id': '123456',
        'title': 'Test Book',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'year': '2022',
        'language': 'english',
        'extension': 'epub',
        'filesize': 1024,
        'md5': 'abc123',
        'cover_url': 'http://example.com/cover.jpg'
    }]

    mock_client_instance = mock_zlib_client.return_value
    # 添加search方法
    mock_client_instance.search = MagicMock(return_value=mock_search_results)

    # 测试使用标题搜索
    results = service.search_books(title='Test Book')
    assert results == mock_search_results
    mock_client_instance.search.assert_called_with(q='Test Book')

    # 测试使用标题和作者搜索
    mock_client_instance.search.reset_mock()
    results = service.search_books(title='Test Book', author='Test Author')
    assert results == mock_search_results
    mock_client_instance.search.assert_called_with(q='Test Book Test Author')

    # 测试使用 ISBN 搜索
    mock_client_instance.search.reset_mock()
    results = service.search_books(isbn='1234567890')
    assert results == mock_search_results
    mock_client_instance.search.assert_called_with(q='isbn:1234567890')


@patch('services.zlibrary_service.AsyncZlib')
def test_find_best_match(mock_zlib_client, zlibrary_service):
    """测试找到最佳匹配功能"""
    service, _, _, _, _ = zlibrary_service

    # 模拟搜索结果
    mock_search_results = [{
        'id': '123456',
        'title': 'Test Book',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'year': '2022',
        'language': 'english',
        'extension': 'epub',
        'filesize': 1024,
        'md5': 'abc123',
        'cover_url': 'http://example.com/cover.jpg'
    }, {
        'id': '789012',
        'title': 'Test Book Second Edition',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'year': '2023',
        'language': 'english',
        'extension': 'pdf',
        'filesize': 2048,
        'md5': 'def456',
        'cover_url': 'http://example.com/cover2.jpg'
    }]

    mock_client_instance = mock_zlib_client.return_value
    mock_client_instance.search.return_value = mock_search_results

    # 测试找到精确匹配
    best_match = service.find_best_match(title='Test Book',
                                         author='Test Author')
    assert best_match['id'] == '123456'

    # 测试找到部分匹配
    best_match = service.find_best_match(title='Test Book Second',
                                         author='Test Author')
    assert best_match['id'] == '789012'

    # 测试未找到匹配
    mock_client_instance.search.return_value = []
    best_match = service.find_best_match(title='Nonexistent Book',
                                         author='Unknown Author')
    assert best_match is None


@patch('services.zlibrary_service.AsyncZlib')
@patch('services.zlibrary_service.open', new_callable=mock_open)
@patch('services.zlibrary_service.os.path.exists')
def test_download_book(mock_exists, mock_file_open, mock_zlib_client,
                       zlibrary_service):
    """测试下载书籍功能"""
    service, _, _, download_dir, _ = zlibrary_service

    # 模拟书籍信息
    book_info = {
        'id': '123456',
        'title': 'Test Book',
        'author': 'Test Author',
        'extension': 'epub',
        'md5': 'abc123'
    }

    # 模拟文件不存在
    mock_exists.return_value = False

    # 模拟下载内容
    mock_content = b'test book content'
    mock_client_instance = mock_zlib_client.return_value
    mock_client_instance.download.return_value = mock_content

    # 测试下载书籍
    file_path = service.download_book(book_info)
    expected_path = os.path.join(download_dir, 'Test Book - Test Author.epub')
    assert file_path == expected_path

    # 验证下载调用
    mock_client_instance.download.assert_called_once_with('123456')

    # 验证文件写入
    mock_file_open.assert_called_once_with(expected_path, 'wb')
    mock_file_open().write.assert_called_once_with(mock_content)

    # 测试文件已存在的情况
    mock_exists.return_value = True
    mock_client_instance.download.reset_mock()
    mock_file_open.reset_mock()

    file_path = service.download_book(book_info)
    assert file_path == expected_path

    # 验证没有重新下载
    mock_client_instance.download.assert_not_called()
    mock_file_open.assert_not_called()


@patch('services.zlibrary_service.AsyncZlib')
def test_search_and_download(mock_zlib_client, zlibrary_service):
    """测试搜索并下载功能"""
    service, _, _, download_dir, _ = zlibrary_service

    # 模拟搜索结果
    mock_search_results = [{
        'id': '123456',
        'title': 'Test Book',
        'author': 'Test Author',
        'publisher': 'Test Publisher',
        'year': '2022',
        'language': 'english',
        'extension': 'epub',
        'filesize': 1024,
        'md5': 'abc123',
        'cover_url': 'http://example.com/cover.jpg'
    }]

    mock_client_instance = mock_zlib_client.return_value
    mock_client_instance.search.return_value = mock_search_results
    mock_client_instance.download.return_value = b'test book content'

    # 模拟文件不存在
    with patch('services.zlibrary_service.os.path.exists', return_value=False):
        # 模拟文件写入
        with patch('services.zlibrary_service.open', new_callable=mock_open):
            # 测试搜索并下载
            result = service.search_and_download(title='Test Book',
                                                 author='Test Author')

            assert result['success'] is True
            assert result['file_path'] == os.path.join(
                download_dir, 'Test Book - Test Author.epub')
            assert result['book_info']['id'] == '123456'

    # 测试搜索失败
    mock_client_instance.search.return_value = []
    result = service.search_and_download(title='Nonexistent Book',
                                         author='Unknown Author')

    assert result['success'] is False
    assert '未找到匹配的书籍' in result['error']


@patch('services.zlibrary_service.ZlibClient')
def test_select_best_format(mock_zlib_client, zlibrary_service):
    """测试选择最佳格式功能"""
    service, _, _, _, _ = zlibrary_service

    # 模拟不同格式的搜索结果
    mock_search_results = [{
        'id': '123456',
        'title': 'Test Book',
        'author': 'Test Author',
        'extension': 'pdf',
        'md5': 'abc123'
    }, {
        'id': '789012',
        'title': 'Test Book',
        'author': 'Test Author',
        'extension': 'epub',
        'md5': 'def456'
    }, {
        'id': '345678',
        'title': 'Test Book',
        'author': 'Test Author',
        'extension': 'mobi',
        'md5': 'ghi789'
    }]

    # 测试按照首选格式选择
    best_format = service._select_best_format(mock_search_results)
    assert best_format['id'] == '789012'  # epub 是首选格式

    # 测试没有首选格式时选择第一个
    service.format_priority = ['azw3', 'djvu']
    best_format = service._select_best_format(mock_search_results)
    assert best_format['id'] == '123456'  # 返回第一个结果

    # 测试空结果
    best_format = service._select_best_format([])
    assert best_format is None


# pytest不需要main函数
