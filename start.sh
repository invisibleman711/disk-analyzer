#!/bin/bash
# 磁盘空间整理工具 - 启动脚本

cd "$(dirname "$0")"

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "错误: 未找到 python3，请先安装 Python 3"
    exit 1
fi

# 检查并安装依赖
if ! python3 -c "import flask" 2>/dev/null || ! python3 -c "import psutil" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
fi

echo ""
echo "=========================================="
echo "  磁盘空间整理工具"
echo "  启动中..."
echo "=========================================="
echo ""

python3 app.py
