#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成豆瓣爬虫测试所需的fixtures文件
"""

import os
from pathlib import Path

# 获取当前文件所在目录
current_dir = Path(__file__).parent
fixtures_dir = current_dir / 'fixtures'

# 创建fixtures目录
fixtures_dir.mkdir(exist_ok=True)

# 创建模拟的书单HTML文件
wishlist_html = '''<!DOCTYPE html>
<html>
<head>
    <title>豆瓣读书 - 想读</title>
</head>
<body>
    <ul class="interest-list">
        <li class="subject-item">
            <div class="pic">
                <a href="https://book.douban.com/subject/26912767/">
                    <img src="https://img2.doubanio.com/view/subject/s/public/s29195878.jpg" alt="深入理解计算机系统">
                </a>
            </div>
            <div class="info">
                <h2 class="title">
                    <a href="https://book.douban.com/subject/26912767/">深入理解计算机系统</a>
                </h2>
                <div class="pub">[美] Randal E. Bryant / David O'Hallaron / 机械工业出版社 / 2016-11</div>
            </div>
        </li>
    </ul>
</body>
</html>'''

with open(fixtures_dir / 'douban_wishlist.html', 'w', encoding='utf-8') as f:
    f.write(wishlist_html)

# 创建模拟的书籍详情HTML文件
book_detail_html = '''<!DOCTYPE html>
<html>
<head>
    <title>深入理解计算机系统 (豆瓣)</title>
</head>
<body>
    <div id="wrapper">
        <h1>深入理解计算机系统</h1>
        <div id="info">
            作者: [美] Randal E. Bryant / David O'Hallaron<br>
            出版社: 机械工业出版社<br>
            出版年: 2016-11<br>
            ISBN: 9787111544937
        </div>
    </div>
</body>
</html>'''

with open(fixtures_dir / 'douban_book_detail.html', 'w', encoding='utf-8') as f:
    f.write(book_detail_html)

print("测试fixtures文件已生成完成")