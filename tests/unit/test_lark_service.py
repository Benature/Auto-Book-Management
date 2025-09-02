import json
import unittest
from unittest.mock import MagicMock, patch

from config.config_manager import ConfigManager
from services.lark_service import LarkService
from utils.logger import get_logger


class TestLarkService(unittest.TestCase):
    """Test cases for LarkService class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_mock = MagicMock(spec=ConfigManager)
        self.config_mock.get_lark_config.return_value = {
            'enabled': True,
            'webhook_url': 'https://open.feishu.cn/webhook/test',
            'secret': 'test_secret'
        }
        self.logger_mock = MagicMock(spec=get_logger)
        self.lark_service = LarkService(self.config_mock, self.logger_mock)

    def test_init(self):
        """Test initialization of LarkService."""
        self.assertTrue(self.lark_service.enabled)
        self.assertEqual(self.lark_service.webhook_url,
                         'https://open.feishu.cn/webhook/test')
        self.assertEqual(self.lark_service.secret, 'test_secret')

    @patch('services.lark_service.larkpy.LarkClient')
    def test_init_lark_client(self, mock_lark_client):
        """Test initialization of Lark client."""
        # Setup mock
        mock_client_instance = MagicMock()
        mock_lark_client.return_value = mock_client_instance

        # Call method
        client = self.lark_service._init_lark_client()

        # Verify
        self.assertEqual(client, mock_client_instance)
        mock_lark_client.assert_called_once_with(
            webhook_url='https://open.feishu.cn/webhook/test',
            secret='test_secret')

    @patch('services.lark_service.LarkService._init_lark_client')
    def test_send_text_message(self, mock_init_client):
        """Test sending a text message."""
        # Setup mock
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.send_text.return_value = {'code': 0, 'msg': 'success'}

        # Call method
        result = self.lark_service.send_text_message('Test message')

        # Verify
        self.assertTrue(result)
        mock_init_client.assert_called_once()
        mock_client.send_text.assert_called_once_with('Test message')

    @patch('services.lark_service.LarkService._init_lark_client')
    def test_send_text_message_disabled(self, mock_init_client):
        """Test sending a text message when service is disabled."""
        # Disable service
        self.lark_service.enabled = False

        # Call method
        result = self.lark_service.send_text_message('Test message')

        # Verify
        self.assertFalse(result)
        mock_init_client.assert_not_called()

    @patch('services.lark_service.LarkService._init_lark_client')
    def test_send_text_message_error(self, mock_init_client):
        """Test handling error when sending a text message."""
        # Setup mock
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.send_text.side_effect = Exception('Test error')

        # Call method
        result = self.lark_service.send_text_message('Test message')

        # Verify
        self.assertFalse(result)
        mock_init_client.assert_called_once()
        mock_client.send_text.assert_called_once_with('Test message')
        self.logger_mock.error.assert_called_once()

    @patch('services.lark_service.LarkService._init_lark_client')
    def test_send_rich_text_message(self, mock_init_client):
        """Test sending a rich text message."""
        # Setup mock
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.send_rich_text.return_value = {'code': 0, 'msg': 'success'}

        # Call method
        result = self.lark_service.send_rich_text_message(title='Test Title',
                                                          content=[[{
                                                              'tag':
                                                              'text',
                                                              'text':
                                                              'Test content'
                                                          }]])

        # Verify
        self.assertTrue(result)
        mock_init_client.assert_called_once()
        mock_client.send_rich_text.assert_called_once_with(title='Test Title',
                                                           content=[[{
                                                               'tag':
                                                               'text',
                                                               'text':
                                                               'Test content'
                                                           }]])

    @patch('services.lark_service.LarkService._init_lark_client')
    def test_send_card_message(self, mock_init_client):
        """Test sending a card message."""
        # Setup mock
        mock_client = MagicMock()
        mock_init_client.return_value = mock_client
        mock_client.send_card.return_value = {'code': 0, 'msg': 'success'}

        # Create test card
        test_card = {
            'config': {
                'wide_screen_mode': True
            },
            'elements': [{
                'tag': 'div',
                'text': {
                    'tag': 'plain_text',
                    'content': 'Test content'
                }
            }],
            'header': {
                'title': {
                    'tag': 'plain_text',
                    'content': 'Test Title'
                }
            }
        }

        # Call method
        result = self.lark_service.send_card_message(test_card)

        # Verify
        self.assertTrue(result)
        mock_init_client.assert_called_once()
        mock_client.send_card.assert_called_once_with(test_card)

    @patch('services.lark_service.LarkService.send_card_message')
    def test_send_book_download_notification(self, mock_send_card):
        """Test sending a book download notification."""
        # Setup mock
        mock_send_card.return_value = True

        # Call method
        result = self.lark_service.send_book_download_notification(
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            isbn='1234567890',
            format='PDF',
            file_size=1024,
            cover_url='http://test.com/cover.jpg',
            douban_url='http://douban.com/book/12345',
            calibre_id=1)

        # Verify
        self.assertTrue(result)
        mock_send_card.assert_called_once()
        # Verify card structure
        card = mock_send_card.call_args[0][0]
        self.assertEqual(card['header']['title']['content'], '📚 新书下载通知')
        # Check that the book title is in the card content
        elements_text = json.dumps(card['elements'])
        self.assertIn('Test Book', elements_text)
        self.assertIn('Test Author', elements_text)

    @patch('services.lark_service.LarkService.send_card_message')
    def test_send_sync_task_summary(self, mock_send_card):
        """Test sending a sync task summary."""
        # Setup mock
        mock_send_card.return_value = True

        # Call method
        result = self.lark_service.send_sync_task_summary(
            task_type='douban_sync',
            start_time='2023-01-01 12:00:00',
            end_time='2023-01-01 12:10:00',
            total_books=10,
            new_books=5,
            downloaded_books=3,
            failed_books=2,
            details='Test details')

        # Verify
        self.assertTrue(result)
        mock_send_card.assert_called_once()
        # Verify card structure
        card = mock_send_card.call_args[0][0]
        self.assertEqual(card['header']['title']['content'], '🔄 同步任务摘要')
        # Check that the task details are in the card content
        elements_text = json.dumps(card['elements'])
        self.assertIn('douban_sync', elements_text)
        self.assertIn('10', elements_text)  # total_books
        self.assertIn('5', elements_text)  # new_books


if __name__ == '__main__':
    unittest.main()
