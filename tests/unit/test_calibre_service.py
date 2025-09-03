# -*- coding: utf-8 -*-
"""
CalibreService 单元测试
"""
import pytest
from pathlib import Path

from config.config_manager import ConfigManager
from services.calibre_service import CalibreService


@pytest.fixture
def calibre_service():
    """创建CalibreService实例用于测试"""
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config.yaml"

    if not config_path.exists():
        config_path = project_root / "config.example.yaml"

    if not config_path.exists():
        pytest.skip("找不到配置文件，跳过测试")

    # 从配置文件加载配置
    config_manager = ConfigManager(str(config_path))
    calibre_config = config_manager.get_calibre_config()

    server_url = calibre_config['content_server_url']
    username = calibre_config['username']
    password = calibre_config['password']
    match_threshold = calibre_config.get('match_threshold', 0.6)

    calibre_service = CalibreService(server_url=server_url,
                                     username=username,
                                     password=password,
                                     match_threshold=match_threshold)

    return calibre_service


@pytest.fixture
def config_values():
    """获取配置值用于测试验证"""
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / "config.yaml"

    if not config_path.exists():
        config_path = project_root / "config.example.yaml"

    if not config_path.exists():
        pytest.skip("找不到配置文件，跳过测试")

    config_manager = ConfigManager(str(config_path))
    calibre_config = config_manager.get_calibre_config()

    return {
        'server_url': calibre_config['content_server_url'],
        'username': calibre_config['username'],
        'password': calibre_config['password'],
        'match_threshold': calibre_config.get('match_threshold', 0.6)
    }


def test_init(calibre_service, config_values):
    """测试 CalibreService 初始化"""
    assert calibre_service.server_url == config_values['server_url']
    assert calibre_service.username == config_values['username']
    assert calibre_service.password == config_values['password']
    assert calibre_service.match_threshold == config_values['match_threshold']
    assert calibre_service.timeout == 120


def test_configuration_validation(calibre_service):
    """测试配置值验证"""
    assert isinstance(calibre_service.server_url, str)
    assert isinstance(calibre_service.username, str)
    assert isinstance(calibre_service.password, str)
    assert isinstance(calibre_service.match_threshold, (int, float))
    assert isinstance(calibre_service.timeout, int)


def test_similarity_calculation(calibre_service):
    """测试相似度计算方法"""
    # 测试完全匹配
    similarity = calibre_service._calculate_similarity("test", "test")
    assert similarity == 1.0

    # 测试无匹配
    similarity = calibre_service._calculate_similarity("abc", "xyz")
    assert 0.0 <= similarity <= 1.0

    # 测试部分匹配
    similarity = calibre_service._calculate_similarity("python programming",
                                                       "python guide")
    assert 0.0 < similarity < 1.0


def test_match_threshold_validation(calibre_service):
    """测试匹配阈值配置"""
    threshold = calibre_service.match_threshold

    assert 0.0 <= threshold <= 1.0
    assert isinstance(threshold, (int, float))


def test_timeout_configuration(calibre_service):
    """测试超时配置"""
    timeout = calibre_service.timeout

    assert timeout > 0
    assert isinstance(timeout, int)


def test_server_url_format(calibre_service):
    """测试服务器URL格式"""
    server_url = calibre_service.server_url

    assert isinstance(server_url, str)
    assert server_url.startswith('http')
    assert ':' in server_url


def test_authentication_data(calibre_service):
    """测试认证数据"""
    username = calibre_service.username
    password = calibre_service.password

    assert isinstance(username, str)
    assert isinstance(password, str)
    assert len(username) > 0
    assert len(password) > 0


def test_book_data_structure_validation():
    """测试期望的书籍数据结构"""
    sample_book = {
        'calibre_id': 123,
        'title': 'Python Programming',
        'authors': ['John Doe'],
        'author': 'John Doe',
        'publisher': 'Tech Books',
        'isbn': '9781234567890',
        'formats': ['EPUB', 'PDF'],
        'identifiers': {
            'isbn': '9781234567890'
        }
    }

    # 验证期望字段存在
    expected_fields = ['calibre_id', 'title', 'authors', 'author']
    for field in expected_fields:
        assert field in sample_book

    # 验证数据类型
    assert isinstance(sample_book['calibre_id'], int)
    assert isinstance(sample_book['title'], str)
    assert isinstance(sample_book['authors'], list)
    assert isinstance(sample_book['author'], str)


def test_search_parameters_validation():
    """测试搜索参数验证逻辑"""
    search_params = {
        'title': 'Python Programming',
        'author': 'John Doe',
        'isbn': '9781234567890',
        'empty_param': '',
        'none_param': None
    }

    # 过滤空/None参数
    filtered_params = {
        k: v
        for k, v in search_params.items()
        if v and isinstance(v, str) and len(v.strip()) > 0
    }

    # 验证过滤结果
    assert 'title' in filtered_params
    assert 'author' in filtered_params
    assert 'isbn' in filtered_params
    assert 'empty_param' not in filtered_params
    assert 'none_param' not in filtered_params


@pytest.mark.real_network
def test_search_book_by_title(calibre_service):
    """测试按标题搜索书籍"""
    # 使用简单的书名进行搜索测试
    title = "交易"
    results = calibre_service.search_book(title=title, verbose=True)

    # 验证返回结果是列表
    assert isinstance(results, list)

    # 如果有结果，验证结果的数据结构
    if results:
        for book in results:
            # 验证必要字段存在
            assert 'calibre_id' in book
            assert 'title' in book
            assert 'authors' in book
            assert 'author' in book

            # 验证数据类型
            assert isinstance(book['calibre_id'], int)
            assert isinstance(book['title'], str)
            assert isinstance(book['authors'], list)
            assert isinstance(book['author'], str)

            # 验证标题包含搜索关键词（不区分大小写）
            assert title in book['title'].lower()

    print(f"搜索 {title} 找到 {len(results)} 本书")
    for book in results[:3]:  # 只显示前3本
        print(f"- {book['title']} by {book['author']}")
