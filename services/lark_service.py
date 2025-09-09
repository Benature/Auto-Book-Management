# -*- coding: utf-8 -*-
"""
飞书通知服务

负责发送通知消息到飞书群聊。
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from larkpy import LarkBot

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
        self.bot = LarkBot(webhook_url)

    def send_card_message(self, title: str, elements: List[Dict[str,
                                                                Any]]) -> bool:
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

    def send_403_error_notification(self, error_message: str,
                                    url: str) -> bool:
        """
        发送豆瓣403错误通知
        
        Args:
            error_message: 错误信息
            url: 出错的URL
            
        Returns:
            bool: 发送是否成功
        """
        # 构建卡片元素
        elements = [{
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "⚠️ **豆瓣访问被拒绝 (403错误)**"
            }
        }, {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**错误信息**: {error_message}"
            }
        }, {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**出错URL**: {url}"
            }
        }, {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**处理方式**: 程序已停止运行，请检查Cookie或更换代理"
            }
        }]

        # 添加时间信息
        elements.append({
            "tag":
            "note",
            "elements": [{
                "tag":
                "plain_text",
                "content":
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }]
        })

        # 发送卡片消息
        title = "🚫 豆瓣同步工具 - 访问被拒绝"
        return self.send_card_message(title, elements)

    def send_sync_summary(
            self,
            total: int,
            success: int,
            failed: int,
            details: Optional[List[Dict[str, Any]]] = None) -> bool:
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
        elements = [{
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**总计**: {total} 本书籍"
            }
        }, {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**成功**: {success} 本"
            }
        }, {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**失败**: {failed} 本"
            }
        }]

        # 如果有详细信息，添加到卡片中
        if details and len(details) > 0:
            elements.append({"tag": "hr"})

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
                        "tag":
                        "lark_md",
                        "content":
                        f"{i+1}. {detail.get('title', '未知')} - {detail.get('status', '未知')}"
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
            "tag":
            "note",
            "elements": [{
                "tag":
                "plain_text",
                "content":
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }]
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
            # 添加签名（如果有密钥）
            if self.secret:
                # 飞书签名实现
                pass

            self.logger.info(
                f"发送飞书消息: {json.dumps(message, ensure_ascii=False)[:100]}...")
            response = self.bot.send(message)
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
