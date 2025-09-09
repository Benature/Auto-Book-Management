# 开发和调试工具

本目录包含用于开发和调试的工具脚本。

## 工具说明

- `check_book_status.py` - 检查数据库中书籍的状态分布
- `check_zlibrary_ids.py` - 检查Z-Library书籍的ID字段
- `debug_reset_status.py` - 调试状态重置脚本
- `debug_zlibrary_search.py` - 调试Z-Library搜索结果结构

## 使用方法

从项目根目录运行：

```bash
# 检查书籍状态分布
python tools/check_book_status.py

# 检查Z-Library IDs
python tools/check_zlibrary_ids.py

# 调试状态重置
python tools/debug_reset_status.py

# 调试Z-Library搜索
python tools/debug_zlibrary_search.py
```