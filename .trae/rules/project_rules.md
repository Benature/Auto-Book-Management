1. 使用pypi包：zlibrary, larkpy, pathlib
2. 使用uv进行虚拟环境的管理
3. 使用sqlite3数据库
4. config.yaml已存在，且基于隐私不允许读，参考config.yaml.example结构即可
5. 测试使用pytest
6. 在完成任务或者需要人工介入时运行terminal: `say "<message in English>"`
7. 使用 pathlib 而非 os.path，python 文件通过 `FILE_DIR = Path(__file__).resolve().parent` 获取当前文件所在目录，相对路径通过 `FILE_DIR` 建立关系