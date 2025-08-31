# -*- coding: utf-8 -*-
"""
豆瓣zlib项目版本信息
"""

__version__ = "0.2.0"
__author__ = "benature"
__description__ = "豆瓣 Z-Library 同步工具"

# 版本历史
VERSION_HISTORY = {
    "0.2.0": "重构项目，删除V1版本代码，统一V2架构为主要版本",
    "0.1.x": "V1版本，基础功能实现"
}

def get_version():
    """获取当前版本"""
    return __version__

def get_version_info():
    """获取版本详细信息"""
    return {
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "history": VERSION_HISTORY
    }