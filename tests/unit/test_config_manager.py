import unittest
from unittest.mock import patch, mock_open
import os
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
            'logging': {
                'level': 'INFO',
                'file': 'logs/app.log',
                'max_size_mb': 10,
                'backup_count': 5
            },
            'system': {
                'temp_dir': '/tmp/temp',
                'max_retries': 3,
                'retry_delay': 5
            }
        }

        # Convert to YAML string for mocking file reads
        self.yaml_content = yaml.dump(self.test_config)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_load_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test loading configuration from file."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config = config_manager.load_config()

        # Verify
        self.assertEqual(config, self.test_config)
        mock_exists.assert_called_once_with('config.yaml')
        mock_file.assert_called_once_with('config.yaml', 'r', encoding='utf-8')
        mock_yaml_load.assert_called_once()

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    def test_load_config_file_not_found(self, mock_exists, mock_file):
        """Test handling of missing configuration file."""
        # Setup mocks
        mock_exists.return_value = False

        # Create config manager and try to load config
        config_manager = ConfigManager('config.yaml')
        with self.assertRaises(FileNotFoundError):
            config_manager.load_config()

        # Verify
        mock_exists.assert_called_once_with('config.yaml')
        mock_file.assert_not_called()

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_validate_config_valid(self, mock_yaml_load, mock_exists,
                                   mock_file):
        """Test validation of a valid configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Validate config
        try:
            config_manager.validate_config()
            validation_passed = True
        except Exception:
            validation_passed = False

        # Verify
        self.assertTrue(validation_passed)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_validate_config_missing_section(self, mock_yaml_load, mock_exists,
                                             mock_file):
        """Test validation with a missing required section."""
        # Setup mocks
        invalid_config = self.test_config.copy()
        del invalid_config['douban']  # Remove required section

        mock_exists.return_value = True
        mock_yaml_load.return_value = invalid_config
        mock_file.return_value.__enter__.return_value.read.return_value = yaml.dump(
            invalid_config)

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Validate config
        with self.assertRaises(ValueError):
            config_manager.validate_config()

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_douban_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting Douban configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get Douban config
        douban_config = config_manager.get_douban_config()

        # Verify
        self.assertEqual(douban_config, self.test_config['douban'])
        self.assertEqual(douban_config['user_id'], 'test_user')
        self.assertEqual(douban_config['cookie'], 'test_cookie')

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_database_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting database configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get database config
        db_config = config_manager.get_database_config()

        # Verify
        self.assertEqual(db_config, self.test_config['database'])
        self.assertEqual(db_config['url'], 'sqlite:///test.db')
        self.assertEqual(db_config['echo'], False)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_calibre_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting Calibre configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get Calibre config
        calibre_config = config_manager.get_calibre_config()

        # Verify
        self.assertEqual(calibre_config, self.test_config['calibre'])
        self.assertEqual(calibre_config['host'], 'http://localhost')
        self.assertEqual(calibre_config['port'], 8080)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_zlibrary_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting Z-Library configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get Z-Library config
        zlib_config = config_manager.get_zlibrary_config()

        # Verify
        self.assertEqual(zlib_config, self.test_config['zlibrary'])
        self.assertEqual(zlib_config['base_url'], 'https://zlibrary.example')
        self.assertEqual(zlib_config['format_priority'],
                         ['PDF', 'EPUB', 'MOBI'])

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_scheduler_config(self, mock_yaml_load, mock_exists,
                                  mock_file):
        """Test getting scheduler configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get scheduler config
        scheduler_config = config_manager.get_scheduler_config()

        # Verify
        self.assertEqual(scheduler_config, self.test_config['scheduler'])
        self.assertEqual(scheduler_config['enabled'], True)
        self.assertEqual(scheduler_config['sync_interval_days'], 1)

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_lark_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting Lark configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get Lark config
        lark_config = config_manager.get_lark_config()

        # Verify
        self.assertEqual(lark_config, self.test_config['lark'])
        self.assertEqual(lark_config['enabled'], True)
        self.assertEqual(lark_config['webhook_url'],
                         'https://open.feishu.cn/webhook/test')

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_logging_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting logging configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get logging config
        logging_config = config_manager.get_logging_config()

        # Verify
        self.assertEqual(logging_config, self.test_config['logging'])
        self.assertEqual(logging_config['level'], 'INFO')
        self.assertEqual(logging_config['file'], 'logs/app.log')

    @patch('builtins.open', new_callable=mock_open)
    @patch('os.path.exists')
    @patch('yaml.safe_load')
    def test_get_system_config(self, mock_yaml_load, mock_exists, mock_file):
        """Test getting system configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_yaml_load.return_value = self.test_config
        mock_file.return_value.__enter__.return_value.read.return_value = self.yaml_content

        # Create config manager and load config
        config_manager = ConfigManager('config.yaml')
        config_manager.load_config()

        # Get system config
        system_config = config_manager.get_system_config()

        # Verify
        self.assertEqual(system_config, self.test_config['system'])
        self.assertEqual(system_config['temp_dir'], '/tmp/temp')
        self.assertEqual(system_config['max_retries'], 3)


if __name__ == '__main__':
    unittest.main()
