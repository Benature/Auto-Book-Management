# 项目说明书：豆瓣书单同步与 Calibre 集成自动化

## 项目目标

本项目旨在实现一个自动化系统，用于每日同步豆瓣用户书单中的“想读”书籍，并与本地 Calibre 书库进行对比与更新。主要流程包括：

1. **数据采集**：定时爬取豆瓣书单“想读”条目（通过提供用户 Cookie 登录）。
2. **书库匹配**：对比本地 Calibre Content Server 中现有书籍，判断是否已收录。
3. **缺失补全**：对于未收录的书籍，从 Z-Library 下载，并自动上传至 Calibre。
4. **消息通知**：通过飞书机器人推送执行日志，方便用户追踪。

---

## 系统架构

```mermaid
flowchart TD
    A[定时任务 - 每日触发] --> B[爬取豆瓣书单 (Cookie 登录)]
    B --> C[存入本地数据库]
    C --> D[查询 Calibre Content Server 书库]
    D -->|存在| E[记录匹配成功]
    D -->|不存在| F[调用 Z-Library API 下载书籍]
    F --> G[按用户优先级选择格式 (epub > mobi > pdf)]
    G --> H[上传书籍到 Calibre Content Server]
    E & H --> I[飞书机器人发送日志]
```

---

## 功能模块说明

### 1. 数据采集模块

* **输入**：豆瓣 Cookie（用户提供）
* **操作**：调用爬虫定时任务（每天固定时间运行），爬取用户“想读”书单。
* **输出**：将结果写入本地数据库（推荐 SQLite 或 PostgreSQL）。

### 2. 数据库维护

* 结构建议：

  ```sql
  CREATE TABLE douban_books (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT,
      author TEXT,
      douban_url TEXT,
      status TEXT,        -- 状态: new/matched/downloaded/uploaded
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
* 用于存储豆瓣书籍信息，并跟踪匹配/下载/上传状态。

### 3. Calibre 书库查询模块

* **接口**：通过 Calibre Content Server 提供的 API 查询。
* **匹配规则**：书名 + 作者，支持模糊匹配。
* **结果**：

  * 若存在：更新数据库状态为 `matched`。
  * 若不存在：进入下载流程。

### 4. Z-Library 下载模块

* **接口**：通过 [zlibrary pypi 包](https://pypi.org/project/zlibrary/)。
* **账号**：用户提供 zlibrary 用户名和密码。
* **功能**：

  * 搜索目标书籍（书名 + 作者）。
  * 按匹配度排序，选取最高匹配结果。
  * 按用户设定的优先级（如 epub > mobi > pdf）选择下载格式。
* **输出**：保存书籍文件到临时目录。

### 5. Calibre 上传模块

* **接口**：Calibre Content Server 提供的书籍上传 API。
* **操作**：将下载完成的书籍推送至 Calibre 书库。
* **状态更新**：数据库更新为 `uploaded`。

### 6. 飞书通知模块

* **依赖**：`larkpy` (pypi 包)。
* **功能**：

  * 发送每日任务执行结果日志。
  * 日志内容包括：新增书籍数、已存在书籍数、下载成功/失败情况、上传结果。

---

## 配置文件（config.yaml 示例）

```yaml
douban:
  cookie: "your_douban_cookie"

database:
  type: "sqlite"
  path: "./douban_books.db"

calibre:
  content_server_url: "http://localhost:8080"
  username: "your_calibre_user"
  password: "your_calibre_password"

zlibrary:
  username: "your_zlibrary_user"
  password: "your_zlibrary_password"
  format_priority: ["epub", "mobi", "pdf"]

schedule:
  time: "02:00"   # 每日执行时间

lark:
  webhook_url: "https://open.feishu.cn/..."

```

---

## 日志通知示例

飞书机器人推送格式：

```
📚 豆瓣书单同步任务完成

- 新增书籍：3 本
- 已存在书籍：5 本
- 成功下载并上传：2 本
- 下载失败：1 本

详细日志请见本地文件 logs/task_2025-08-23.log
```

---

## 技术栈与依赖

* **爬虫**：requests + BeautifulSoup / playwright
* **数据库**：SQLite / PostgreSQL
* **Calibre API**：Calibre Content Server
* **下载**：zlibrary (pypi 包)
* **消息通知**：larkpy
* **调度**：APScheduler / cron

---

## 开发任务拆解

1. **项目初始化**

   * 配置文件解析
   * 数据库 schema 定义
2. **豆瓣爬虫**

   * 模拟登录（cookie）
   * 抓取“想读”书单
   * 入库
3. **Calibre 查询**

   * API 对接
   * 模糊匹配逻辑
4. **Z-Library 下载**

   * 登录
   * 搜索 & 按优先级下载
5. **书籍上传**

   * Calibre API 上传
   * 状态更新
6. **飞书机器人**

   * 日志收集与推送
7. **调度系统**

   * 每日定时执行
   * 错误捕获与重试机制

---

我这里写的偏 **全局设计** + **开发任务拆解**，非常适合交给 Cursor 生成代码。
要不要我帮你再写一个 **最小可运行的项目结构（文件夹树 + 空文件）**，让 Cursor 能直接补全代码？
