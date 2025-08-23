# -*- coding: utf-8 -*-
"""
配置管理模块

负责加载和验证配置文件，提供配置访问接口。
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List


class ConfigManager:
    """配置管理器
    
    负责加载、验证和访问配置文件中的设置。
    """

    def __init__(self, config_path: str):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            Dict[str, Any]: 配置字典
            
        Raises:
            ValueError: 配置文件加载失败时抛出
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise ValueError(f"无法加载配置文件: {e}") from e

    def _validate_config(self) -> None:
        """
        验证配置文件的完整性和正确性
        
        Raises:
            ValueError: 配置验证失败时抛出
        """
        required_sections = [
            'douban', 'database', 'calibre', 'zlibrary', 'schedule', 'lark',
            'logging', 'system'
        ]
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"配置文件缺少必要的 '{section}' 部分")

        # 验证豆瓣配置
        if 'cookie' not in self.config['douban']:
            raise ValueError("豆瓣配置缺少 'cookie' 字段")

        # 验证数据库配置
        db_config = self.config['database']
        if 'type' not in db_config:
            raise ValueError("数据库配置缺少 'type' 字段")
        if db_config['type'] not in ['sqlite', 'postgresql']:
            raise ValueError("数据库类型必须是 'sqlite' 或 'postgresql'")
        if db_config['type'] == 'sqlite' and 'path' not in db_config:
            raise ValueError("SQLite 数据库配置缺少 'path' 字段")
        if db_config['type'] == 'postgresql':
            for field in ['host', 'port', 'dbname', 'username', 'password']:
                if field not in db_config:
                    raise ValueError(f"PostgreSQL 数据库配置缺少 '{field}' 字段")

        # 验证 Calibre 配置
        calibre_config = self.config['calibre']
        for field in ['content_server_url', 'username', 'password']:
            if field not in calibre_config:
                raise ValueError(f"Calibre 配置缺少 '{field}' 字段")

        # 验证 Z-Library 配置
        zlib_config = self.config['zlibrary']
        for field in [
                'username', 'password', 'format_priority', 'download_dir'
        ]:
            if field not in zlib_config:
                raise ValueError(f"Z-Library 配置缺少 '{field}' 字段")
        if not isinstance(zlib_config['format_priority'], list):
            raise ValueError("Z-Library 'format_priority' 必须是列表类型")

    def get_douban_config(self) -> Dict[str, Any]:
        """
        获取豆瓣配置
        
        Returns:
            Dict[str, Any]: 豆瓣配置字典
        """
        return self.config['douban']

    def get_database_config(self) -> Dict[str, Any]:
        """
        获取数据库配置
        
        Returns:
            Dict[str, Any]: 数据库配置字典
        """
        return self.config['database']

    def get_database_url(self) -> str:
        """
        获取数据库连接 URL
        
        Returns:
            str: 数据库连接 URL
        """
        db_config = self.config['database']
        if db_config['type'] == 'sqlite':
            db_path = Path(db_config['path'])
            # 确保路径是绝对路径
            if not db_path.is_absolute():
                db_path = Path(
                    os.path.dirname(
                        os.path.abspath(
                            self.config_path.as_posix()))) / db_path
            return f"sqlite:///{db_path}"
        else:  # postgresql
            return f"postgresql://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['dbname']}"

    def get_calibre_config(self) -> Dict[str, Any]:
        """
        获取 Calibre 配置
        
        Returns:
            Dict[str, Any]: Calibre 配置字典
        """
        return self.config['calibre']

    def get_zlibrary_config(self) -> Dict[str, Any]:
        """
        获取 Z-Library 配置
        
        Returns:
            Dict[str, Any]: Z-Library 配置字典
        """
        return self.config['zlibrary']

    def get_schedule_config(self) -> Dict[str, Any]:
        """
        获取调度配置
        
        Returns:
            Dict[str, Any]: 调度配置字典
        """
        return self.config['schedule']

    def get_lark_config(self) -> Dict[str, Any]:
        """
        获取飞书通知配置
        
        Returns:
            Dict[str, Any]: 飞书通知配置字典
        """
        return self.config['lark']

    def get_logging_config(self) -> Dict[str, Any]:
        """
        获取日志配置
        
        Returns:
            Dict[str, Any]: 日志配置字典
        """
        return self.config['logging']

    def get_system_config(self) -> Dict[str, Any]:
        """
        获取系统配置
        
        Returns:
            Dict[str, Any]: 系统配置字典
        """
        return self.config['system']

    def get_download_dir(self) -> Path:
        """
        获取下载目录路径
        
        Returns:
            Path: 下载目录的 Path 对象
        """
        download_dir = Path(self.config['zlibrary']['download_dir'])
        if not download_dir.is_absolute():
            download_dir = Path(
                os.path.dirname(os.path.abspath(
                    self.config_path.as_posix()))) / download_dir
        return download_dir

    def get_temp_dir(self) -> Path:
        """
        获取临时目录路径
        
        Returns:
            Path: 临时目录的 Path 对象
        """
        temp_dir = Path(self.config['system']['temp_dir'])
        if not temp_dir.is_absolute():
            temp_dir = Path(
                os.path.dirname(os.path.abspath(
                    self.config_path.as_posix()))) / temp_dir
        return temp_dir
