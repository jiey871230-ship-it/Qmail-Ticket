#!/bin/bash
# 构建微信云函数公共层
# 用法: 在项目根目录运行 ./cloudfunctions/pymupdf-pillow-layer/build.sh
# 或者: cd cloudfunctions/pymupdf-pillow-layer && bash build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LAYER_DIR="python/lib/python3.9/site-packages"
OUTPUT="pymupdf-pillow-layer.zip"

echo "=== 清理旧文件 ==="
rm -rf python ${OUTPUT}

echo "=== 安装依赖到 ${LAYER_DIR} ==="
mkdir -p ${LAYER_DIR}
pip install \
    --target=${LAYER_DIR} \
    --platform=manylinux2014_x86_64 \
    --only-binary=:all: \
    --python-version=3.9 \
    -r requirements.txt

echo "=== 清理不需要的文件以减小体积 ==="
find ${LAYER_DIR} -name '*.pyc' -delete
find ${LAYER_DIR} -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find ${LAYER_DIR} -name '*.dist-info' -type d -exec rm -rf {} + 2>/dev/null || true
find ${LAYER_DIR} -name 'tests' -type -exec rm -rf {} + 2>/dev/null || true

echo "=== 打包为 ${OUTPUT} ==="
zip -r ${OUTPUT} python/

echo "=== 完成 ==="
ls -lh ${OUTPUT}
echo ""
echo "下一步: 在微信云开发控制台 → 云函数 → 层管理 中上传 ${OUTPUT}"
