import os
import tempfile
import unittest

import yaml

from config.config_manager import ConfigManager


class TestConfigManager(unittest.TestCase):
    """Test cases for ConfigManager class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_config = {
            'douban': {
                'user_id': 'test_user',
                'cookie': 'test_cookie',
                'user_agent': 'test_agent',
                'wishlist_url': 'https://book.douban.com/people/{user_id}/wish'
            },
            'database': {
                'url': 'sqlite:///test.db',
                'echo': False
            },
            'calibre': {
                'host': 'http://localhost',
                'port': 8080,
                'username': 'test_user',
                'password': 'test_pass',
                'library': 'test_library'
            },
            'zlibrary': {
                'base_url': 'https://zlibrary.example',
                'email': 'test@example.com',
                'password': 'test_pass',
                'download_dir': '/tmp/downloads',
                'format_priority': ['PDF', 'EPUB', 'MOBI']
            },
            'scheduler': {
                'enabled': True,
                'sync_interval_days': 1,
                'sync_time': '03:00',
                'cleanup_interval_days': 7
            },
            'lark': {
                'enabled': True,
                'webhook_url': 'https://open.feishu.cn/webhook/test',
                'secret': 'test_secret'
            },
            'settings': {
                'download_timeout': 300,
                'max_retries': 3,
                'retry_delay': 5
            }
        }

        # Create temporary config file for testing
        self.temp_dir = tempfile.mkdtemp()
        self.test_config_path = os.path.join(self.temp_dir, 'test_config.yaml')
        
        # Write test config to temporary file
        with open(self.test_config_path, 'w') as f:
            yaml.dump(self.test_config, f, default_flow_style=False)

    def test_load_config(self):
        """Test loading configuration from file."""
        # Create config manager and test initialization loads config
        config_manager = ConfigManager(self.test_config_path)

        # Verify config was loaded correctly
        self.assertEqual(config_manager.config, self.test_config)

    def test_load_config_file_not_found(self):
        """Test loading config when file doesn't exist."""
        # Test and verify exception
        with self.assertRaises(FileNotFoundError):
            ConfigManager('nonexistent.yaml')

    def test_validate_config_valid(self):
        """Test validation of a valid configuration."""
        # Create config manager
        config_manager = ConfigManager(self.test_config_path)

        # Validate config - should not raise exception
        config_manager._validate_config()

        # Verify all required sections exist
        self.assertIn('douban', config_manager.config)
        self.assertIn('database', config_manager.config)
        self.assertIn('calibre', config_manager.config)
        self.assertIn('zlibrary', config_manager.config)
        self.assertIn('scheduler', config_manager.config)
        self.assertIn('lark', config_manager.config)

    def test_validate_config_missing_section(self):
        """Test validation with missing required section."""
        # Create invalid config file
        invalid_config = self.test_config.copy()
        del invalid_config['douban']  # Remove required section
        
        invalid_config_path = os.path.join(self.temp_dir, 'invalid_config.yaml')
        with open(invalid_config_path, 'w') as f:
            yaml.dump(invalid_config, f, default_flow_style=False)

        # Test - should raise ValueError
        with self.assertRaises(ValueError) as context:
            config_manager = ConfigManager(invalid_config_path)

        self.assertIn('Missing required configuration section: douban',
                      str(context.exception))

    def test_get_douban_config(self):
        """Test getting douban configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        douban_config = config_manager.get_douban_config()

        # Verify
        self.assertEqual(douban_config['user_id'], 'test_user')
        self.assertEqual(douban_config['cookie'], 'test_cookie')
        self.assertEqual(douban_config['user_agent'], 'test_agent')
        self.assertEqual(
            douban_config['wishlist_url'],
            'https://book.douban.com/people/{user_id}/wish')

    def test_get_database_config(self):
        """Test getting database configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        database_config = config_manager.get_database_config()

        # Verify
        self.assertEqual(database_config['url'], 'sqlite:///test.db')
        self.assertEqual(database_config['echo'], False)

    def test_get_calibre_config(self):
        """Test getting calibre configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        calibre_config = config_manager.get_calibre_config()

        # Verify
        self.assertEqual(calibre_config['host'], 'http://localhost')
        self.assertEqual(calibre_config['port'], 8080)
        self.assertEqual(calibre_config['username'], 'test_user')
        self.assertEqual(calibre_config['password'], 'test_pass')
        self.assertEqual(calibre_config['library'], 'test_library')

    def test_get_zlibrary_config(self):
        """Test getting zlibrary configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        zlibrary_config = config_manager.get_zlibrary_config()

        # Verify
        self.assertEqual(zlibrary_config['base_url'],
                         'https://zlibrary.example')
        self.assertEqual(zlibrary_config['email'], 'test@example.com')
        self.assertEqual(zlibrary_config['password'], 'test_pass')
        self.assertEqual(zlibrary_config['download_dir'], '/tmp/downloads')
        self.assertEqual(zlibrary_config['format_priority'],
                         ['PDF', 'EPUB', 'MOBI'])

    def test_get_scheduler_config(self):
        """Test getting scheduler configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        scheduler_config = config_manager.get_scheduler_config()

        # Verify
        self.assertEqual(scheduler_config['enabled'], True)
        self.assertEqual(scheduler_config['sync_interval_days'], 1)
        self.assertEqual(scheduler_config['sync_time'], '03:00')
        self.assertEqual(scheduler_config['cleanup_interval_days'], 7)

    def test_get_lark_config(self):
        """Test getting lark configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        lark_config = config_manager.get_lark_config()

        # Verify
        self.assertEqual(lark_config['enabled'], True)
        self.assertEqual(lark_config['webhook_url'],
                         'https://open.feishu.cn/webhook/test')
        self.assertEqual(lark_config['secret'], 'test_secret')

    def test_get_settings_config(self):
        """Test getting settings configuration."""
        config_manager = ConfigManager(self.test_config_path)

        # Test
        settings_config = config_manager.get_settings_config()

        # Verify
        self.assertEqual(settings_config['download_timeout'], 300)
        self.assertEqual(settings_config['max_retries'], 3)
        self.assertEqual(settings_config['retry_delay'], 5)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)


if __name__ == '__main__':
    unittest.main()