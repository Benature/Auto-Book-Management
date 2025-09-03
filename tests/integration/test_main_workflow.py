import os
import shutil
import tempfile
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.config_manager import ConfigManager
from db.database import Database
from db.models import Base, BookStatus, DoubanBook, DownloadRecord, SyncTask
from scrapers.douban_scraper import DoubanScraper
from services.calibre_service import CalibreService
from services.lark_service import LarkService
from services.zlibrary_service import ZLibraryService
from utils.logger import get_logger, setup_logger


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
              enabled: false
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
        # Create real service instances with disabled features for testing
        # Services will use the test configuration and avoid real network calls
        self.douban_scraper = DoubanScraper(self.config_manager, self.logger)
        self.zlibrary_service = ZLibraryService(self.config_manager, self.logger)
        self.calibre_service = CalibreService(self.config_manager, self.logger)
        self.lark_service = LarkService(self.config_manager, self.logger)

        # Clear database tables
        session = self.database.get_session()
        session.query(DownloadRecord).delete()
        session.query(DoubanBook).delete()
        session.query(SyncTask).delete()
        session.commit()

    def test_database_operations(self):
        """Test basic database operations without external dependencies."""
        # Test data for books
        test_books_data = [{
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

        # Test workflow: Add books to database
        added_books = []
        for book_data in test_books_data:
            book = DoubanBook(douban_id=book_data['douban_id'],
                              title=book_data['title'],
                              author=book_data['author'],
                              publisher=book_data['publisher'],
                              isbn=book_data['isbn'],
                              url=book_data['url'],
                              cover_url=book_data['cover_url'],
                              status=BookStatus.NEW)
            added_book = self.database.add_douban_book(book)
            added_books.append(added_book)

        # Verify books were added to database
        session = self.database.get_session()
        db_books = session.query(DoubanBook).all()
        self.assertEqual(len(db_books), 2)

        # Test status updates
        for book in added_books:
            # Test status transitions
            book.status = BookStatus.SEARCH_QUEUED
            updated_book = self.database.update_douban_book(book)
            self.assertEqual(updated_book.status, BookStatus.SEARCH_QUEUED)

            # Test adding download record
            download_record = DownloadRecord(
                book_id=book.id,
                source='zlibrary',
                format='PDF',
                file_path=os.path.join(self.download_dir, f'{book.title.replace(" ", "_")}.pdf'),
                file_size=1024000,
                success=True)
            added_record = self.database.add_download_record(download_record)
            self.assertIsNotNone(added_record.id)

        # Verify final state
        updated_books = session.query(DoubanBook).all()
        for book in updated_books:
            self.assertEqual(book.status, BookStatus.SEARCH_QUEUED)

        # Check download records
        download_records = session.query(DownloadRecord).all()
        self.assertEqual(len(download_records), 2)
        for record in download_records:
            self.assertEqual(record.format, 'PDF')
            self.assertTrue(record.success)

    def test_service_initialization(self):
        """Test that all services can be initialized with the test configuration."""
        # Test service initialization - should not raise exceptions
        self.assertIsNotNone(self.douban_scraper)
        self.assertIsNotNone(self.zlibrary_service)
        self.assertIsNotNone(self.calibre_service)
        self.assertIsNotNone(self.lark_service)
        
        # Test that services have proper configuration
        # These services should be disabled for testing to avoid network calls
        self.assertFalse(self.lark_service.enabled)  # Lark should be disabled in test config
        
        # Test database operations work
        session = self.database.get_session()
        self.assertIsNotNone(session)
        
        # Test logging works
        self.logger.info("Test log message")
        
        # Test that temporary directories exist
        self.assertTrue(os.path.exists(self.download_dir))
        self.assertTrue(os.path.exists(self.temp_data_dir))
        self.assertTrue(os.path.exists(self.log_dir))


if __name__ == '__main__':
    unittest.main()
