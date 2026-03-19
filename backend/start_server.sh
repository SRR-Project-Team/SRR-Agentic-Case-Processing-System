#!/bin/bash
# Cloud Run 启动脚本
# 读取 PORT 环境变量（Cloud Run 会自动设置），如果没有则使用默认值 8080
set -x  # 打印每一行命令，方便在日志里看到

echo "Environment variables at startup:"
env | sort

PORT=${PORT:-8080}
DEBUG_PORT=${DEBUG_PORT:-}

echo "Starting server on port $PORT"
if [ -n "$DEBUG_PORT" ]; then
    echo "🐛 Debug mode enabled - debugpy will listen on port $DEBUG_PORT"
    echo "   The debugger will be started by Python code in main.py"
fi

exec uvicorn src.api.main:app --host 0.0.0.0 --port $PORT --log-level debug



