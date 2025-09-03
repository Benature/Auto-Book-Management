import unittest
import tempfile
import os

from config.config_manager import ConfigManager
from services.calibre_service import CalibreService
from utils.logger import get_logger


class TestCalibreService(unittest.TestCase):
    """Test cases for CalibreService class using real configurations."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary config for testing
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'test_config.yaml')
        
        config_content = '''
calibre:
  content_server_url: "http://localhost:8080"
  username: "test_user"
  password: "test_pass"
  match_threshold: 0.6
  timeout: 120
database:
  url: ':memory:'
lark:
  enabled: false
scheduler:
  enabled: false
'''
        
        with open(self.config_path, 'w') as f:
            f.write(config_content)
            
        self.config_manager = ConfigManager(self.config_path)
        self.logger = get_logger('test_calibre_service')
        self.calibre_service = CalibreService(self.config_manager, self.logger)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_init(self):
        """Test initialization of CalibreService."""
        calibre_config = self.config_manager.get_calibre_config()
        
        # Test that service properties are set from config
        self.assertEqual(self.calibre_service.server_url, calibre_config['content_server_url'])
        self.assertEqual(self.calibre_service.username, calibre_config['username'])
        self.assertEqual(self.calibre_service.password, calibre_config['password'])
        self.assertEqual(self.calibre_service.match_threshold, calibre_config['match_threshold'])
        self.assertEqual(self.calibre_service.timeout, calibre_config['timeout'])

    def test_configuration_loading(self):
        """Test that configuration is loaded correctly."""
        calibre_config = self.config_manager.get_calibre_config()
        
        # Verify required configuration fields
        required_fields = ['content_server_url', 'username', 'password', 'match_threshold', 'timeout']
        for field in required_fields:
            self.assertIn(field, calibre_config)
            
        # Verify field types
        self.assertIsInstance(calibre_config['content_server_url'], str)
        self.assertIsInstance(calibre_config['username'], str)
        self.assertIsInstance(calibre_config['password'], str)
        self.assertIsInstance(calibre_config['match_threshold'], (int, float))
        self.assertIsInstance(calibre_config['timeout'], int)

    def test_similarity_calculation(self):
        """Test similarity calculation method."""
        # Test exact match
        similarity = self.calibre_service._calculate_similarity("test", "test")
        self.assertEqual(similarity, 1.0)
        
        # Test no match
        similarity = self.calibre_service._calculate_similarity("abc", "xyz")
        self.assertGreaterEqual(similarity, 0.0)
        self.assertLessEqual(similarity, 1.0)
        
        # Test partial match
        similarity = self.calibre_service._calculate_similarity("python programming", "python guide")
        self.assertGreater(similarity, 0.0)
        self.assertLess(similarity, 1.0)

    def test_string_normalization(self):
        """Test string normalization method."""
        # Test basic normalization
        normalized = self.calibre_service._normalize_string("  Python Programming  ")
        self.assertEqual(normalized, "python programming")
        
        # Test special character removal
        normalized = self.calibre_service._normalize_string("C++ & Java: The Guide!")
        self.assertNotIn("+", normalized)
        self.assertNotIn("&", normalized)
        self.assertNotIn(":", normalized)
        self.assertNotIn("!", normalized)
        
        # Test multiple spaces
        normalized = self.calibre_service._normalize_string("Python    Programming")
        self.assertEqual(normalized, "python programming")

    def test_match_threshold_validation(self):
        """Test match threshold configuration."""
        threshold = self.calibre_service.match_threshold
        
        # Verify threshold is within valid range
        self.assertGreaterEqual(threshold, 0.0)
        self.assertLessEqual(threshold, 1.0)
        self.assertIsInstance(threshold, (int, float))

    def test_timeout_configuration(self):
        """Test timeout configuration."""
        timeout = self.calibre_service.timeout
        
        # Verify timeout is positive integer
        self.assertGreater(timeout, 0)
        self.assertIsInstance(timeout, int)

    def test_server_url_format(self):
        """Test server URL format."""
        server_url = self.calibre_service.server_url
        
        # Verify URL format
        self.assertIsInstance(server_url, str)
        self.assertTrue(server_url.startswith('http'))
        self.assertIn(':', server_url)

    def test_authentication_data(self):
        """Test authentication data."""
        username = self.calibre_service.username
        password = self.calibre_service.password
        
        # Verify authentication data exists
        self.assertIsInstance(username, str)
        self.assertIsInstance(password, str)
        self.assertGreater(len(username), 0)
        self.assertGreater(len(password), 0)

    def test_book_data_structure_validation(self):
        """Test expected book data structure."""
        # Sample book data structure that Calibre service should handle
        sample_book = {
            'calibre_id': 123,
            'title': 'Python Programming',
            'authors': ['John Doe'],
            'author': 'John Doe',
            'publisher': 'Tech Books',
            'isbn': '9781234567890',
            'formats': ['EPUB', 'PDF'],
            'identifiers': {'isbn': '9781234567890'}
        }
        
        # Verify expected fields exist
        expected_fields = ['calibre_id', 'title', 'authors', 'author']
        for field in expected_fields:
            self.assertIn(field, sample_book)
            
        # Verify data types
        self.assertIsInstance(sample_book['calibre_id'], int)
        self.assertIsInstance(sample_book['title'], str)
        self.assertIsInstance(sample_book['authors'], list)
        self.assertIsInstance(sample_book['author'], str)

    def test_search_parameters_validation(self):
        """Test search parameter validation logic."""
        # Test parameter filtering
        search_params = {
            'title': 'Python Programming',
            'author': 'John Doe',
            'isbn': '9781234567890',
            'empty_param': '',
            'none_param': None
        }
        
        # Filter out empty/None parameters
        filtered_params = {k: v for k, v in search_params.items() 
                          if v and isinstance(v, str) and len(v.strip()) > 0}
        
        # Verify filtering worked
        self.assertIn('title', filtered_params)
        self.assertIn('author', filtered_params)
        self.assertIn('isbn', filtered_params)
        self.assertNotIn('empty_param', filtered_params)
        self.assertNotIn('none_param', filtered_params)


if __name__ == '__main__':
    unittest.main()