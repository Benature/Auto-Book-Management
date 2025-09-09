# 管理和维护脚本

本目录包含用于系统管理和维护的脚本。

## 脚本说明

- `setup.py` - 项目初始化脚本，用于安装依赖、创建配置文件和初始化数据库
- `reset_books_to_search_queued.py` - 重置书籍状态到搜索队列，用于测试搜索功能

## 使用方法

从项目根目录运行：

```bash
# 初始化项目（首次使用时）
python scripts/setup.py

# 重置书籍状态到搜索队列
python scripts/reset_books_to_search_queued.py
```

### setup.py 详细选项

```bash
# 跳过安装依赖
python scripts/setup.py --skip-deps

# 跳过创建配置文件
python scripts/setup.py --skip-config

# 跳过创建目录
python scripts/setup.py --skip-dirs

# 跳过初始化数据库
python scripts/setup.py --skip-db
```

**注意**: 这些脚本会修改数据库状态，请在使用前备份数据。