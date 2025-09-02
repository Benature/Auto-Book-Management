import unittest
from unittest.mock import MagicMock, patch

import requests

from config.config_manager import ConfigManager
from services.calibre_service import CalibreService
from utils.logger import get_logger


class TestCalibreService(unittest.TestCase):
    """Test cases for CalibreService class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_mock = MagicMock(spec=ConfigManager)
        self.config_mock.get_calibre_config.return_value = {
            'host': 'http://localhost',
            'port': 8080,
            'username': 'test_user',
            'password': 'test_pass',
            'library': 'test_library'
        }
        self.logger_mock = MagicMock(spec=get_logger)
        self.calibre_service = CalibreService(self.config_mock,
                                              self.logger_mock)

    def test_init(self):
        """Test initialization of CalibreService."""
        self.assertEqual(self.calibre_service.base_url,
                         'http://localhost:8080')
        self.assertEqual(self.calibre_service.username, 'test_user')
        self.assertEqual(self.calibre_service.password, 'test_pass')
        self.assertEqual(self.calibre_service.library, 'test_library')



    @patch('services.calibre_service.requests.get')
    def test_search_books_by_title(self, mock_get):
        """Test searching books by title."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total_num': 1,
            'offset': 0,
            'num': 1,
            'sort': 'title',
            'sort_order': 'asc',
            'base_url': '/ajax/books',
            'query': 'title:"Test Book"',
            'book_ids': [1],
            'vl': {
                '1': {
                    'title': 'Test Book',
                    'authors': ['Test Author']
                }
            }
        }
        mock_get.return_value = mock_response

        results = self.calibre_service.search_books(title="Test Book")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Test Book')
        self.assertEqual(results[0]['authors'], ['Test Author'])
        mock_get.assert_called_once()

    @patch('services.calibre_service.requests.get')
    def test_search_books_by_author(self, mock_get):
        """Test searching books by author."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total_num': 1,
            'offset': 0,
            'num': 1,
            'sort': 'title',
            'sort_order': 'asc',
            'base_url': '/ajax/books',
            'query': 'authors:"Test Author"',
            'book_ids': [1],
            'vl': {
                '1': {
                    'title': 'Test Book',
                    'authors': ['Test Author']
                }
            }
        }
        mock_get.return_value = mock_response

        results = self.calibre_service.search_books(author="Test Author")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Test Book')
        self.assertEqual(results[0]['authors'], ['Test Author'])
        mock_get.assert_called_once()

    @patch('services.calibre_service.requests.get')
    def test_search_books_by_isbn(self, mock_get):
        """Test searching books by ISBN."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'total_num': 1,
            'offset': 0,
            'num': 1,
            'sort': 'title',
            'sort_order': 'asc',
            'base_url': '/ajax/books',
            'query': 'identifiers:isbn:1234567890',
            'book_ids': [1],
            'vl': {
                '1': {
                    'title': 'Test Book',
                    'authors': ['Test Author'],
                    'identifiers': {
                        'isbn': '1234567890'
                    }
                }
            }
        }
        mock_get.return_value = mock_response

        results = self.calibre_service.search_books(isbn="1234567890")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Test Book')
        self.assertEqual(results[0]['identifiers']['isbn'], '1234567890')
        mock_get.assert_called_once()

    @patch('services.calibre_service.requests.get')
    def test_get_book_details(self, mock_get):
        """Test getting book details."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'book_id': 1,
            'title': 'Test Book',
            'authors': ['Test Author'],
            'identifiers': {
                'isbn': '1234567890'
            },
            'formats': ['EPUB', 'PDF']
        }
        mock_get.return_value = mock_response

        book_details = self.calibre_service.get_book_details(1)
        self.assertEqual(book_details['title'], 'Test Book')
        self.assertEqual(book_details['authors'], ['Test Author'])
        self.assertEqual(book_details['identifiers']['isbn'], '1234567890')
        self.assertEqual(book_details['formats'], ['EPUB', 'PDF'])
        mock_get.assert_called_once()

    def test_find_best_match_exact_title_author(self):
        """Test finding best match with exact title and author."""
        books = [{
            'title': 'Test Book',
            'authors': ['Test Author'],
            'id': 1
        }, {
            'title': 'Another Book',
            'authors': ['Another Author'],
            'id': 2
        }]

        best_match = self.calibre_service.find_best_match(
            books, 'Test Book', 'Test Author')
        self.assertEqual(best_match['id'], 1)

    def test_find_best_match_similar_title(self):
        """Test finding best match with similar title."""
        books = [{
            'title': 'Test Book',
            'authors': ['Test Author'],
            'id': 1
        }, {
            'title': 'Test Book: Extended Edition',
            'authors': ['Test Author'],
            'id': 2
        }]

        best_match = self.calibre_service.find_best_match(
            books, 'Test Book Extended', 'Test Author')
        self.assertEqual(best_match['id'], 2)

    def test_string_similarity(self):
        """Test string similarity calculation."""
        similarity = self.calibre_service._string_similarity('Test', 'test')
        self.assertGreaterEqual(similarity,
                                0.9)  # Should be very similar despite case

        similarity = self.calibre_service._string_similarity(
            'Test Book', 'Test Book: Extended Edition')
        self.assertGreaterEqual(similarity,
                                0.5)  # Should have moderate similarity

        similarity = self.calibre_service._string_similarity(
            'Test Book', 'Completely Different')
        self.assertLessEqual(similarity, 0.3)  # Should have low similarity

    @patch('services.calibre_service.requests.post')
    def test_upload_book(self, mock_post):
        """Test uploading a book to Calibre."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'book_id': 1}
        mock_post.return_value = mock_response

        book_id = self.calibre_service.upload_book('/path/to/book.epub',
                                                   'Test Book', 'Test Author')
        self.assertEqual(book_id, 1)
        mock_post.assert_called_once()


if __name__ == '__main__':
    unittest.main()
