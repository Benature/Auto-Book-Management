import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.config_manager import ConfigManager
from db.database import Database
from db.models import Base, DoubanBook, DownloadRecord, SyncTask, BookStatus
from scrapers.douban_scraper import DoubanScraper
from services.zlibrary_service import ZLibraryService
from services.calibre_service import CalibreService
from services.lark_service import LarkService
from utils.logger import setup_logger, get_logger


class TestMainWorkflow(unittest.TestCase):
    """Integration tests for the main workflow of the application."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures that are used for all tests."""
        # Create temporary directories
        cls.temp_dir = tempfile.mkdtemp()
        cls.download_dir = os.path.join(cls.temp_dir, 'downloads')
        cls.temp_data_dir = os.path.join(cls.temp_dir, 'temp')
        cls.log_dir = os.path.join(cls.temp_dir, 'logs')

        # Create directories
        os.makedirs(cls.download_dir, exist_ok=True)
        os.makedirs(cls.temp_data_dir, exist_ok=True)
        os.makedirs(cls.log_dir, exist_ok=True)

        # Create a temporary config file
        cls.config_file = os.path.join(cls.temp_dir, 'config.yaml')
        with open(cls.config_file, 'w', encoding='utf-8') as f:
            f.write(f'''
            douban:
              user_id: test_user
              cookie: test_cookie
              user_agent: test_agent
              wishlist_url: https://book.douban.com/people/{{user_id}}/wish
            database:
              url: sqlite:///{os.path.join(cls.temp_dir, 'test.db')}
              echo: false
            calibre:
              host: http://localhost
              port: 8080
              username: test_user
              password: test_pass
              library: test_library
            zlibrary:
              base_url: https://zlibrary.example
              email: test@example.com
              password: test_pass
              download_dir: {cls.download_dir}
              format_priority: [PDF, EPUB, MOBI]
            scheduler:
              enabled: true
              sync_interval_days: 1
              sync_time: "03:00"
              cleanup_interval_days: 7
            lark:
              enabled: true
              webhook_url: https://open.feishu.cn/webhook/test
              secret: test_secret
            logging:
              level: INFO
              file: {os.path.join(cls.log_dir, 'app.log')}
              max_size_mb: 10
              backup_count: 5
            system:
              temp_dir: {cls.temp_data_dir}
              max_retries: 3
              retry_delay: 5
            ''')

        # Setup logger
        cls.logger = setup_logger('test_logger',
                                  os.path.join(cls.log_dir, 'test.log'))

        # Create config manager
        cls.config_manager = ConfigManager(cls.config_file)

        # Create database
        cls.database = Database(cls.config_manager, cls.logger)
        Base.metadata.create_all(cls.database.engine)

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        # Close database session
        if hasattr(cls, 'database') and cls.database.session:
            cls.database.close_session()

        # Remove temporary directory and all its contents
        if hasattr(cls, 'temp_dir') and os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

    def setUp(self):
        """Set up test fixtures for each test."""
        # Create mock services
        self.douban_scraper = MagicMock(spec=DoubanScraper)
        self.zlibrary_service = MagicMock(spec=ZLibraryService)
        self.calibre_service = MagicMock(spec=CalibreService)
        self.lark_service = MagicMock(spec=LarkService)

        # Clear database tables
        session = self.database.get_session()
        session.query(DownloadRecord).delete()
        session.query(DoubanBook).delete()
        session.query(SyncTask).delete()
        session.commit()

    def test_douban_to_zlibrary_to_calibre_workflow(self):
        """Test the main workflow from Douban to Z-Library to Calibre."""
        # Setup mock data
        # 1. Mock Douban books
        mock_douban_books = [{
            'douban_id': '12345',
            'title': 'Test Book 1',
            'author': 'Test Author 1',
            'publisher': 'Test Publisher 1',
            'isbn': '1234567890',
            'url': 'http://douban.com/book/12345',
            'cover_url': 'http://douban.com/covers/12345.jpg'
        }, {
            'douban_id': '67890',
            'title': 'Test Book 2',
            'author': 'Test Author 2',
            'publisher': 'Test Publisher 2',
            'isbn': '0987654321',
            'url': 'http://douban.com/book/67890',
            'cover_url': 'http://douban.com/covers/67890.jpg'
        }]

        # 2. Mock Z-Library search results
        mock_zlib_results = [{
            'title':
            'Test Book 1',
            'author':
            'Test Author 1',
            'publisher':
            'Test Publisher 1',
            'year':
            '2023',
            'language':
            'English',
            'format':
            'PDF',
            'size':
            '2.5 MB',
            'download_url':
            'http://zlibrary.example/download/12345',
            'cover_url':
            'http://zlibrary.example/covers/12345.jpg'
        }]

        # 3. Mock Calibre search results
        mock_calibre_results = []

        # Configure mocks
        # 1. Douban Scraper
        self.douban_scraper.get_wishlist.return_value = mock_douban_books

        # 2. Z-Library Service
        self.zlibrary_service.test_connection.return_value = True
        self.zlibrary_service.search_books.return_value = mock_zlib_results
        self.zlibrary_service.download_book.return_value = {
            'success': True,
            'file_path': os.path.join(self.download_dir, 'test_book_1.pdf'),
            'format': 'PDF',
            'file_size': 2621440  # 2.5 MB in bytes
        }

        # 3. Calibre Service
        self.calibre_service.test_connection.return_value = True
        self.calibre_service.search_books.return_value = mock_calibre_results  # Empty, book not in Calibre yet
        self.calibre_service.upload_book.return_value = 1  # Calibre book ID

        # 4. Lark Service
        self.lark_service.send_book_download_notification.return_value = True
        self.lark_service.send_sync_task_summary.return_value = True

        # Execute workflow
        # 1. Fetch books from Douban
        douban_books = self.douban_scraper.get_wishlist()
        self.assertEqual(len(douban_books), 2)

        # 2. Add books to database
        added_books = []
        for book_data in douban_books:
            book = DoubanBook(douban_id=book_data['douban_id'],
                              title=book_data['title'],
                              author=book_data['author'],
                              publisher=book_data['publisher'],
                              isbn=book_data['isbn'],
                              url=book_data['url'],
                              cover_url=book_data['cover_url'],
                              status=BookStatus.PENDING)
            added_book = self.database.add_douban_book(book)
            added_books.append(added_book)

        # Verify books were added to database
        session = self.database.get_session()
        db_books = session.query(DoubanBook).all()
        self.assertEqual(len(db_books), 2)

        # 3. Process each book
        for book in added_books:
            # 3.1 Check if book exists in Calibre
            calibre_books = self.calibre_service.search_books(
                title=book.title, author=book.author)
            if calibre_books:  # Book already in Calibre
                book.status = BookStatus.IN_CALIBRE
                self.database.update_douban_book(book)
                continue

            # 3.2 Search Z-Library for the book
            zlib_results = self.zlibrary_service.search_books(
                title=book.title, author=book.author)
            if not zlib_results:  # Book not found in Z-Library
                book.status = BookStatus.NOT_FOUND
                self.database.update_douban_book(book)
                continue

            # 3.3 Download the book from Z-Library
            download_result = self.zlibrary_service.download_book(
                zlib_results[0]['download_url'])
            if not download_result['success']:  # Download failed
                book.status = BookStatus.DOWNLOAD_FAILED
                self.database.update_douban_book(book)
                continue

            # 3.4 Add download record
            download_record = DownloadRecord(
                book_id=book.id,
                source='zlibrary',
                format=download_result['format'],
                file_path=download_result['file_path'],
                file_size=download_result['file_size'],
                success=True)
            self.database.add_download_record(download_record)

            # 3.5 Upload to Calibre
            calibre_id = self.calibre_service.upload_book(
                file_path=download_result['file_path'],
                title=book.title,
                author=book.author)

            if calibre_id:  # Upload successful
                book.calibre_id = calibre_id
                book.status = BookStatus.IN_CALIBRE
            else:  # Upload failed
                book.status = BookStatus.UPLOAD_FAILED

            self.database.update_douban_book(book)

            # 3.6 Send notification
            self.lark_service.send_book_download_notification(
                title=book.title,
                author=book.author,
                publisher=book.publisher,
                isbn=book.isbn,
                format=download_result['format'],
                file_size=download_result['file_size'],
                cover_url=book.cover_url,
                douban_url=book.url,
                calibre_id=calibre_id)

        # Verify final state
        # 1. Check book status in database
        updated_books = session.query(DoubanBook).all()
        for book in updated_books:
            if book.title == 'Test Book 1':  # This book should be processed successfully
                self.assertEqual(book.status, BookStatus.IN_CALIBRE)
                self.assertEqual(book.calibre_id, 1)
            elif book.title == 'Test Book 2':  # This book should not be found in Z-Library
                self.assertEqual(book.status, BookStatus.NOT_FOUND)

        # 2. Check download records
        download_records = session.query(DownloadRecord).all()
        self.assertEqual(len(download_records),
                         1)  # Only one book should be downloaded
        self.assertEqual(download_records[0].format, 'PDF')
        self.assertTrue(download_records[0].success)

        # 3. Verify service calls
        self.douban_scraper.get_wishlist.assert_called_once()
        self.zlibrary_service.search_books.assert_called()
        self.zlibrary_service.download_book.assert_called_once_with(
            mock_zlib_results[0]['download_url'])
        self.calibre_service.upload_book.assert_called_once()
        self.lark_service.send_book_download_notification.assert_called_once()


if __name__ == '__main__':
    unittest.main()
