import unittest
from unittest.mock import MagicMock, patch
import time
from datetime import datetime, timedelta
from scheduler.task_scheduler import TaskScheduler
from config.config_manager import ConfigManager
from utils.logger import get_logger


class TestTaskScheduler(unittest.TestCase):
    """Test cases for TaskScheduler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_mock = MagicMock(spec=ConfigManager)
        self.config_mock.get_scheduler_config.return_value = {
            'enabled': True,
            'sync_interval_days': 1,
            'sync_time': '03:00',
            'cleanup_interval_days': 7
        }
        self.logger_mock = MagicMock(spec=get_logger)
        self.scheduler = TaskScheduler(self.config_mock, self.logger_mock)

    def test_init(self):
        """Test initialization of TaskScheduler."""
        self.assertTrue(self.scheduler.enabled)
        self.assertEqual(self.scheduler.sync_interval_days, 1)
        self.assertEqual(self.scheduler.sync_time, '03:00')
        self.assertEqual(self.scheduler.cleanup_interval_days, 7)
        self.assertEqual(len(self.scheduler.tasks), 0)

    def test_add_task(self):
        """Test adding a task to the scheduler."""
        # Create a mock task function
        task_func = MagicMock()
        task_func.__name__ = 'test_task'
        
        # Add task
        task_id = self.scheduler.add_task(
            name='Test Task',
            func=task_func,
            args=(1, 2),
            kwargs={'key': 'value'},
            interval_days=2,
            specific_time='12:00',
            enabled=True
        )
        
        # Verify
        self.assertIsNotNone(task_id)
        self.assertEqual(len(self.scheduler.tasks), 1)
        self.assertIn(task_id, self.scheduler.tasks)
        
        task = self.scheduler.tasks[task_id]
        self.assertEqual(task['name'], 'Test Task')
        self.assertEqual(task['func'], task_func)
        self.assertEqual(task['args'], (1, 2))
        self.assertEqual(task['kwargs'], {'key': 'value'})
        self.assertEqual(task['interval_days'], 2)
        self.assertEqual(task['specific_time'], '12:00')
        self.assertTrue(task['enabled'])
        self.assertIsNotNone(task['last_run'])
        self.assertIsNotNone(task['next_run'])

    def test_add_daily_task(self):
        """Test adding a daily task."""
        task_func = MagicMock()
        task_func.__name__ = 'daily_task'
        
        task_id = self.scheduler.add_daily_task(
            name='Daily Task',
            func=task_func,
            specific_time='08:00'
        )
        
        # Verify
        self.assertIsNotNone(task_id)
        task = self.scheduler.tasks[task_id]
        self.assertEqual(task['interval_days'], 1)
        self.assertEqual(task['specific_time'], '08:00')

    def test_add_weekly_task(self):
        """Test adding a weekly task."""
        task_func = MagicMock()
        task_func.__name__ = 'weekly_task'
        
        task_id = self.scheduler.add_weekly_task(
            name='Weekly Task',
            func=task_func,
            specific_time='10:00'
        )
        
        # Verify
        self.assertIsNotNone(task_id)
        task = self.scheduler.tasks[task_id]
        self.assertEqual(task['interval_days'], 7)
        self.assertEqual(task['specific_time'], '10:00')

    def test_enable_disable_task(self):
        """Test enabling and disabling a task."""
        # Add a task
        task_func = MagicMock()
        task_func.__name__ = 'test_task'
        task_id = self.scheduler.add_task(
            name='Test Task',
            func=task_func,
            interval_days=1
        )
        
        # Disable task
        self.scheduler.disable_task(task_id)
        self.assertFalse(self.scheduler.tasks[task_id]['enabled'])
        
        # Enable task
        self.scheduler.enable_task(task_id)
        self.assertTrue(self.scheduler.tasks[task_id]['enabled'])

    def test_get_task_status(self):
        """Test getting task status."""
        # Add a task
        task_func = MagicMock()
        task_func.__name__ = 'test_task'
        task_id = self.scheduler.add_task(
            name='Test Task',
            func=task_func,
            interval_days=1
        )
        
        # Get status
        status = self.scheduler.get_task_status(task_id)
        
        # Verify
        self.assertIsNotNone(status)
        self.assertEqual(status['name'], 'Test Task')
        self.assertTrue(status['enabled'])
        self.assertIn('last_run', status)
        self.assertIn('next_run', status)

    def test_get_all_task_statuses(self):
        """Test getting all task statuses."""
        # Add multiple tasks
        task_func1 = MagicMock()
        task_func1.__name__ = 'task1'
        task_id1 = self.scheduler.add_task(
            name='Task 1',
            func=task_func1,
            interval_days=1
        )
        
        task_func2 = MagicMock()
        task_func2.__name__ = 'task2'
        task_id2 = self.scheduler.add_task(
            name='Task 2',
            func=task_func2,
            interval_days=2
        )
        
        # Get all statuses
        statuses = self.scheduler.get_all_task_statuses()
        
        # Verify
        self.assertEqual(len(statuses), 2)
        self.assertIn(task_id1, statuses)
        self.assertIn(task_id2, statuses)
        self.assertEqual(statuses[task_id1]['name'], 'Task 1')
        self.assertEqual(statuses[task_id2]['name'], 'Task 2')

    def test_run_task(self):
        """Test running a task."""
        # Create a mock task function
        task_func = MagicMock()
        task_func.__name__ = 'test_task'
        
        # Add task
        task_id = self.scheduler.add_task(
            name='Test Task',
            func=task_func,
            args=(1, 2),
            kwargs={'key': 'value'},
            interval_days=1
        )
        
        # Run task
        self.scheduler.run_task(task_id)
        
        # Verify
        task_func.assert_called_once_with(1, 2, key='value')
        self.assertIsNotNone(self.scheduler.tasks[task_id]['last_run'])
        self.assertIsNotNone(self.scheduler.tasks[task_id]['next_run'])

    def test_calculate_next_run_time(self):
        """Test calculation of next run time."""
        # Test with specific time
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        tomorrow_at_8 = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 8, 0)
        
        next_run = self.scheduler._calculate_next_run_time(
            interval_days=1,
            specific_time='08:00',
            last_run=now
        )
        
        # Verify next run is tomorrow at 8:00
        self.assertEqual(next_run.hour, 8)
        self.assertEqual(next_run.minute, 0)
        
        # Test without specific time (interval only)
        next_run = self.scheduler._calculate_next_run_time(
            interval_days=2,
            specific_time=None,
            last_run=now
        )
        
        # Verify next run is 2 days from now
        expected_next_run = now + timedelta(days=2)
        self.assertEqual(next_run.date(), expected_next_run.date())

    @patch('scheduler.task_scheduler.time.sleep')
    def test_run_pending_tasks(self, mock_sleep):
        """Test running pending tasks."""
        # Create mock task functions
        task_func1 = MagicMock()
        task_func1.__name__ = 'task1'
        task_func2 = MagicMock()
        task_func2.__name__ = 'task2'
        
        # Add tasks
        # Task 1: Due to run (next_run in the past)
        task_id1 = self.scheduler.add_task(
            name='Task 1',
            func=task_func1,
            interval_days=1
        )
        self.scheduler.tasks[task_id1]['next_run'] = datetime.now() - timedelta(minutes=5)
        
        # Task 2: Not due yet (next_run in the future)
        task_id2 = self.scheduler.add_task(
            name='Task 2',
            func=task_func2,
            interval_days=1
        )
        self.scheduler.tasks[task_id2]['next_run'] = datetime.now() + timedelta(hours=1)
        
        # Run pending tasks once
        self.scheduler.run_pending_tasks(run_once=True)
        
        # Verify
        task_func1.assert_called_once()  # Task 1 should have run
        task_func2.assert_not_called()   # Task 2 should not have run

    def test_is_task_due(self):
        """Test checking if a task is due to run."""
        # Create a task
        task_func = MagicMock()
        task_func.__name__ = 'test_task'
        task_id = self.scheduler.add_task(
            name='Test Task',
            func=task_func,
            interval_days=1
        )
        
        # Set next_run to the past
        self.scheduler.tasks[task_id]['next_run'] = datetime.now() - timedelta(minutes=5)
        self.assertTrue(self.scheduler._is_task_due(self.scheduler.tasks[task_id]))
        
        # Set next_run to the future
        self.scheduler.tasks[task_id]['next_run'] = datetime.now() + timedelta(hours=1)
        self.assertFalse(self.scheduler._is_task_due(self.scheduler.tasks[task_id]))


if __name__ == '__main__':
    unittest.main()