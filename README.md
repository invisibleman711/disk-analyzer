# macOS 磁盘空间整理工具

分析存储空间、管理缓存、优化磁盘的本地 Web 工具。

## 功能

| 模块 | 说明 |
|------|------|
| 磁盘概览 | 查看各卷宗使用率，附中文说明解释每个卷宗的用途 |
| 文件浏览 | 按大小排序浏览任意目录，文件按类型分类（文档/图片/视频/代码等） |
| 应用程序 | 点击应用可展开查看内部文件组成（可执行程序/框架/资源/缓存），缓存可选清理，程序文件不可操作 |
| 缓存管理 | 扫描浏览器、开发工具、通讯软件等缓存，每项有详细说明和清理建议，支持全选和一键清理 |
| 优化建议 | 综合分析后给出分级建议，明确标注哪些可清理、哪些不要动，并说明理由 |

## 安装

需要 Python 3 环境。

```bash
git clone https://github.com/invisibleman711/disk-analyzer.git
cd disk-analyzer
pip3 install -r requirements.txt
```

## 使用

```bash
bash start.sh
```

启动后浏览器会自动打开 `http://127.0.0.1:8765`。

按 `Ctrl+C` 关闭。

如果端口被占用：

```bash
lsof -ti:8765 | xargs kill; bash start.sh
```

## 技术栈

- 后端：Python + Flask
- 前端：HTML / CSS / JavaScript（无框架）
- 系统信息：psutil

## 注意事项

- 仅支持 macOS
- 清理操作会弹出确认对话框，不会误删
- 系统保护路径（/System、/usr 等）不允许删除
- 应用程序内的程序文件没有删除按钮，只有缓存文件可选清理
