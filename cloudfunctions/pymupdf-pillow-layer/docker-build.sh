#!/bin/bash
# 使用 Docker 构建云函数依赖层（Linux x86_64 环境）
# 用法: bash cloudfunctions/pymupdf-pillow-layer/docker-build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "使用 Docker 构建 pymupdf-pillow 依赖层..."
docker run --rm \
    -v "$SCRIPT_DIR:/build" \
    -w /build \
    python:3.9-slim \
    bash build.sh

echo ""
echo "构建完成! 输出文件: $SCRIPT_DIR/pymupdf-pillow-layer.zip"
echo "请在微信云开发控制台上传此文件作为公共层"
