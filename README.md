# 豆瓣Z-Library同步工具 

## 架构重构说明

V2版本采用了全新的Pipeline架构，将原来的混合式处理流程重构为分阶段的处理管道，实现了更好的错误恢复、数据持久化和状态管理。

## 架构特性

### 1. 分阶段Pipeline架构
- **数据收集阶段**：从豆瓣获取书籍详细信息
- **搜索阶段**：在Z-Library中搜索书籍并持久化结果  
- **下载阶段**：从Z-Library下载书籍文件
- **上传阶段**：将文件上传到Calibre
- **清理阶段**：清理临时文件

### 2. 强化的状态管理
- 新增细粒度状态：`DETAIL_FETCHING`、`SEARCH_ACTIVE`、`DOWNLOAD_ACTIVE`等
- 统一的状态转换验证和历史记录
- 支持断点续传和状态恢复

### 3. 任务调度系统
- 基于优先级的任务队列
- 支持指数退避的重试策略
- 并发控制和资源管理

### 4. 错误处理机制
- 分类错误处理：网络错误、认证错误、资源未找到等
- 智能重试策略
- 错误恢复和降级处理

### 5. 监控告警系统
- 实时指标收集：处理速度、错误率、队列积压等
- 可配置的告警规则
- 集成飞书通知

## 使用方式

### 1. 数据库迁移

首先执行数据库迁移（会自动备份现有数据）：

```bash
python db/migration_v2.py --config config.yaml
```

### 2. 运行新版本

#### 执行一次同步（推荐）
```bash
python main_v2.py --once --config config.yaml
```

#### 守护进程模式
```bash
python main_v2.py --daemon --config config.yaml
```

#### 查看系统状态
```bash
python main_v2.py --status --config config.yaml
```

### 3. 监控和维护

#### 查看处理进度
V2版本提供了详细的状态统计，可以实时查看各阶段的处理进度。

#### 错误恢复
系统会自动处理各种错误情况：
- 网络超时：自动重试，指数退避
- 认证失败：发送告警，需要人工干预
- 资源未找到：标记跳过，不重试
- 系统错误：记录详细日志，支持重试

#### 断点续传
程序重启后会自动：
- 重置卡住的任务状态
- 继续处理未完成的书籍
- 从正确的阶段开始处理

## 配置说明

V2版本兼容原有配置文件，新增了以下可选配置：

```yaml
# Pipeline配置
pipeline:
  max_concurrent_tasks: 10        # 最大并发任务数
  retry_max_attempts: 3          # 最大重试次数
  retry_delay_base: 30           # 重试基础延迟（秒）

# 监控配置
monitoring:
  enabled: true                   # 是否启用监控
  metrics_retention_hours: 168   # 指标保留时间（7天）
  alert_cooldown_minutes: 30     # 告警冷却时间

# 告警规则
alerts:
  high_error_rate:
    threshold: 50                 # 错误率阈值（%）
    severity: "critical"
  slow_processing:
    threshold: 1                  # 处理速度阈值（本/小时）
    severity: "warning"
```

## 架构对比

### V1 (原版本)
- 单一流程处理
- 状态管理分散
- 错误处理简单
- 难以恢复和调试

### V2 (新版本)
- 分阶段Pipeline处理
- 统一状态管理
- 智能错误处理和重试
- 支持断点续传
- 实时监控告警
- 更好的可维护性

## 数据库模型变化

### 新增表
- `processing_tasks`: 处理任务管理
- `system_config`: 系统配置
- `worker_status`: 工作进程状态

### 状态枚举扩展
原有的8个状态扩展为19个细粒度状态，支持更精确的流程控制。

### 新增字段
- `DoubanBook`: 新增 `search_title`、`search_author` 搜索字段
- `ZLibraryBook`: 增强字段结构，支持更完整的元数据存储

## 性能优化

### 1. 并发处理
- 多线程并行处理不同阶段
- 可配置的并发数限制
- 智能资源调度

### 2. 数据库优化
- 批量操作减少数据库压力
- 索引优化提升查询性能
- 连接池管理

### 3. 网络优化
- 智能延迟策略
- 错误自适应退避
- 代理轮换支持

## 故障排除

### 常见问题

1. **迁移失败**
   ```bash
   # 回滚到备份
   python db/migration_v2.py --rollback --config config.yaml
   ```

2. **任务卡住**
   - 系统会自动检测并重置超时任务
   - 可通过状态查询确认处理进度

3. **错误率过高**
   - 检查网络连接和代理配置
   - 查看错误日志确定具体原因
   - 系统会自动发送告警通知

### 日志分析
V2版本提供了结构化的日志输出，便于问题定位：
```
2024-01-01 12:00:00 [INFO] pipeline.search: 搜索Z-Library: 《书名》
2024-01-01 12:00:05 [INFO] state_manager: 状态转换成功: 书籍ID 123, SEARCH_QUEUED -> SEARCH_COMPLETE
```

## 兼容性说明

- 完全兼容V1的配置文件
- 数据库结构向后兼容
- 保留原有的API接口
- 渐进式迁移，可随时回滚

## 未来计划

- Web管理界面
- 更多数据源支持
- 集群部署支持
- 更丰富的监控指标

---

如有问题，请查看日志文件或提交Issue。