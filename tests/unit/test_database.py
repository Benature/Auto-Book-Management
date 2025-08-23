import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.database import Database
from db.models import Base, DoubanBook, DownloadRecord, SyncTask, BookStatus
from config.config_manager import ConfigManager
from utils.logger import get_logger


class TestDatabase(unittest.TestCase):
    """Test cases for Database class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary SQLite database for testing
        self.temp_db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_file.close()
        self.db_url = f'sqlite:///{self.temp_db_file.name}'
        
        # Mock config manager
        self.config_mock = MagicMock(spec=ConfigManager)
        self.config_mock.get_database_config.return_value = {
            'url': self.db_url,
            'echo': False
        }
        
        # Mock logger
        self.logger_mock = MagicMock(spec=get_logger)
        
        # Create database instance
        self.database = Database(self.config_mock, self.logger_mock)
        
        # Create tables
        Base.metadata.create_all(self.database.engine)

    def tearDown(self):
        """Tear down test fixtures."""
        # Close session
        if hasattr(self, 'database') and self.database.session:
            self.database.session.close()
        
        # Remove temporary database file
        if hasattr(self, 'temp_db_file') and os.path.exists(self.temp_db_file.name):
            os.unlink(self.temp_db_file.name)

    def test_init(self):
        """Test initialization of Database."""
        self.assertIsNotNone(self.database.engine)
        self.assertIsNotNone(self.database.Session)
        self.assertIsNone(self.database.session)  # Session should be None until get_session is called

    def test_get_session(self):
        """Test getting a database session."""
        session = self.database.get_session()
        self.assertIsNotNone(session)
        self.assertEqual(session, self.database.session)  # Should store the session

    def test_close_session(self):
        """Test closing a database session."""
        session = self.database.get_session()
        self.assertIsNotNone(self.database.session)
        
        self.database.close_session()
        self.assertIsNone(self.database.session)  # Session should be None after closing

    def test_add_douban_book(self):
        """Test adding a DoubanBook to the database."""
        book = DoubanBook(
            douban_id='12345',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            isbn='1234567890',
            url='http://test.com/book',
            cover_url='http://test.com/cover.jpg',
            status=BookStatus.PENDING
        )
        
        # Add book
        added_book = self.database.add_douban_book(book)
        
        # Verify book was added
        self.assertIsNotNone(added_book.id)  # Should have an ID after being added
        
        # Query to verify
        session = self.database.get_session()
        queried_book = session.query(DoubanBook).filter_by(douban_id='12345').first()
        self.assertIsNotNone(queried_book)
        self.assertEqual(queried_book.title, 'Test Book')

    def test_get_douban_book_by_id(self):
        """Test getting a DoubanBook by ID."""
        # Add a book
        book = DoubanBook(
            douban_id='12345',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            isbn='1234567890',
            url='http://test.com/book',
            cover_url='http://test.com/cover.jpg',
            status=BookStatus.PENDING
        )
        added_book = self.database.add_douban_book(book)
        
        # Get book by ID
        retrieved_book = self.database.get_douban_book_by_id(added_book.id)
        
        # Verify
        self.assertIsNotNone(retrieved_book)
        self.assertEqual(retrieved_book.douban_id, '12345')
        self.assertEqual(retrieved_book.title, 'Test Book')

    def test_get_douban_book_by_douban_id(self):
        """Test getting a DoubanBook by Douban ID."""
        # Add a book
        book = DoubanBook(
            douban_id='12345',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            isbn='1234567890',
            url='http://test.com/book',
            cover_url='http://test.com/cover.jpg',
            status=BookStatus.PENDING
        )
        self.database.add_douban_book(book)
        
        # Get book by Douban ID
        retrieved_book = self.database.get_douban_book_by_douban_id('12345')
        
        # Verify
        self.assertIsNotNone(retrieved_book)
        self.assertEqual(retrieved_book.title, 'Test Book')

    def test_update_douban_book(self):
        """Test updating a DoubanBook."""
        # Add a book
        book = DoubanBook(
            douban_id='12345',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            isbn='1234567890',
            url='http://test.com/book',
            cover_url='http://test.com/cover.jpg',
            status=BookStatus.PENDING
        )
        added_book = self.database.add_douban_book(book)
        
        # Update book
        added_book.title = 'Updated Book Title'
        added_book.status = BookStatus.DOWNLOADED
        updated_book = self.database.update_douban_book(added_book)
        
        # Verify
        self.assertEqual(updated_book.title, 'Updated Book Title')
        self.assertEqual(updated_book.status, BookStatus.DOWNLOADED)
        
        # Query to verify
        session = self.database.get_session()
        queried_book = session.query(DoubanBook).filter_by(douban_id='12345').first()
        self.assertEqual(queried_book.title, 'Updated Book Title')
        self.assertEqual(queried_book.status, BookStatus.DOWNLOADED)

    def test_get_pending_books(self):
        """Test getting pending books."""
        # Add books with different statuses
        book1 = DoubanBook(
            douban_id='12345',
            title='Pending Book',
            author='Test Author',
            status=BookStatus.PENDING
        )
        book2 = DoubanBook(
            douban_id='67890',
            title='Downloaded Book',
            author='Test Author',
            status=BookStatus.DOWNLOADED
        )
        self.database.add_douban_book(book1)
        self.database.add_douban_book(book2)
        
        # Get pending books
        pending_books = self.database.get_pending_books()
        
        # Verify
        self.assertEqual(len(pending_books), 1)
        self.assertEqual(pending_books[0].title, 'Pending Book')
        self.assertEqual(pending_books[0].status, BookStatus.PENDING)

    def test_add_download_record(self):
        """Test adding a DownloadRecord."""
        # Add a book first
        book = DoubanBook(
            douban_id='12345',
            title='Test Book',
            author='Test Author',
            status=BookStatus.PENDING
        )
        added_book = self.database.add_douban_book(book)
        
        # Add download record
        record = DownloadRecord(
            book_id=added_book.id,
            source='zlibrary',
            format='PDF',
            file_path='/path/to/book.pdf',
            file_size=1024,
            success=True
        )
        added_record = self.database.add_download_record(record)
        
        # Verify
        self.assertIsNotNone(added_record.id)
        
        # Query to verify
        session = self.database.get_session()
        queried_record = session.query(DownloadRecord).filter_by(book_id=added_book.id).first()
        self.assertIsNotNone(queried_record)
        self.assertEqual(queried_record.format, 'PDF')
        self.assertEqual(queried_record.success, True)

    def test_get_download_records_for_book(self):
        """Test getting download records for a book."""
        # Add a book
        book = DoubanBook(
            douban_id='12345',
            title='Test Book',
            author='Test Author',
            status=BookStatus.PENDING
        )
        added_book = self.database.add_douban_book(book)
        
        # Add multiple download records
        record1 = DownloadRecord(
            book_id=added_book.id,
            source='zlibrary',
            format='PDF',
            file_path='/path/to/book.pdf',
            file_size=1024,
            success=True
        )
        record2 = DownloadRecord(
            book_id=added_book.id,
            source='zlibrary',
            format='EPUB',
            file_path='/path/to/book.epub',
            file_size=512,
            success=True
        )
        self.database.add_download_record(record1)
        self.database.add_download_record(record2)
        
        # Get records
        records = self.database.get_download_records_for_book(added_book.id)
        
        # Verify
        self.assertEqual(len(records), 2)
        formats = [record.format for record in records]
        self.assertIn('PDF', formats)
        self.assertIn('EPUB', formats)

    def test_add_sync_task(self):
        """Test adding a SyncTask."""
        # Add a task
        task = SyncTask(
            task_type='douban_sync',
            status='pending',
            details='{"user_id": "12345"}'
        )
        added_task = self.database.add_sync_task(task)
        
        # Verify
        self.assertIsNotNone(added_task.id)
        
        # Query to verify
        session = self.database.get_session()
        queried_task = session.query(SyncTask).filter_by(task_type='douban_sync').first()
        self.assertIsNotNone(queried_task)
        self.assertEqual(queried_task.status, 'pending')

    def test_update_sync_task(self):
        """Test updating a SyncTask."""
        # Add a task
        task = SyncTask(
            task_type='douban_sync',
            status='pending',
            details='{"user_id": "12345"}'
        )
        added_task = self.database.add_sync_task(task)
        
        # Update task
        added_task.status = 'completed'
        added_task.details = '{"user_id": "12345", "books_synced": 10}'
        updated_task = self.database.update_sync_task(added_task)
        
        # Verify
        self.assertEqual(updated_task.status, 'completed')
        self.assertEqual(updated_task.details, '{"user_id": "12345", "books_synced": 10}')
        
        # Query to verify
        session = self.database.get_session()
        queried_task = session.query(SyncTask).filter_by(id=added_task.id).first()
        self.assertEqual(queried_task.status, 'completed')

    def test_get_latest_sync_task(self):
        """Test getting the latest sync task of a specific type."""
        # Add multiple tasks with different timestamps
        task1 = SyncTask(
            task_type='douban_sync',
            status='completed',
            details='{"user_id": "12345"}'
        )
        task2 = SyncTask(
            task_type='douban_sync',
            status='pending',
            details='{"user_id": "12345"}'
        )
        self.database.add_sync_task(task1)
        
        # Add a small delay to ensure different timestamps
        import time
        time.sleep(0.1)
        
        self.database.add_sync_task(task2)
        
        # Get latest task
        latest_task = self.database.get_latest_sync_task('douban_sync')
        
        # Verify
        self.assertIsNotNone(latest_task)
        self.assertEqual(latest_task.status, 'pending')  # Should be the second task


if __name__ == '__main__':
    unittest.main()