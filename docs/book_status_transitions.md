# 书籍状态转移过程

以下是书籍状态的转移过程，基于 `BookStatus` 枚举定义：

1. **NEW**
   - 初始状态，表示豆瓣中新发现的书籍。
   - 下一步：获取详细信息。

2. **WITH_DETAIL**
   - 已获取详细信息。
   - 下一步：尝试在 Calibre 中匹配。

3. **MATCHED**
   - 已在 Calibre 中匹配到，结束节点。

4. **SEARCHING**
   - 正在从 Z-Library 搜索。
   - 下一步：找到资源或未找到资源。

5. **SEARCH_NOT_FOUND**
   - 未在 Z-Library 找到。
   - 下一步：结束或重新尝试搜索。

6. **DOWNLOADING**
   - 正在从 Z-Library 下载。
   - 下一步：下载完成或下载失败。

7. **DOWNLOADED**
   - 已从 Z-Library 下载。
   - 下一步：上传到 Calibre。

8. **UPLOADING**
   - 正在上传到 Calibre。
   - 下一步：上传完成或上传失败。

9. **UPLOADED**
   - 已上传到 Calibre，结束节点。

此文档旨在记录书籍状态的转移过程，便于后续参考和长记忆。