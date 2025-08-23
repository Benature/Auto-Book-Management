#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
运行所有测试的脚本

使用方法：
    python run_tests.py          # 运行所有测试
    python run_tests.py unit     # 只运行单元测试
    python run_tests.py integration  # 只运行集成测试
"""

import unittest
import sys
import os


def run_all_tests():
    """运行所有测试"""
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover('tests', pattern='test_*.py')
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    return result.wasSuccessful()


def run_unit_tests():
    """只运行单元测试"""
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover('tests/unit', pattern='test_*.py')
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    return result.wasSuccessful()


def run_integration_tests():
    """只运行集成测试"""
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover('tests/integration', pattern='test_*.py')
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)
    return result.wasSuccessful()


if __name__ == '__main__':
    # 确保当前工作目录是项目根目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    
    # 添加项目根目录到 Python 路径
    sys.path.insert(0, project_root)
    
    # 根据命令行参数决定运行哪些测试
    if len(sys.argv) > 1:
        test_type = sys.argv[1].lower()
        if test_type == 'unit':
            success = run_unit_tests()
        elif test_type == 'integration':
            success = run_integration_tests()
        else:
            print(f"未知的测试类型: {test_type}")
            print("可用选项: unit, integration")
            sys.exit(1)
    else:
        success = run_all_tests()
    
    # 根据测试结果设置退出码
    sys.exit(0 if success else 1)