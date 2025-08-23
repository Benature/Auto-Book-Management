#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
项目安装脚本

该脚本用于安装项目依赖和初始化数据库
"""

import os
import sys
import subprocess
import argparse
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
import yaml
import shutil


def check_python_version():
    """检查 Python 版本是否满足要求"""
    if sys.version_info < (3, 7):
        print("错误: 需要 Python 3.7 或更高版本")
        sys.exit(1)


def install_dependencies():
    """安装项目依赖"""
    print("正在安装项目依赖...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
        print("依赖安装成功")
        return True
    except subprocess.CalledProcessError as e:
        print(f"依赖安装失败: {e}")
        return False


def create_config_file():
    """如果配置文件不存在，则从示例创建配置文件"""
    if not os.path.exists("config.yaml") and os.path.exists("config.yaml.example"):
        print("正在从示例创建配置文件...")
        shutil.copy("config.yaml.example", "config.yaml")
        print("配置文件已创建，请编辑 config.yaml 以适应您的环境")
        return True
    elif os.path.exists("config.yaml"):
        print("配置文件已存在，跳过创建")
        return True
    else:
        print("错误: 找不到 config.yaml.example 文件")
        return False


def create_directories():
    """创建必要的目录"""
    directories = [
        "logs",
        "data/downloads",
        "data/temp"
    ]
    
    print("正在创建必要的目录...")
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    print("目录创建成功")
    return True


def init_database():
    """初始化数据库"""
    print("正在初始化数据库...")
    
    # 加载配置文件
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return False
    
    # 获取数据库 URL
    try:
        db_config = config["database"]
        if db_config["type"] == "sqlite":
            db_path = db_config["path"]
            # 确保路径是绝对路径
            if not os.path.isabs(db_path):
                db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path)
            db_url = f"sqlite:///{db_path}"
        else:  # postgresql
            db_url = f"postgresql://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    except KeyError as e:
        print(f"错误: 配置文件中缺少数据库配置项: {e}")
        return False
    
    # 初始化数据库
    try:
        # 动态导入模型，避免循环导入
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db.models import Base
        
        # 创建数据库引擎和表
        engine = create_engine(db_url)
        Base.metadata.create_all(engine)
        print("数据库初始化成功")
        return True
    except SQLAlchemyError as e:
        print(f"数据库初始化失败: {e}")
        return False
    except ImportError as e:
        print(f"导入模型失败: {e}")
        return False


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="豆瓣zlib 项目安装脚本")
    parser.add_argument("--skip-deps", action="store_true", help="跳过安装依赖")
    parser.add_argument("--skip-config", action="store_true", help="跳过创建配置文件")
    parser.add_argument("--skip-dirs", action="store_true", help="跳过创建目录")
    parser.add_argument("--skip-db", action="store_true", help="跳过初始化数据库")
    args = parser.parse_args()
    
    # 检查 Python 版本
    check_python_version()
    
    # 安装依赖
    if not args.skip_deps:
        if not install_dependencies():
            return False
    
    # 创建配置文件
    if not args.skip_config:
        if not create_config_file():
            return False
    
    # 创建目录
    if not args.skip_dirs:
        if not create_directories():
            return False
    
    # 初始化数据库
    if not args.skip_db:
        if not init_database():
            return False
    
    print("\n安装完成！您现在可以运行 python main.py 启动应用")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)