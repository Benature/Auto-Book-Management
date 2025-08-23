# -*- coding: utf-8 -*-

"""
Z-Library 服务模块单元测试
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open
import json
import os
from pathlib import Path
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from services.zlibrary_service import ZLibraryService


class TestZLibraryService(unittest.TestCase):
    """Z-Library 服务测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.email = 'test@example.com'
        self.password = 'test_password'
        self.download_dir = 'test_downloads'
        self.preferred_formats = ['epub', 'mobi', 'pdf']
        
        # 创建测试下载目录
        os.makedirs(self.download_dir, exist_ok=True)
        
        self.service = ZLibraryService(
            email=self.email,
            password=self.password,
            download_dir=self.download_dir,
            preferred_formats=self.preferred_formats
        )
    
    def tearDown(self):
        """测试后清理"""
        # 清理测试下载目录
        if os.path.exists(self.download_dir):
            for file in os.listdir(self.download_dir):
                os.remove(os.path.join(self.download_dir, file))
            os.rmdir(self.download_dir)
    
    @patch('services.zlibrary_service.ZlibClient')
    def test_init(self, mock_zlib_client):
        """测试初始化功能"""
        # 验证初始化参数
        self.assertEqual(self.service.email, self.email)
        self.assertEqual(self.service.password, self.password)
        self.assertEqual(self.service.download_dir, self.download_dir)
        self.assertEqual(self.service.preferred_formats, self.preferred_formats)
        
        # 验证 ZlibClient 被正确初始化
        mock_zlib_client.assert_called_once_with(
            email=self.email,
            password=self.password
        )
    
    @patch('services.zlibrary_service.ZlibClient')
    def test_test_connection(self, mock_zlib_client):
        """测试连接测试功能"""
        # 模拟连接成功
        mock_client_instance = mock_zlib_client.return_value
        mock_client_instance.test_connection.return_value = True
        
        result = self.service.test_connection()
        self.assertTrue(result)
        mock_client_instance.test_connection.assert_called_once()
        
        # 模拟连接失败
        mock_client_instance.test_connection.return_value = False
        result = self.service.test_connection()
        self.assertFalse(result)
    
    @patch('services.zlibrary_service.ZlibClient')
    def test_search_books(self, mock_zlib_client):
        """测试搜索书籍功能"""
        # 模拟搜索结果
        mock_search_results = [
            {
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
            }
        ]
        
        mock_client_instance = mock_zlib_client.return_value
        mock_client_instance.search.return_value = mock_search_results
        
        # 测试使用标题搜索
        results = self.service.search_books(title='Test Book')
        self.assertEqual(results, mock_search_results)
        mock_client_instance.search.assert_called_with(q='Test Book')
        
        # 测试使用标题和作者搜索
        mock_client_instance.search.reset_mock()
        results = self.service.search_books(title='Test Book', author='Test Author')
        self.assertEqual(results, mock_search_results)
        mock_client_instance.search.assert_called_with(q='Test Book Test Author')
        
        # 测试使用 ISBN 搜索
        mock_client_instance.search.reset_mock()
        results = self.service.search_books(isbn='1234567890')
        self.assertEqual(results, mock_search_results)
        mock_client_instance.search.assert_called_with(q='isbn:1234567890')
    
    @patch('services.zlibrary_service.ZlibClient')
    def test_find_best_match(self, mock_zlib_client):
        """测试找到最佳匹配功能"""
        # 模拟搜索结果
        mock_search_results = [
            {
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
            },
            {
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
            }
        ]
        
        mock_client_instance = mock_zlib_client.return_value
        mock_client_instance.search.return_value = mock_search_results
        
        # 测试找到精确匹配
        best_match = self.service.find_best_match(title='Test Book', author='Test Author')
        self.assertEqual(best_match['id'], '123456')
        
        # 测试找到部分匹配
        best_match = self.service.find_best_match(title='Test Book Second', author='Test Author')
        self.assertEqual(best_match['id'], '789012')
        
        # 测试未找到匹配
        mock_client_instance.search.return_value = []
        best_match = self.service.find_best_match(title='Nonexistent Book', author='Unknown Author')
        self.assertIsNone(best_match)
    
    @patch('services.zlibrary_service.ZlibClient')
    @patch('services.zlibrary_service.open', new_callable=mock_open)
    @patch('services.zlibrary_service.os.path.exists')
    def test_download_book(self, mock_exists, mock_file_open, mock_zlib_client):
        """测试下载书籍功能"""
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
        file_path = self.service.download_book(book_info)
        expected_path = os.path.join(self.download_dir, 'Test Book - Test Author.epub')
        self.assertEqual(file_path, expected_path)
        
        # 验证下载调用
        mock_client_instance.download.assert_called_once_with('123456')
        
        # 验证文件写入
        mock_file_open.assert_called_once_with(expected_path, 'wb')
        mock_file_open().write.assert_called_once_with(mock_content)
        
        # 测试文件已存在的情况
        mock_exists.return_value = True
        mock_client_instance.download.reset_mock()
        mock_file_open.reset_mock()
        
        file_path = self.service.download_book(book_info)
        self.assertEqual(file_path, expected_path)
        
        # 验证没有重新下载
        mock_client_instance.download.assert_not_called()
        mock_file_open.assert_not_called()
    
    @patch('services.zlibrary_service.ZlibClient')
    def test_search_and_download(self, mock_zlib_client):
        """测试搜索并下载功能"""
        # 模拟搜索结果
        mock_search_results = [
            {
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
            }
        ]
        
        mock_client_instance = mock_zlib_client.return_value
        mock_client_instance.search.return_value = mock_search_results
        mock_client_instance.download.return_value = b'test book content'
        
        # 模拟文件不存在
        with patch('services.zlibrary_service.os.path.exists', return_value=False):
            # 模拟文件写入
            with patch('services.zlibrary_service.open', new_callable=mock_open):
                # 测试搜索并下载
                result = self.service.search_and_download(title='Test Book', author='Test Author')
                
                self.assertTrue(result['success'])
                self.assertEqual(result['file_path'], os.path.join(self.download_dir, 'Test Book - Test Author.epub'))
                self.assertEqual(result['book_info']['id'], '123456')
        
        # 测试搜索失败
        mock_client_instance.search.return_value = []
        result = self.service.search_and_download(title='Nonexistent Book', author='Unknown Author')
        
        self.assertFalse(result['success'])
        self.assertIn('未找到匹配的书籍', result['error'])
    
    @patch('services.zlibrary_service.ZlibClient')
    def test_select_best_format(self, mock_zlib_client):
        """测试选择最佳格式功能"""
        # 模拟不同格式的搜索结果
        mock_search_results = [
            {
                'id': '123456',
                'title': 'Test Book',
                'author': 'Test Author',
                'extension': 'pdf',
                'md5': 'abc123'
            },
            {
                'id': '789012',
                'title': 'Test Book',
                'author': 'Test Author',
                'extension': 'epub',
                'md5': 'def456'
            },
            {
                'id': '345678',
                'title': 'Test Book',
                'author': 'Test Author',
                'extension': 'mobi',
                'md5': 'ghi789'
            }
        ]
        
        # 测试按照首选格式选择
        best_format = self.service._select_best_format(mock_search_results)
        self.assertEqual(best_format['id'], '789012')  # epub 是首选格式
        
        # 测试没有首选格式时选择第一个
        self.service.preferred_formats = ['azw3', 'djvu']
        best_format = self.service._select_best_format(mock_search_results)
        self.assertEqual(best_format['id'], '123456')  # 返回第一个结果
        
        # 测试空结果
        best_format = self.service._select_best_format([])
        self.assertIsNone(best_format)


if __name__ == '__main__':
    unittest.main()