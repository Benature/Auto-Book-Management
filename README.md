# 豆瓣Z-Library同步工具

一个基于Pipeline架构的自动化书籍同步工具，可以将豆瓣想读书单中的书籍自动下载并上传到Calibre书库。

## 功能特性

- 🚀 **Pipeline架构**：分阶段处理，支持断点续传和状态恢复
- 📚 **智能匹配**：基于书名、作者、ISBN等多维度匹配算法
- 🔄 **自动重试**：智能错误处理和指数退避重试机制
- 📊 **状态跟踪**：19种精细化状态，完整处理链路可视化
- 🔔 **实时通知**：集成飞书通知，处理进度一目了然
- 🛠️ **易于维护**：结构化日志，完善的错误处理和监控

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd auto-book-management

# 安装依赖 (使用uv)
uv pip install -r requirements.txt

# 或使用pip
pip install -r requirements.txt
```

#### 安装Calibre

项目需要使用Calibre的命令行工具`calibredb`进行书库管理：

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install calibre
```

**macOS:**
```bash
# 使用Homebrew
brew install --cask calibre

# 或从官网下载安装包
# https://calibre-ebook.com/download
```

**Windows:**
从官网下载安装包：https://calibre-ebook.com/download

安装完成后，确保`calibredb`命令可用：
```bash
calibredb --version
```

#### 启动Calibre Content Server

```bash
# 启动内容服务器 (默认端口8080)
calibre-server /path/to/your/calibre/library

# 或指定端口和认证
calibre-server --port=8080 --username=admin --password=password /path/to/library
```

### 2. 配置设置

复制配置文件模板并填入相关信息：

```bash
cp config.example.yaml config.yaml
```

编辑`config.yaml`，填入以下必要配置：
- **豆瓣Cookie**：登录豆瓣后从浏览器获取
- **Calibre服务器**：Content Server的URL和认证信息
- **Z-Library账号**：用于下载书籍
- **飞书Webhook**（可选）：用于状态通知

### 3. 初始化项目

```bash
python scripts/setup.py
```

### 4. 运行同步

```bash
# 执行一次同步（推荐）
python main.py --once

# 守护进程模式
python main.py --daemon

# 查看帮助
python main.py --help
```

## 核心架构

### Pipeline处理阶段
1. **数据收集**：从豆瓣获取书籍详细信息
2. **书籍搜索**：在Z-Library中搜索匹配的书籍
3. **文件下载**：下载书籍文件到本地
4. **上传同步**：上传到Calibre书库
5. **状态更新**：更新处理状态和通知

### 状态管理系统
支持19种精细化状态，完整跟踪书籍处理生命周期：

**数据收集阶段**：
- `NEW` → `DETAIL_FETCHING` → `DETAIL_COMPLETE`

**搜索阶段**：
- `SEARCH_QUEUED` → `SEARCH_ACTIVE` → `SEARCH_COMPLETE`/`SEARCH_NO_RESULTS`

**下载阶段**：
- `DOWNLOAD_QUEUED` → `DOWNLOAD_ACTIVE` → `DOWNLOAD_COMPLETE`/`DOWNLOAD_FAILED`

**上传阶段**：
- `UPLOAD_QUEUED` → `UPLOAD_ACTIVE` → `UPLOAD_COMPLETE`/`UPLOAD_FAILED`

**终态**：
- `COMPLETED`、`SKIPPED_EXISTS`、`FAILED_PERMANENT`

## 使用指南

### 常用命令

```bash
# 执行一次完整同步
python main.py --once

# 后台守护进程模式
python main.py --daemon

# 清理临时文件
python main.py --cleanup

# 仅处理豆瓣数据收集
python main.py --stage data_collection

# 查看当前状态统计
python main.py --status
```

### 测试和维护

```bash
# 运行所有测试
python tests/run_tests.py
# 或者
pytest tests/

# 运行单元测试
python tests/run_tests.py unit

# 运行集成测试
python tests/run_tests.py integration

# 代码格式化
yapf -r -i .

# 代码检查
flake8 .
```

### 高级功能

#### 批量状态管理
```bash
# 重置指定状态的书籍
python reset_books_to_search_queued.py

# 检查书籍状态分布
python check_book_status.py

# 调试Z-Library搜索
python debug_zlibrary_search.py
```

## 配置说明

### 核心配置项

项目使用YAML格式配置文件，主要配置项包括：

```yaml
# 豆瓣配置
douban:
  cookie: "bid=xxx; dbcl2=xxx..."  # 豆瓣登录Cookie
  wishlist_url: "https://book.douban.com/people/me/wish"
  max_pages: 0                     # 0表示爬取所有页

# Z-Library配置  
zlibrary:
  username: "your_email@example.com"
  password: "your_password"
  format_priority: ["epub", "mobi", "azw3", "pdf"]
  language_priority: ["Chinese", "English"]
  proxy_list: ["socks5://127.0.0.1:9050"]  # 可选代理

# Calibre配置
calibre:
  content_server_url: "http://localhost:8080"
  username: "admin"
  password: "password"
  match_threshold: 0.6             # 匹配阈值 0.0-1.0

# 数据库配置
database:
  type: "sqlite"                   # sqlite 或 postgresql
  path: "data/douban_books.db"     # SQLite文件路径

# 飞书通知配置（可选）
lark:
  webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
  enabled: true
  level: "all"                     # all, success, error

# 调度配置
schedule:
  time: "03:00"                    # 每日执行时间
  run_at_startup: false
  retry_interval: 60               # 失败重试间隔（分钟）
```

详细配置说明请参考 `config.example.yaml`

## 项目结构

```
auto-book-management/
├── main.py                 # 主程序入口
├── config.yaml            # 配置文件  
├── requirements.txt       # Python依赖
│
├── core/                  # 核心组件
│   ├── pipeline.py        # Pipeline管理器
│   ├── state_manager.py   # 状态管理器
│   ├── task_scheduler.py  # 任务调度器
│   └── error_handler.py   # 错误处理器
│
├── stages/                # 处理阶段
│   ├── data_collection_stage.py  # 数据收集
│   ├── search_stage.py           # 搜索阶段
│   ├── download_stage.py         # 下载阶段
│   └── upload_stage.py           # 上传阶段
│
├── services/              # 外部服务集成
│   ├── zlibrary_service.py      # Z-Library服务
│   ├── calibre_service.py       # Calibre服务
│   └── lark_service.py          # 飞书通知服务
│
├── db/                    # 数据库
│   ├── models.py         # 数据模型
│   └── database.py       # 数据库连接
│
├── scrapers/             # 网页爬虫
│   └── douban_scraper.py # 豆瓣爬虫
│
├── tools/                # 开发调试工具
│   ├── check_book_status.py     # 状态检查
│   ├── debug_reset_status.py    # 状态重置调试
│   └── debug_zlibrary_search.py # Z-Library搜索调试
│
├── scripts/              # 管理维护脚本
│   ├── setup.py          # 项目初始化脚本
│   └── reset_books_to_search_queued.py  # 重置书籍状态
│
├── tests/                # 测试代码
│   ├── run_tests.py     # 测试运行器
│   ├── unit/            # 单元测试
│   └── integration/     # 集成测试
│
├── logs/                # 日志文件
├── data/               # 数据存储
└── docs/              # 项目文档
```

## 技术架构特性

### 错误处理与重试
- **分类错误处理**：网络、认证、资源等不同类型错误
- **指数退避重试**：智能重试策略，避免系统过载
- **永久失败标记**：识别无需重试的错误类型

### 并发与性能
- **任务队列管理**：基于优先级的任务调度
- **资源限制**：可配置的并发数和速率限制
- **内存优化**：流式处理大量数据

### 监控与通知
- **状态统计**：实时处理进度和错误率统计
- **日志系统**：结构化日志，支持不同级别
- **通知集成**：飞书机器人实时状态推送

## 故障排除

### 常见问题

#### 1. 豆瓣403错误
当遇到豆瓣访问被拒绝时，系统会：
- 自动保留当前状态，稍后重试数据收集
- 继续处理已获取详情的书籍进行后续步骤
- 建议检查Cookie是否过期，网络是否正常

#### 2. Z-Library连接失败
- 检查账号密码是否正确
- 确认代理设置（如果使用）
- 查看是否触发下载限制

#### 3. Calibre上传失败
- 确认Calibre Content Server正在运行
- 检查认证信息和网络连接
- 确认书库写入权限

#### 4. 任务处理缓慢
- 检查网络连接质量
- 调整并发数和重试间隔
- 查看日志确定瓶颈环节

### 日志分析

系统提供结构化日志，便于问题定位：

```
2024-01-01 12:00:00 [INFO] pipeline.search: 开始搜索Z-Library: 《围城》
2024-01-01 12:00:05 [INFO] state_manager: 状态转换: 书籍ID 123, SEARCH_QUEUED -> SEARCH_COMPLETE  
2024-01-01 12:00:06 [ERROR] zlibrary: 下载失败: 达到每日限制
```

日志文件位置：`logs/` 目录下，按日期分割

### 性能优化建议

1. **数据库优化**
   - 定期清理过期数据
   - 为大表添加适当索引
   
2. **网络优化**  
   - 使用稳定的代理服务
   - 调整请求间隔避免被限制
   
3. **资源管理**
   - 控制并发任务数量
   - 定期清理临时文件

## 开发说明

### 依赖管理
项目使用 `uv` 进行依赖管理，支持快速安装和锁定版本。

### 测试覆盖
- 单元测试覆盖核心业务逻辑
- 集成测试验证完整工作流程  
- 使用真实配置进行测试，避免过度mock

### 代码质量
- 使用 `yapf` 进行代码格式化
- 使用 `flake8` 进行代码检查
- 遵循PEP8编码规范

## 许可证

本项目基于 MIT 许可证开源，详见 [LICENSE](LICENSE) 文件。

## 贡献指南

欢迎提交Issue和Pull Request来改进这个项目！

---

如有问题或建议，请在GitHub上提交Issue。