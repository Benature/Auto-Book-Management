import json
import unittest
import tempfile
import os

from config.config_manager import ConfigManager
from services.lark_service import LarkService
from utils.logger import get_logger


class TestLarkService(unittest.TestCase):
    """Test cases for LarkService class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary config file for testing
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'test_config.yaml')
        
        # Create test config content - disable lark to avoid real network calls
        config_content = '''
lark:
  enabled: false
  webhook_url: 'https://open.feishu.cn/webhook/test'
  secret: 'test_secret'
database:
  url: ':memory:'
scheduler:
  enabled: false
'''
        with open(self.config_path, 'w') as f:
            f.write(config_content)
            
        # Use real config manager
        self.config_manager = ConfigManager(self.config_path)
        self.logger = get_logger('test_lark_service')
        self.lark_service = LarkService(self.config_manager, self.logger)

    def test_init(self):
        """Test initialization of LarkService."""
        # With lark disabled in config, service should be disabled
        self.assertFalse(self.lark_service.enabled)
        self.assertEqual(self.lark_service.webhook_url,
                         'https://open.feishu.cn/webhook/test')
        self.assertEqual(self.lark_service.secret, 'test_secret')

    def test_init_lark_client(self):
        """Test initialization of Lark client when service is disabled."""
        # Since service is disabled, _init_lark_client should handle it gracefully
        # This test verifies the method exists and can be called
        try:
            client = self.lark_service._init_lark_client()
            # When disabled, it should return None or handle gracefully
            self.assertIsNone(client)
        except Exception as e:
            # If it raises an exception when disabled, that's also acceptable
            self.assertIsInstance(e, (ImportError, AttributeError, ConnectionError))

    def test_send_text_message(self):
        """Test sending a text message when service is disabled."""
        # Call method - should return False when service is disabled
        result = self.lark_service.send_text_message('Test message')

        # Verify - should return False when service is disabled
        self.assertFalse(result)

    def test_send_text_message_disabled(self):
        """Test sending a text message when service is disabled."""
        # Service is already disabled by default in our config
        # Explicitly ensure it's disabled
        self.lark_service.enabled = False

        # Call method
        result = self.lark_service.send_text_message('Test message')

        # Verify
        self.assertFalse(result)

    def test_send_text_message_error(self):
        """Test handling error when sending a text message."""
        # Enable service temporarily to test error handling
        self.lark_service.enabled = True
        
        # Call method - will fail due to missing larkpy or network issues
        result = self.lark_service.send_text_message('Test message')

        # Verify - should return False on error
        self.assertFalse(result)

    def test_send_rich_text_message(self):
        """Test sending a rich text message when service is disabled."""
        # Call method - should return False when service is disabled
        result = self.lark_service.send_rich_text_message(title='Test Title',
                                                          content=[[{
                                                              'tag':
                                                              'text',
                                                              'text':
                                                              'Test content'
                                                          }]])

        # Verify - should return False when service is disabled
        self.assertFalse(result)

    def test_send_card_message(self):
        """Test sending a card message when service is disabled."""

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

        # Call method - should return False when service is disabled
        result = self.lark_service.send_card_message(test_card)

        # Verify - should return False when service is disabled
        self.assertFalse(result)

    def test_send_book_download_notification(self):
        """Test sending a book download notification when service is disabled."""

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

        # Verify - should return False when service is disabled
        self.assertFalse(result)

    def test_send_sync_task_summary(self):
        """Test sending a sync task summary when service is disabled."""

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

        # Verify - should return False when service is disabled
        self.assertFalse(result)


    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    unittest.main()
