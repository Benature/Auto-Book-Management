# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

### Testing
- **Run all tests**: `python run_tests.py` or `pytest tests/`
- **Run unit tests only**: `python run_tests.py unit` or `pytest tests/unit/`
- **Run integration tests only**: `python run_tests.py integration` or `pytest tests/integration/`
- **Run with coverage**: `pytest --cov=. tests/`

### Code Quality
- **Format code**: `black .` (auto-format all Python files)
- **Sort imports**: `isort .` (organize import statements)
- **Lint code**: `flake8 .` (check code style and potential issues)
- **Type checking**: `mypy .` (static type analysis)

### Application
- **Run once**: `python main.py --once` (execute sync once and exit)
- **Run as daemon**: `python main.py --daemon` (run continuously with scheduler)
- **Setup project**: `python setup.py` (install dependencies and initialize database)
- **Clean temporary files**: `python main.py --cleanup`

### Database
- **Initialize database**: `python -c "from db.database import Database; db = Database('sqlite:///data/douban_books.db'); db.init_db()"`

## High-Level Architecture

This is a book synchronization automation tool that syncs books from Douban wishlist to Calibre library via Z-Library downloads.

### Core Workflow
1. **Douban Scraping**: Scrapes user's "想读" (wish to read) list from Douban using cookie authentication
2. **Database Storage**: Stores book metadata in SQLite database with status tracking
3. **Calibre Check**: Queries Calibre content server to avoid duplicate downloads
4. **Z-Library Download**: Searches and downloads books from Z-Library with format priority (epub > mobi > pdf)
5. **Calibre Upload**: Uploads downloaded books to Calibre library
6. **Notifications**: Sends status updates via Lark (Feishu) webhook
7. **Scheduling**: Runs automatically on configured schedule (daily/weekly/interval)

### Key Components

**Main Application** (`main.py`):
- Entry point and orchestration
- Command-line interface with `--once`, `--daemon`, `--cleanup` options
- Handles initialization of all services and database

**Data Models** (`db/models.py`):
- `DoubanBook`: Core book entity with status workflow
- `BookStatus` enum: Tracks book processing states (NEW → WITH_DETAIL → SEARCHING → DOWNLOADED → UPLOADED)
- `DownloadRecord`: Records of successful downloads
- `SyncTask`: Tracks synchronization job runs

**Services** (`services/`):
- `DoubanScraper`: Web scraper for Douban wishlist with cookie auth and rate limiting
- `ZLibraryService`: Z-Library API client with proxy support and format preferences
- `CalibreService`: Calibre content server integration for book queries and uploads
- `LarkService`: Feishu notification service with webhook support

**Configuration** (`config/config_manager.py`):
- YAML-based configuration management
- Validates required fields and provides typed access methods
- Supports database, service credentials, scheduling, and system settings

**Task Scheduling** (`scheduler/task_scheduler.py`):
- Background job scheduler supporting daily/weekly/interval patterns
- Thread-safe execution with error handling and logging

### Book Status Workflow
Books progress through these states:
- `NEW`: Newly discovered from Douban
- `WITH_DETAIL`: Detailed metadata retrieved
- `MATCHED`: Already exists in Calibre (terminal state)
- `SEARCHING`: Querying Z-Library
- `SEARCH_NOT_FOUND`: Not found on Z-Library
- `DOWNLOADING`: Downloading from Z-Library
- `DOWNLOADED`: Successfully downloaded
- `UPLOADING`: Uploading to Calibre
- `UPLOADED`: Successfully added to Calibre (terminal state)

### Configuration Structure
The `config.yaml` requires:
- `douban`: Cookie and user credentials for scraping
- `database`: SQLite path or PostgreSQL connection
- `calibre`: Content server URL and authentication
- `zlibrary`: Credentials and download preferences
- `schedule`: Timing configuration (daily/weekly/interval)
- `lark`: Optional webhook notifications

### Testing Structure
- `tests/unit/`: Component-level tests with mocking
- `tests/integration/`: End-to-end workflow tests
- Fixtures in `tests/unit/fixtures/` for HTML parsing tests
- Real network tests marked with `@pytest.mark.real_network`

### Key Dependencies
- `requests` + `beautifulsoup4`: Web scraping
- `sqlalchemy`: Database ORM with SQLite/PostgreSQL support
- `schedule`: Task scheduling
- `zlibrary`: Z-Library API client
- `pyyaml`: Configuration management
- `loguru`: Structured logging
- `pytest`: Testing framework with coverage and mocking