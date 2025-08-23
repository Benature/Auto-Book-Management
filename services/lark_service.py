# -*- coding: utf-8 -*-

"""
飞书通知服务

负责发送通知消息到飞书群聊。
"""

import requests
import json
from typing import Dict, Any, Optional, List, Union
import time
from datetime import datetime

from utils.logger import get_logger


class LarkService:
    """飞书通知服务类"""
    
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        """
        初始化飞书通知服务
        
        Args:
            webhook_url: 飞书机器人 Webhook URL
            secret: 飞书机器人安全设置中的签名密钥（可选）
        """
        self.logger = get_logger("lark_service")
        self.webhook_url = webhook_url
        self.secret = secret
    
    def send_text_message(self, content: str) -> bool:
        """
        发送纯文本消息
        
        Args:
            content: 消息内容
            
        Returns:
            bool: 发送是否成功
        """
        message = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }
        return self._send_message(message)
    
    def send_rich_text_message(self, title: str, content: str) -> bool:
        """
        发送富文本消息
        
        Args:
            title: 消息标题
            content: 消息内容（支持部分 markdown 语法）
            
        Returns:
            bool: 发送是否成功
        """
        message = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": title,
                        "content": [
                            [
                                {
                                    "tag": "text",
                                    "text": content
                                }
                            ]
                        ]
                    }
                }
            }
        }
        return self._send_message(message)
    
    def send_card_message(self, title: str, elements: List[Dict[str, Any]]) -> bool:
        """
        发送卡片消息
        
        Args:
            title: 卡片标题
            elements: 卡片元素列表
            
        Returns:
            bool: 发送是否成功
        """
        message = {
            "msg_type": "interactive",
            "card": {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue"
                },
                "elements": elements
            }
        }
        return self._send_message(message)
    
    def send_book_notification(self, book_info: Dict[str, Any], download_status: bool, error_message: Optional[str] = None) -> bool:
        """
        发送书籍下载通知
        
        Args:
            book_info: 书籍信息
            download_status: 下载状态
            error_message: 错误信息（如果有）
            
        Returns:
            bool: 发送是否成功
        """
        # 构建卡片元素
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**书名**: {book_info.get('title', '未知')}"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**作者**: {book_info.get('author', '未知')}"
                }
            }
        ]
        
        # 添加 ISBN 信息（如果有）
        if book_info.get('isbn'):
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**ISBN**: {book_info.get('isbn', '')}"
                }
            })
        
        # 添加状态信息
        status_text = "✅ 下载成功" if download_status else "❌ 下载失败"
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**状态**: {status_text}"
            }
        })
        
        # 如果下载失败，添加错误信息
        if not download_status and error_message:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**错误**: {error_message}"
                }
            })
        
        # 添加时间信息
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })
        
        # 发送卡片消息
        title = "📚 豆瓣书籍下载通知"
        return self.send_card_message(title, elements)
    
    def send_sync_summary(self, total: int, success: int, failed: int, details: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        发送同步任务摘要
        
        Args:
            total: 总书籍数
            success: 成功下载数
            failed: 失败数
            details: 详细信息列表（可选）
            
        Returns:
            bool: 发送是否成功
        """
        # 构建卡片元素
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**总计**: {total} 本书籍"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**成功**: {success} 本"
                }
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**失败**: {failed} 本"
                }
            }
        ]
        
        # 如果有详细信息，添加到卡片中
        if details and len(details) > 0:
            elements.append({
                "tag": "hr"
            })
            
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**详细信息**:"
                }
            })
            
            # 最多显示 5 条详细信息
            for i, detail in enumerate(details[:5]):
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"{i+1}. {detail.get('title', '未知')} - {detail.get('status', '未知')}"
                    }
                })
            
            # 如果有更多信息，添加提示
            if len(details) > 5:
                elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"...还有 {len(details) - 5} 条记录未显示"
                    }
                })
        
        # 添加时间信息
        elements.append({
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })
        
        # 发送卡片消息
        title = "📊 豆瓣同步任务摘要"
        return self.send_card_message(title, elements)
    
    def _send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送消息到飞书
        
        Args:
            message: 消息内容
            
        Returns:
            bool: 发送是否成功
        """
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            
            # 添加签名（如果有密钥）
            if self.secret:
                # 飞书签名实现
                pass
            
            self.logger.info(f"发送飞书消息: {json.dumps(message, ensure_ascii=False)[:100]}...")
            response = requests.post(self.webhook_url, headers=headers, data=json.dumps(message), timeout=10)
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                self.logger.info("飞书消息发送成功")
                return True
            else:
                self.logger.error(f"飞书消息发送失败: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"飞书消息发送异常: {str(e)}")
            return False