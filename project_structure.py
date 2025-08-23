#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
项目结构初始化脚本

此脚本用于创建「豆瓣书单同步与 Calibre 集成自动化」项目的基本目录结构。
运行此脚本将创建项目所需的所有目录和基本文件。
"""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any


def create_directory(path):
    """创建目录，如果已存在则跳过"""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"创建目录: {path}")


def create_file(path, content=""):
    """创建文件，如果已存在则跳过"""
    if not os.path.exists(path):
        # 确保目录存在
        directory = os.path.dirname(path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"创建文件: {path}")


def create_init_file(path):
    """创建 __init__.py 文件"""
    create_file(path, "# -*- coding: utf-8 -*-\n")


def main():
    """主函数：创建项目结构"""
    
    # 获取当前脚本所在目录
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir
    
    print("开始创建项目结构...")
    
    # 创建主要目录
    directories = [
        "config",
        "scrapers",
        "services",
        "models",
        "utils",
        "db",
        "tests",
        "tests/unit",
        "tests/integration",
        "data",
        "data/downloads",
        "data/temp",
        "logs",
        "scripts"
    ]
    
    for directory in directories:
        create_directory(os.path.join(root_dir, directory))
    
    # 创建 __init__.py 文件
    init_files = [
        "scrapers/__init__.py",
        "services/__init__.py",
        "models/__init__.py",
        "utils/__init__.py",
        "db/__init__.py",
        "tests/__init__.py",
        "tests/unit/__init__.py",
        "tests/integration/__init__.py"
    ]
    
    for init_file in init_files:
        create_init_file(os.path.join(root_dir, init_file))
    
    # 创建 requirements.txt
    create_file(os.path.join(root_dir, "requirements.txt"), """# 网络请求
requests>=2.31.0
beautifulsoup4>=4.12.2
lxml>=4.9.3

# 数据库
SQLAlchemy>=2.0.23
alembic>=1.12.1

# 配置管理
PyYAML>=6.0.1

# 日志
loguru>=0.7.2

# 测试
pytest>=7.4.3
pytest-cov>=4.1.0

# 其他工具
click>=8.1.7
python-dotenv>=1.0.0

# zlibrary 相关
# 注意：zlibrary 可能需要额外安装
# zlibrary-api>=1.0.0
""")
    
    # 创建 config.yaml.example
    create_file(os.path.join(root_dir, "config.yaml.example"), """# 豆瓣配置
douban:
  cookie: "your_douban_cookie_here"
  user_id: "your_douban_user_id"

# zlibrary 配置
zlibrary:
  email: "your_email@example.com"
  password: "your_password"
  
# 数据库配置
database:
  url: "sqlite:///data/douban_books.db"

# 日志配置
logging:
  level: "INFO"
  file: "logs/app.log"
  max_size: "10MB"
  backup_count: 5

# 同步配置
sync:
  interval_hours: 24
  auto_start: true
  download_path: "data/downloads"
""")
    
    # 创建 main.py
    create_file(os.path.join(root_dir, "main.py"), """#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
豆瓣书单同步与 Calibre 集成自动化 - 主程序

此程序用于自动同步豆瓣书单到本地数据库，并集成 Calibre 管理电子书。
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
FILE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(FILE_DIR))

from utils.logger import setup_logger
from scrapers.douban_scraper import DoubanScraper
from services.zlibrary_service import ZLibraryService
from db.database import Database


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="豆瓣书单同步与 Calibre 集成")
    parser.add_argument("--once", action="store_true", help="执行一次同步")
    parser.add_argument("--daemon", action="store_true", help="以守护进程运行")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logger()
    logger.info("豆瓣书单同步系统启动")
    
    try:
        # 初始化数据库
        db = Database()
        
        # 初始化服务
        scraper = DoubanScraper()
        zlibrary_service = ZLibraryService()
        
        if args.once:
            # 执行一次同步
            logger.info("执行一次同步任务...")
            # TODO: 实现同步逻辑
            pass
        elif args.daemon:
            # 以守护进程运行
            logger.info("启动守护进程...")
            # TODO: 实现守护进程逻辑
            pass
        else:
            # 默认行为
            logger.info("执行默认任务...")
            # TODO: 实现默认逻辑
            pass
            
    except Exception as e:
        logger.error(f"系统错误: {e}")
        sys.exit(1)
    finally:
        logger.info("系统关闭")


if __name__ == "__main__":
    main()
""")
    
    # 创建 config/config_manager.py
    create_file(os.path.join(root_dir, "config/config_manager.py"), """# -*- coding: utf-8 -*-

"""
配置文件管理器

管理项目的配置文件，提供统一的配置访问接口。
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """配置管理器类"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
        """
        if config_path is None:
            # 使用项目根目录下的config.yaml
            FILE_DIR = Path(__file__).resolve().parent.parent
            config_path = str(FILE_DIR / "config.yaml")
        
        self.config_path = config_path
        self._config = None
    
    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            Dict[str, Any]: 配置字典
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键，如'douban.cookie'
            default: 默认值
        
        Returns:
            配置值
        """
        if self._config is None:
            self.load_config()
        
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键，支持点号分隔的嵌套键
            value: 要设置的值
        """
        if self._config is None:
            self.load_config()
        
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save_config(self) -> None:
        """保存配置到文件"""
        if self._config is None:
            return
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)


# 全局配置实例
config = ConfigManager()
""")
    
    # 创建 scrapers/douban_scraper.py
    create_file(os.path.join(root_dir, "scrapers/douban_scraper.py"), """# -*- coding: utf-8 -*-

"""
豆瓣爬虫模块

用于从豆瓣获取用户书单信息。
"""

import requests
import time
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from pathlib import Path

from config.config_manager import config
from utils.logger import get_logger


class DoubanScraper:
    """豆瓣爬虫类"""
    
    def __init__(self, cookie: str = None):
        """
        初始化豆瓣爬虫
        
        Args:
            cookie: 豆瓣Cookie，如果为None则从配置中读取
        """
        self.cookie = cookie or config.get("douban.cookie", "")
        self.user_id = config.get("douban.user_id")
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Cookie": self.cookie,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        self.logger = get_logger("douban_scraper")
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_wish_list(self, user_id: str = None) -> List[Dict[str, Any]]:
        """
        获取用户想读书单
        
        Args:
            user_id: 用户ID，如果为None则使用配置中的用户ID
        
        Returns:
            List[Dict[str, Any]]: 书籍列表
        """
        user_id = user_id or self.user_id
        if not user_id:
            raise ValueError("用户ID不能为空")
        
        wish_list = []
        page = 1
        
        while True:
            url = f"https://book.douban.com/people/{user_id}/wish"
            params = {"start": (page - 1) * 15, "sort": "time", "rating": "all", "filter": "all", "mode": "list"}
            
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                books = soup.find_all('li', class_='subject-item')
                
                if not books:
                    break
                
                for book in books:
                    book_info = self._parse_book_info(book)
                    if book_info:
                        wish_list.append(book_info)
                
                self.logger.info(f"已获取第{page}页书单，共{len(wish_list)}本书")
                page += 1
                time.sleep(1)  # 避免请求过快
                
            except requests.RequestException as e:
                self.logger.error(f"获取书单失败: {e}")
                break
        
        return wish_list
    
    def _parse_book_info(self, book_element) -> Optional[Dict[str, Any]]:
        """
        解析单本书的信息
        
        Args:
            book_element: BeautifulSoup元素
        
        Returns:
            Dict[str, Any]: 书籍信息
        """
        try:
            # 获取标题
            title_elem = book_element.find('h2', class_='')
            if title_elem:
                title = title_elem.get_text(strip=True)
            else:
                return None
            
            # 获取链接
            link_elem = book_element.find('a', class_='nbg')
            book_url = link_elem['href'] if link_elem else ""
            
            # 获取封面图片
            img_elem = book_element.find('img')
            cover_url = img_elem['src'] if img_elem else ""
            
            # 获取书籍信息
            info_elem = book_element.find('div', class_='pub')
            pub_info = info_elem.get_text(strip=True) if info_elem else ""
            
            # 获取评分
            rating_elem = book_element.find('span', class_='rating_nums')
            rating = float(rating_elem.get_text(strip=True)) if rating_elem else 0.0
            
            # 获取评论数
            comment_elem = book_element.find('span', class_='pl')
            comment_count = 0
            if comment_elem:
                comment_text = comment_elem.get_text(strip=True)
                import re
                match = re.search(r'(\d+)', comment_text)
                if match:
                    comment_count = int(match.group(1))
            
            return {
                "title": title,
                "url": book_url,
                "cover_url": cover_url,
                "pub_info": pub_info,
                "rating": rating,
                "comment_count": comment_count,
                "status": "wish"
            }
            
        except Exception as e:
            self.logger.error(f"解析书籍信息失败: {e}")
            return None
    
    def get_book_detail(self, book_url: str) -> Optional[Dict[str, Any]]:
        """
        获取书籍详细信息
        
        Args:
            book_url: 书籍URL
        
        Returns:
            Dict[str, Any]: 书籍详细信息
        """
        try:
            response = self.session.get(book_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 获取ISBN
            isbn = ""
            info_elem = soup.find('div', id='info')
            if info_elem:
                isbn_match = str(info_elem).find('ISBN')
                if isbn_match != -1:
                    import re
                    isbn_pattern = r'ISBN[:\s]*([\d-]+)'
                    match = re.search(isbn_pattern, str(info_elem))
                    if match:
                        isbn = match.group(1)
            
            # 获取作者
            author = ""
            author_elem = soup.find('span', class_='author')
            if author_elem:
                author = author_elem.get_text(strip=True)
            
            # 获取出版社
            publisher = ""
            if info_elem:
                text = info_elem.get_text()
                import re
                pub_match = re.search(r'出版社[:\s]*([^\n]+)', text)
                if pub_match:
                    publisher = pub_match.group(1).strip()
            
            return {
                "isbn": isbn,
                "author": author,
                "publisher": publisher
            }
            
        except Exception as e:
            self.logger.error(f"获取书籍详情失败: {e}")
            return None
""")
    
    # 创建 services/zlibrary_service.py
    create_file(os.path.join(root_dir, "services/zlibrary_service.py"), """# -*- coding: utf-8 -*-

"""
ZLibrary 服务模块

用于与 ZLibrary 交互，搜索和下载电子书。
"""

import requests
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from config.config_manager import config
from utils.logger import get_logger


class ZLibraryService:
    """ZLibrary 服务类"""
    
    def __init__(self, email: str = None, password: str = None):
        """
        初始化 ZLibrary 服务
        
        Args:
            email: 邮箱，如果为None则从配置中读取
            password: 密码，如果为None则从配置中读取
        """
        self.email = email or config.get("zlibrary.email")
        self.password = password or config.get("zlibrary.password")
        
        self.logger = get_logger("zlibrary_service")
        self.session = requests.Session()
        
        # 注意：这里需要根据实际的ZLibrary API进行调整
        self.base_url = "https://z-lib.io"
    
    def search_book(self, title: str, author: str = None, isbn: str = None) -> List[Dict[str, Any]]:
        """
        搜索书籍
        
        Args:
            title: 书名
            author: 作者
            isbn: ISBN
        
        Returns:
            List[Dict[str, Any]]: 搜索结果
        """
        # 注意：这里需要根据实际的ZLibrary API实现
        # 由于ZLibrary经常变动，这里提供的是通用框架
        
        search_results = []
        
        try:
            # 构建搜索URL
            search_url = f"{self.base_url}/search"
            
            params = {"q": title}
            if author:
                params["author"] = author
            if isbn:
                params["isbn"] = isbn
            
            # 注意：实际实现需要根据ZLibrary的API进行调整
            self.logger.info(f"搜索书籍: {title}")
            
            # 这里应该是实际的API调用
            # response = self.session.get(search_url, params=params)
            # ... 解析结果
            
        except Exception as e:
            self.logger.error(f"搜索书籍失败: {e}")
        
        return search_results
    
    def download_book(self, book_id: str, download_path: str = None) -> bool:
        """
        下载书籍
        
        Args:
            book_id: 书籍ID
            download_path: 下载路径
        
        Returns:
            bool: 是否下载成功
        """
        if download_path is None:
            download_path = config.get("sync.download_path", "data/downloads")
        
        try:
            # 确保下载目录存在
            Path(download_path).mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"下载书籍: {book_id}")
            
            # 注意：实际实现需要根据ZLibrary的API进行调整
            # 这里应该是实际的下载逻辑
            
            return True
            
        except Exception as e:
            self.logger.error(f"下载书籍失败: {e}")
            return False
""")
    
    # 创建 db/database.py
    create_file(os.path.join(root_dir, "db/database.py"), """# -*- coding: utf-8 -*-

"""
数据库模块

管理数据库连接和表结构。
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from pathlib import Path

from config.config_manager import config

Base = declarative_base()


class Book(Base):
    """书籍模型"""
    __tablename__ = 'books'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    author = Column(String(200))
    publisher = Column(String(200))
    isbn = Column(String(20))
    cover_url = Column(String(500))
    rating = Column(Float)
    comment_count = Column(Integer)
    douban_url = Column(String(500))
    status = Column(String(20))  # wish, reading, read
    
    # 同步信息
    sync_date = Column(DateTime, default=datetime.utcnow)
    downloaded = Column(Boolean, default=False)
    download_path = Column(String(500))
    
    # 额外信息
    description = Column(Text)
    tags = Column(String(500))


class Database:
    """数据库管理类"""
    
    def __init__(self, database_url: str = None):
        """
        初始化数据库
        
        Args:
            database_url: 数据库URL，如果为None则从配置中读取
        """
        if database_url is None:
            database_url = config.get("database.url", "sqlite:///data/douban_books.db")
        
        # 处理SQLite的相对路径
        if database_url.startswith("sqlite:///"):
            db_path = database_url[10:]  # 移除 "sqlite:///"
            if not os.path.isabs(db_path):
                # 转换为绝对路径
                FILE_DIR = Path(__file__).resolve().parent.parent
                db_path = str(FILE_DIR / db_path)
                database_url = f"sqlite:///{db_path}"
        
        self.engine = create_engine(database_url)
        self.Session = sessionmaker(bind=self.engine)
    
    def init_db(self):
        """初始化数据库表"""
        Base.metadata.create_all(self.engine)
    
    def get_session(self):
        """获取数据库会话"""
        return self.Session()
""")
    
    # 创建 utils/logger.py
    create_file(os.path.join(root_dir, "utils/logger.py"), """# -*- coding: utf-8 -*-

"""
日志工具

提供日志记录功能。
"""

import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logger(log_level=logging.INFO, log_file=None, console=True):
    """设置日志记录器
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        console: 是否输出到控制台
    
    Returns:
        logger: 日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger("douban_zlib")
    logger.setLevel(log_level)
    logger.handlers = []  # 清除已有的处理器
    
    # 设置日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 添加控制台处理器
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def get_logger(name=None):
    """获取日志记录器
    
    Args:
        name: 日志记录器名称
    
    Returns:
        logger: 日志记录器
    """
    if name:
        return logging.getLogger(f"douban_zlib.{name}")
    return logging.getLogger("douban_zlib")
""")
    
    # 创建 .gitignore 文件
    create_file(os.path.join(root_dir, ".gitignore"), """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
env/
ENV/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Project specific
config.yaml
logs/
data/
!data/.gitkeep

# Temporary files
*.log
*.tmp
.DS_Store
""")
    
    # 创建空的 .gitkeep 文件以保留空目录
    for directory in ["data", "data/downloads", "data/temp", "logs"]:
        create_file(os.path.join(root_dir, f"{directory}/.gitkeep"), "")
    
    print("\n项目结构初始化完成！")
    print("\n接下来的步骤：")
    print("1. 创建虚拟环境: python -m venv venv")
    print("2. 激活虚拟环境:")
    print("   - Windows: venv\\Scripts\\activate")
    print("   - macOS/Linux: source venv/bin/activate")
    print("3. 安装依赖: pip install -r requirements.txt")
    print("4. 配置系统: cp config.yaml.example config.yaml")
    print("5. 初始化数据库: python -c \"from db.database import Database; db = Database('sqlite:///data/douban_books.db'); db.init_db()\"")
    print("6. 运行系统: python main.py")


if __name__ == "__main__":
    main()