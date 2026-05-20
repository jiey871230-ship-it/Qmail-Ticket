#!/bin/bash
# 构建微信云函数公共层
# 在 Linux x86_64 环境中运行（如 Docker），确保二进制兼容云函数运行时

set -e

LAYER_DIR="python/lib/python3.6/site-packages"
OUTPUT="pymupdf-pillow-layer.zip"

echo "=== 清理旧文件 ==="
rm -rf python ${OUTPUT}

echo "=== 安装依赖到 ${LAYER_DIR} ==="
mkdir -p ${LAYER_DIR}
pip install \
    --target=${LAYER_DIR} \
    --platform=manylinux2014_x86_64 \
    --only-binary=:all: \
    -r requirements.txt

echo "=== 清理不需要的文件以减小体积 ==="
find ${LAYER_DIR} -name '*.pyc' -delete
find ${LAYER_DIR} -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find ${LAYER_DIR} -name '*.dist-info' -type d -exec rm -rf {} + 2>/dev/null || true
find ${LAYER_DIR} -name 'tests' -type d -exec rm -rf {} + 2>/dev/null || true

echo "=== 打包为 ${OUTPUT} ==="
zip -r ${OUTPUT} python/

echo "=== 完成 ==="
echo "文件: ${OUTPUT}"
ls -lh ${OUTPUT}
echo ""
echo "下一步: 在微信云开发控制台上传此 zip 作为公共层"
