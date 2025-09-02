#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
运行真实网络测试的脚本

使用示例:
    python tests/unit/run_real_test.py
    python tests/unit/run_real_test.py --book-id 26912767
"""

import argparse
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
FILE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FILE_DIR.parent.parent))

from config.config_manager import ConfigManager
from scrapers.douban_scraper import DoubanScraper


def run_real_test(book_id=None):
    """运行真实网络测试"""
    print("开始运行真实网络测试...")
    
    try:
        # 加载配置
        config_manager = ConfigManager(Path(__file__).parent.parent.parent / 'config.yaml')
        douban_config = config_manager.get_douban_config()
        
        # 检查cookie配置
        cookie = douban_config.get('cookie', '')
        if not cookie:
            print("❌ 错误: 需要在config.yaml中配置有效的豆瓣cookie")
            return False
            
        print("✅ 检测到cookie配置")
        
        # 创建爬虫实例
        system_config = config_manager.get_system_config()
        user_agent = system_config.get('user_agent')
        max_pages = douban_config.get('max_pages', 1)
        
        scraper = DoubanScraper(
            cookie=cookie,
            user_agent=user_agent,
            max_pages=max_pages
        )
        
        print("🔄 正在测试获取想读书单...")
        
        # 测试获取想读书单
        wish_list = scraper.get_wish_list()
        print(f"✅ 成功获取 {len(wish_list)} 本想读书籍")
        
        if wish_list:
            print("\n📚 书单预览:")
            for i, book in enumerate(wish_list[:3], 1):
                print(f"  {i}. {book.get('title', '未知标题')} - {book.get('author', '未知作者')}")
            
            # 如果有指定书籍ID，测试获取详情
            if book_id:
                print(f"\n🔄 正在测试获取书籍 {book_id} 的详情...")
                book_detail = scraper.get_book_detail(book_id)
                if book_detail:
                    print("✅ 成功获取书籍详情:")
                    print(f"   标题: {book_detail.get('title', '未知')}")
                    print(f"   作者: {book_detail.get('author', '未知')}")
                    print(f"   评分: {book_detail.get('rating', '未知')}")
                    print(f"   ISBN: {book_detail.get('isbn', '未知')}")
                else:
                    print("❌ 无法获取书籍详情")
        
        print("\n🎉 真实网络测试完成!")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='运行豆瓣爬虫真实网络测试')
    parser.add_argument('--book-id', 
                       default=None, 
                       help='指定测试的书籍ID (例如: 26912767)')
    
    args = parser.parse_args()
    
    success = run_real_test(args.book_id)
    sys.exit(0 if success else 1)