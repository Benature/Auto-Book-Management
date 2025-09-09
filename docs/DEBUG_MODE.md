# Debug模式使用说明

## 功能描述

Debug模式是为了方便开发和调试而添加的特殊运行模式，它会限制系统的并发性以便于问题排查。

## 使用方法

```bash
# 启用debug模式运行一次
python main.py --debug -o

# 启用debug模式运行守护进程
python main.py --debug --daemon

# 查看所有选项
python main.py --help
```

## Debug模式的限制

### 1. 单线程Pipeline
- **普通模式**: 4个Pipeline workers
- **Debug模式**: 1个Pipeline worker

### 2. 单任务调度
- **普通模式**: 最多10个并发任务
- **Debug模式**: 最多1个并发任务

### 3. 处理书籍数量限制
- **普通模式**: 处理所有待处理书籍
- **Debug模式**: 最多处理3本书籍

## 日志输出示例

启用debug模式时，您会看到以下日志：

```
调试模式已启用：使用单线程pipeline
调试模式：限制并发任务数为 1
调试模式：限制处理书籍数量为 3 本
```

## 适用场景

1. **功能测试**: 快速验证新功能是否正常工作
2. **问题调试**: 避免并发干扰，专注于单个任务的问题排查
3. **开发阶段**: 在开发新功能时进行快速迭代测试
4. **错误复现**: 简化环境以便于重现和分析问题

## 技术实现

Debug模式通过以下方式实现限制：

1. **Pipeline Manager**: 将max_workers从4减少到1
2. **Task Scheduler**: 将max_concurrent_tasks从10减少到1  
3. **Book Processing**: 在run_once()方法中限制处理的书籍数量

这确保了系统在debug模式下真正是单线程、单任务运行的。