#!/bin/bash
set -e

# 确保运行时目录存在（config.py 导入时也会创建，这里只是兜底）
mkdir -p /app/data/originals \
         /app/data/watermarked \
         /app/data/evidence_packages \
         /app/data/reports \
         /app/static/uploads

echo "[entrypoint] 启动 nginx..."
nginx

echo "[entrypoint] 启动 Flask..."
cd /app
exec python3 run.py
