# Qmail-Ticket 微信小程序版实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Qmail-Ticket Python CLI 工具移植为微信小程序，使用微信云开发（Python 云函数 + 云存储 + 云数据库），支持 QQ邮箱 IMAP 提取 12306/携程票据并导出。

**架构：** 微信小程序前端（3 页面 + 1 组件）通过 `wx.cloud.callFunction` 调用 Python 云函数。`fetchTickets` 函数复用现有 parsers/sources 模块，流式处理邮件并上传文件到云存储。`sendEmail` 函数打包 ZIP 通过 SMTP 发送。PyMuPDF + Pillow 通过公共层（Layer）解决代码包体积限制。

**技术栈：** 微信小程序原生（WXML/WXSS/JS）、微信云开发（Python 3.x 云函数）、PyMuPDF、Pillow、imaplib、smtplib

---

## 文件结构

```
miniprogram/
├── app.js                    # 小程序入口，初始化云开发
├── app.json                  # 全局配置（页面路由、tabBar）
├── app.wxss                  # 全局样式变量
├── pages/
│   ├── index/                # 首页（提取配置）
│   │   ├── index.wxml
│   │   ├── index.wxss
│   │   ├── index.js
│   │   └── index.json
│   ├── tickets/              # 票据列表
│   │   ├── tickets.wxml
│   │   ├── tickets.wxss
│   │   ├── tickets.js
│   │   └── tickets.json
│   └── export/               # 导出页
│       ├── export.wxml
│       ├── export.wxss
│       ├── export.js
│       └── export.json
├── components/
│   └── ticket-card/          # 票据卡片组件
│       ├── ticket-card.wxml
│       ├── ticket-card.wxss
│       ├── ticket-card.js
│       └── ticket-card.json
├── utils/
│   └── cloud.js              # 云函数调用封装
└── images/                   # 图标资源（train.png, plane.png）

cloudfunctions/
├── pymupdf-pillow-layer/
│   ├── requirements.txt
│   └── build.sh
├── fetchTickets/
│   ├── main.py
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── imap.py
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── train_12306.py
│   │   └── ctrip.py
│   └── utils/
│       ├── __init__.py
│       ├── email_utils.py
│       └── pdf_utils.py
└── sendEmail/
    └── main.py
```

---

## 任务 1：项目结构初始化

**文件：**
- 创建：`miniprogram/app.js`、`miniprogram/app.json`、`miniprogram/app.wxss`
- 创建：`miniprogram/utils/cloud.js`
- 创建：`miniprogram/images/`（占位）

- [ ] **步骤 1：创建项目目录结构**

```bash
cd /Users/yangjie/Qmail-Ticket
mkdir -p miniprogram/pages/index
mkdir -p miniprogram/pages/tickets
mkdir -p miniprogram/pages/export
mkdir -p miniprogram/components/ticket-card
mkdir -p miniprogram/utils
mkdir -p miniprogram/images
mkdir -p cloudfunctions/pymupdf-pillow-layer
mkdir -p cloudfunctions/fetchTickets/sources
mkdir -p cloudfunctions/fetchTickets/parsers
mkdir -p cloudfunctions/fetchTickets/utils
mkdir -p cloudfunctions/sendEmail
```

- [ ] **步骤 2：创建 `miniprogram/app.json`**

```json
{
  "pages": [
    "pages/index/index",
    "pages/tickets/tickets",
    "pages/export/export"
  ],
  "window": {
    "navigationBarBackgroundColor": "#1890ff",
    "navigationBarTitleText": "Qmail-Ticket",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#f5f5f5"
  },
  "tabBar": {
    "color": "#999",
    "selectedColor": "#1890ff",
    "list": [
      {
        "pagePath": "pages/index/index",
        "text": "首页",
        "iconPath": "images/home.png",
        "selectedIconPath": "images/home-active.png"
      },
      {
        "pagePath": "pages/tickets/tickets",
        "text": "票据列表",
        "iconPath": "images/ticket.png",
        "selectedIconPath": "images/ticket-active.png"
      },
      {
        "pagePath": "pages/export/export",
        "text": "导出",
        "iconPath": "images/export.png",
        "selectedIconPath": "images/export-active.png"
      }
    ]
  },
  "usingComponents": {}
}
```

- [ ] **步骤 3：创建 `miniprogram/app.js`**

```javascript
App({
  onLaunch() {
    if (!wx.cloud) {
      console.error('请使用 2.2.3 或以上的基础库以使用云能力')
      return
    }
    wx.cloud.init({
      env: 'your-env-id', // 替换为实际云开发环境 ID
      traceUser: true,
    })
  },
  globalData: {}
})
```

- [ ] **步骤 4：创建 `miniprogram/app.wxss`**

```css
page {
  --primary-color: #1890ff;
  --text-color: #333;
  --text-secondary: #666;
  --bg-color: #f5f5f5;
  --card-bg: #fff;
  --border-color: #eee;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 28rpx;
  color: var(--text-color);
  background-color: var(--bg-color);
}

.container {
  padding: 30rpx;
}

.btn-primary {
  background-color: var(--primary-color);
  color: #fff;
  border-radius: 12rpx;
  padding: 24rpx;
  text-align: center;
  font-size: 32rpx;
  border: none;
}

.btn-primary[disabled] {
  opacity: 0.5;
}
```

- [ ] **步骤 5：创建 `miniprogram/utils/cloud.js`**

```javascript
/**
 * 云函数调用封装
 */
const db = wx.cloud.database()

/**
 * 调用 fetchTickets 云函数
 */
function fetchTickets({ email, code, startDate, endDate, taskId }) {
  return wx.cloud.callFunction({
    name: 'fetchTickets',
    data: { email, code, startDate, endDate, taskId },
  })
}

/**
 * 调用 sendEmail 云函数
 */
function sendEmail({ email, code, toAddress, fileIds }) {
  return wx.cloud.callFunction({
    name: 'sendEmail',
    data: { email, code, toAddress, fileIds },
  })
}

/**
 * 创建任务记录（用于进度跟踪）
 */
async function createTask() {
  const res = await db.collection('tasks').add({
    data: {
      status: 'connecting',
      progress: '0/0',
      ticketCount: 0,
      totalAmount: 0,
      fileIds: {},
      createTime: db.serverDate(),
    },
  })
  return res._id
}

/**
 * 轮询任务进度
 */
function watchTask(taskId, callback) {
  const timer = setInterval(async () => {
    try {
      const { data } = await db.collection('tasks').doc(taskId).get()
      callback(data)
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(timer)
      }
    } catch (e) {
      console.error('轮询失败:', e)
    }
  }, 2000)
  return timer
}

/**
 * 获取最新任务的票据列表
 */
async function getTickets(taskId) {
  const { data } = await db.collection('tickets')
    .where({ _taskId: taskId })
    .orderBy('travelDate', 'desc')
    .get()
  return data
}

/**
 * 获取最新任务信息
 */
async function getTask(taskId) {
  const { data } = await db.collection('tasks').doc(taskId).get()
  return data
}

/**
 * 下载云存储文件到临时路径
 */
async function downloadFile(fileID) {
  const res = await wx.cloud.downloadFile({ fileID })
  return res.tempFilePath
}

/**
 * 保存图片到相册
 */
async function saveImageToAlbum(tempFilePath) {
  return new Promise((resolve, reject) => {
    wx.saveImageToPhotosAlbum({
      filePath: tempFilePath,
      success: resolve,
      fail: reject,
    })
  })
}

/**
 * 打开文档预览
 */
async function openDocument(tempFilePath, fileType) {
  return new Promise((resolve, reject) => {
    wx.openDocument({
      filePath: tempFilePath,
      fileType,
      success: resolve,
      fail: reject,
    })
  })
}

module.exports = {
  fetchTickets,
  sendEmail,
  createTask,
  watchTask,
  getTickets,
  getTask,
  downloadFile,
  saveImageToAlbum,
  openDocument,
  db,
}
```

- [ ] **步骤 6：创建占位图标文件**

```bash
# 创建简单的 SVG 转 PNG 占位图标（实际开发时替换为设计稿）
cd /Users/yangjie/Qmail-Ticket/miniprogram/images
for name in home home-active ticket ticket-active export export-active train plane; do
  # 创建 1x1 透明 PNG 占位
  echo -n -e '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82' > ${name}.png
done
```

- [ ] **步骤 7：Commit**

```bash
git add miniprogram/
git commit -m "feat: initialize miniprogram project structure"
```

---

## 任务 2：云函数公共层（Layer）

**文件：**
- 创建：`cloudfunctions/pymupdf-pillow-layer/requirements.txt`
- 创建：`cloudfunctions/pymupdf-pillow-layer/build.sh`

- [ ] **步骤 1：创建 `requirements.txt`**

```
PyMuPDF>=1.23.0
Pillow>=10.0.0
```

- [ ] **步骤 2：创建 `build.sh` 打包脚本**

```bash
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
```

- [ ] **步骤 3：创建 Docker 构建环境（可选）**

创建 `cloudfunctions/pymupdf-pillow-layer/Dockerfile`：

```dockerfile
FROM python:3.6-slim
WORKDIR /build
COPY requirements.txt .
RUN pip install --target=python/lib/python3.6/site-packages \
    --platform=manylinux2014_x86_64 \
    --only-binary=:all: \
    -r requirements.txt
COPY build.sh .
RUN chmod +x build.sh
```

构建命令：
```bash
cd /Users/yangjie/Qmail-Ticket/cloudfunctions/pymupdf-pillow-layer
docker build -t layer-builder .
docker run --rm -v $(pwd):/output layer-builder bash -c "cp -r python /output/ && cp pymupdf-pillow-layer.zip /output/ 2>/dev/null || true"
```

- [ ] **步骤 4：Commit**

```bash
git add cloudfunctions/pymupdf-pillow-layer/
git commit -m "feat: add pymupdf-pillow cloud function layer build config"
```

---

## 任务 3：迁移 Python 解析模块到 fetchTickets

**文件：**
- 创建：`cloudfunctions/fetchTickets/sources/__init__.py`
- 创建：`cloudfunctions/fetchTickets/sources/base.py`
- 创建：`cloudfunctions/fetchTickets/sources/imap.py`
- 创建：`cloudfunctions/fetchTickets/parsers/__init__.py`
- 创建：`cloudfunctions/fetchTickets/parsers/base.py`
- 创建：`cloudfunctions/fetchTickets/parsers/train_12306.py`
- 创建：`cloudfunctions/fetchTickets/parsers/ctrip.py`
- 创建：`cloudfunctions/fetchTickets/utils/__init__.py`
- 创建：`cloudfunctions/fetchTickets/utils/email_utils.py`
- 创建：`cloudfunctions/fetchTickets/utils/pdf_utils.py`

- [ ] **步骤 1：复制 `sources/base.py`（直接复用）**

```bash
cp /Users/yangjie/Qmail-Ticket/qmail_ticket/sources/base.py \
   /Users/yangjie/Qmail-Ticket/cloudfunctions/fetchTickets/sources/base.py
```

内容无需修改，直接复用原文件。

- [ ] **步骤 2：创建 `sources/__init__.py`**

```python
"""邮件源模块"""
from qmail_ticket.sources.base import MailSource
from qmail_ticket.sources.imap import ImapSource

__all__ = ['MailSource', 'ImapSource']
```

- [ ] **步骤 3：迁移 `sources/imap.py`（优化版）**

从原项目复制，修改 import 路径为相对导入，并添加 IMAP 优化：

```python
"""IMAP 通用邮件源（优化版：先扫主题再取全文）"""
import email.header
import imaplib
import re
from datetime import timedelta

from .base import MailSource

SUBJECT_12306 = "网上购票系统"
SUBJECT_CTRIP = "携程"


def _decode_subject(raw_bytes: bytes) -> str:
    """从 IMAP FETCH 返回的原始 header bytes 中解码 Subject。"""
    text = raw_bytes.decode('utf-8', errors='replace')
    m = re.search(r'Subject:\s*(.+?)(?:\r?\n\s*\r?\n|\r?\n$|$)', text, re.DOTALL)
    if not m:
        return ''
    subject_raw = m.group(1).strip()
    if '=?' in subject_raw:
        parts = email.header.decode_header(subject_raw)
        result = []
        for s, cs in parts:
            if isinstance(s, bytes):
                try:
                    result.append(s.decode(cs or 'utf-8', errors='replace'))
                except LookupError:
                    result.append(s.decode('utf-8', errors='replace'))
            else:
                result.append(s)
        return ''.join(result).strip()
    return subject_raw


class ImapSource(MailSource):
    """IMAP 通用邮件源"""

    def __init__(self, email: str, code: str,
                 server: str = "imap.qq.com", port: int = 993):
        self._email = email
        self._code = code
        self._server = server
        self._port = port
        self._conn = None

    def connect(self, **kwargs) -> None:
        self._conn = imaplib.IMAP4_SSL(self._server, self._port)
        self._conn.login(self._email, self._code)

    def search(self, start_date=None, end_date=None) -> list:
        self._conn.select('INBOX')

        # 服务端日期过滤
        criteria = 'ALL'
        if start_date:
            criteria = f'SINCE {start_date.strftime("%d-%b-%Y")}'
        if end_date:
            criteria += f' BEFORE {(end_date + timedelta(days=1)).strftime("%d-%b-%Y")}'

        _, data = self._conn.uid('SEARCH', criteria)
        all_uids = data[0].split() if data[0] else []

        if not all_uids:
            return []

        # 先扫主题头（极小数据量），只对匹配的邮件取全文
        matching_uids = []
        for raw_uid in all_uids:
            _, hdr_data = self._conn.uid('FETCH', raw_uid,
                                         '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
            if not hdr_data or not hdr_data[0]:
                continue

            raw_bytes = None
            for part in hdr_data:
                if isinstance(part, tuple):
                    raw_bytes = part[1]
                    break
            if raw_bytes is None:
                continue

            decoded = _decode_subject(raw_bytes)
            if SUBJECT_12306 in decoded or SUBJECT_CTRIP in decoded:
                matching_uids.append((raw_uid, decoded))

        # 只对匹配的邮件取全文
        from ..models import RawEmail
        results = []
        for raw_uid, decoded in matching_uids:
            _, fetch_data = self._conn.uid('FETCH', raw_uid, '(RFC822)')
            if fetch_data and fetch_data[0]:
                full_bytes = fetch_data[0][1]
                results.append(RawEmail(
                    source='imap', uid=raw_uid,
                    raw_bytes=full_bytes, subject=decoded
                ))

        return results

    def disconnect(self) -> None:
        if self._conn:
            self._conn.logout()
```

- [ ] **步骤 4：创建 `models.py`（数据模型）**

```python
"""数据模型"""
from dataclasses import dataclass


@dataclass
class Ticket:
    """一张票据"""
    travel_date: str       # "2026-04-28"
    carrier: str           # 车次 "G8888" 或航班号 "ZH8848"
    route: str             # "成都东-重庆北"
    amount: float          # 票价
    ticket_type: str       # "火车" / "飞机"
    vehicle: str           # "二等座" / "飞机" / "硬卧"
    item: str              # "票价" / "机票" / "退票费"


@dataclass
class RawEmail:
    """一封原始邮件"""
    source: str            # "imap"
    uid: bytes | None      # IMAP UID
    raw_bytes: bytes       # 原始邮件 bytes
    subject: str           # 解码后的主题
```

- [ ] **步骤 5：复制 `parsers/base.py`（直接复用）**

```bash
cp /Users/yangjie/Qmail-Ticket/qmail_ticket/parsers/base.py \
   /Users/yangjie/Qmail-Ticket/cloudfunctions/fetchTickets/parsers/base.py
```

修改 import 路径为相对导入：
```python
"""票面解析器抽象基类"""
from abc import ABC, abstractmethod

from ..models import RawEmail, Ticket


class TicketParser(ABC):
    @abstractmethod
    def can_parse(self, raw_email: RawEmail) -> bool:
        """判断是否能解析此邮件"""

    @abstractmethod
    def parse(self, raw_email: RawEmail) -> list:
        """解析邮件，返回 [(pdf_bytes, pdf_name, [ticket, ...]), ...]"""
```

- [ ] **步骤 6：迁移 `parsers/train_12306.py`**

从原项目复制，修改 import 路径为相对导入：

```bash
cp /Users/yangjie/Qmail-Ticket/qmail_ticket/parsers/train_12306.py \
   /Users/yangjie/Qmail-Ticket/cloudfunctions/fetchTickets/parsers/train_12306.py
```

修改文件头部 import：
```python
"""12306 火车票解析器"""
import email.policy
import re
from email import message_from_bytes

from ..models import RawEmail, Ticket
from ..utils.email_utils import extract_12306_pdf
from ..utils.pdf_utils import pdf_to_text
from .base import TicketParser
```

其余逻辑（`_parse_12306_text`、`_match_by_pinyin_blocks`、`_match_by_pinyin_lines`、`_extract_travel_date`、`_extract_amount`）完全保留。

- [ ] **步骤 7：迁移 `parsers/ctrip.py`**

从原项目复制，修改 import 路径为相对导入：

```bash
cp /Users/yangjie/Qmail-Ticket/qmail_ticket/parsers/ctrip.py \
   /Users/yangjie/Qmail-Ticket/cloudfunctions/fetchTickets/parsers/ctrip.py
```

修改文件头部 import：
```python
"""携程机票解析器"""
import email.policy
import quopri
import re
from email import message_from_bytes

from ..models import RawEmail, Ticket
from ..utils.email_utils import extract_ctrip_pdfs
from ..utils.pdf_utils import pdf_to_text
from .base import TicketParser
```

其余逻辑完全保留。

- [ ] **步骤 8：创建 `parsers/__init__.py`**

```python
"""解析器模块"""
from .train_12306 import Train12306Parser
from .ctrip import CtripParser
from ..models import RawEmail

PARSERS = [Train12306Parser(), CtripParser()]


def get_parser(raw_email: RawEmail):
    """根据邮件主题选择解析器"""
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
```

- [ ] **步骤 9：迁移 `utils/email_utils.py`**

直接复制，无需修改（纯标准库，无外部依赖）：

```bash
cp /Users/yangjie/Qmail-Ticket/qmail_ticket/email_utils.py \
   /Users/yangjie/Qmail-Ticket/cloudfunctions/fetchTickets/utils/email_utils.py
```

- [ ] **步骤 10：迁移 `utils/pdf_utils.py`**

复制并增加 `pdf_to_jpg_bytes` 函数（返回 bytes 而非写文件）：

```python
"""PDF 文本提取和图片转换工具"""
import io
import fitz


def pdf_to_text(pdf_bytes: bytes) -> str:
    """从 PDF 字节提取文本。"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception:
        return ""


def pdf_to_jpg_bytes(pdf_bytes: bytes, dpi: int = 150) -> bytes:
    """将 PDF 第一页转为 JPG bytes。"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    jpg_bytes = pix.tobytes("jpeg")
    doc.close()
    return jpg_bytes
```

- [ ] **步骤 11：创建 `utils/__init__.py`**

```python
"""工具模块"""
```

- [ ] **步骤 12：Commit**

```bash
git add cloudfunctions/fetchTickets/
git commit -m "feat: migrate Python parsers/sources/utils to cloud function"
```

---

## 任务 4：fetchTickets 云函数主逻辑

**文件：**
- 创建：`cloudfunctions/fetchTickets/main.py`
- 创建：`cloudfunctions/fetchTickets/config.json`

- [ ] **步骤 1：创建 `config.json`（函数配置）**

```json
{
  "permissions": {
    "openapi": []
  },
  "timeout": 120,
  "memorySize": 512,
  "layers": [
    {
      "name": "pymupdf-pillow-layer",
      "version": 1
    }
  ]
}
```

- [ ] **步骤 2：创建 `main.py`**

```python
"""fetchTickets 云函数主入口"""
import csv
import io
import os
import uuid
from dataclasses import asdict

import fitz
from PIL import Image

from sources.imap import ImapSource
from parsers import get_parser
from models import Ticket


def main(event, context):
    """云函数入口"""
    email = event['email']
    code = event['code']
    task_id = event.get('taskId', str(uuid.uuid4()))
    start_date = _parse_date(event.get('startDate'))
    end_date = _parse_date(event.get('endDate'))

    import datetime
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    db = _get_db()

    try:
        # [1/4] IMAP 连接
        _update_progress(db, task_id, 'connecting', '0/0')
        source = ImapSource(email, code)
        source.connect()
        raw_emails = source.search(start_date, end_date)
        source.disconnect()

        if not raw_emails:
            _update_progress(db, task_id, 'done', '0/0')
            return {'taskId': task_id, 'tickets': [], 'fileIds': {'jpgs': [], 'csv': '', 'pdf': ''}}

        _update_progress(db, task_id, 'parsing', f'0/{len(raw_emails)}')

        # [2/4] 逐封解析，流式处理
        all_tickets = []
        jpg_file_ids = []

        for i, raw in enumerate(raw_emails):
            parser = get_parser(raw)
            if not parser:
                continue
            results = parser.parse(raw)
            if not results:
                continue
            for pdf_bytes, pdf_name, tickets in results:
                # 转 JPG 并上传
                jpg_bytes = _pdf_to_jpg_bytes(pdf_bytes, dpi=150)
                safe_name = pdf_name.replace('.pdf', '.jpg')
                jpg_id = _upload_to_cloud(jpg_bytes, f"tickets/{task_id}/{safe_name}")
                jpg_file_ids.append(jpg_id)

                # PDF 原文上传
                pdf_id = _upload_to_cloud(pdf_bytes, f"tickets/{task_id}/{pdf_name}")

                for t in tickets:
                    ticket_dict = asdict(t)
                    ticket_dict['jpgFileId'] = jpg_id
                    ticket_dict['pdfFileId'] = pdf_id
                    all_tickets.append(ticket_dict)

                del pdf_bytes, jpg_bytes

            _update_progress(db, task_id, 'parsing', f'{i+1}/{len(raw_emails)}')

        if not all_tickets:
            _update_progress(db, task_id, 'done', f'{len(raw_emails)}/{len(raw_emails)}')
            return {'taskId': task_id, 'tickets': [], 'fileIds': {'jpgs': [], 'csv': '', 'pdf': ''}}

        # [3/4] 生成 CSV 和 print.pdf
        _update_progress(db, task_id, 'generating', f'{len(raw_emails)}/{len(raw_emails)}')
        csv_id = _generate_csv(all_tickets, task_id)
        print_pdf_id = _generate_print_pdf(jpg_file_ids, all_tickets, task_id)

        # [4/4] 写入数据库
        _save_tickets(db, task_id, all_tickets)

        total_amount = sum(t['amount'] for t in all_tickets)
        _update_task_done(db, task_id, len(all_tickets), total_amount,
                          {'jpgs': jpg_file_ids, 'csv': csv_id, 'pdf': print_pdf_id})

        return {
            'taskId': task_id,
            'tickets': all_tickets,
            'fileIds': {
                'jpgs': jpg_file_ids,
                'csv': csv_id,
                'pdf': print_pdf_id,
            },
        }

    except Exception as e:
        _update_progress(db, task_id, 'error', str(e))
        raise


def _parse_date(s):
    if not s:
        return None
    from datetime import datetime
    return datetime.strptime(s.strip(), "%Y-%m-%d")


def _get_db():
    from wechatcloudbase import tcb
    return tcb.Database()


def _update_progress(db, task_id, status, progress):
    try:
        db.collection('tasks').doc(task_id).update({
            'data': {
                'status': status,
                'progress': progress,
            }
        })
    except Exception:
        pass


def _update_task_done(db, task_id, ticket_count, total_amount, file_ids):
    try:
        db.collection('tasks').doc(task_id).update({
            'data': {
                'status': 'done',
                'progress': 'done',
                'ticketCount': ticket_count,
                'totalAmount': round(total_amount, 2),
                'fileIds': file_ids,
            }
        })
    except Exception:
        pass


def _pdf_to_jpg_bytes(pdf_bytes, dpi=150):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    jpg_bytes = pix.tobytes("jpeg")
    doc.close()
    return jpg_bytes


def _upload_to_cloud(file_bytes, cloud_path):
    """上传文件到云存储，返回 fileID"""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
    tmp.write(file_bytes)
    tmp.close()

    from wechatcloudbase import tcb
    res = tcb.upload_file(cloud_path, tmp.name)
    os.unlink(tmp.name)
    return res['fileID']


def _generate_csv(all_tickets, task_id):
    """生成 CSV 并上传"""
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['乘车日期', '交通工具', '车次/航班', '发到站', '票价'])
    total = 0.0
    for t in sorted(all_tickets, key=lambda x: x['travelDate']):
        w.writerow([
            t['travelDate'], t['vehicle'], t['carrier'],
            t['route'], f"{t['amount']:.2f}"
        ])
        total += t['amount']
    w.writerow(['合计', '', '', '', f"{total:.2f}"])

    csv_bytes = output.getvalue().encode('utf-8-sig')
    return _upload_to_cloud(csv_bytes, f"tickets/{task_id}/ticket_summary.csv")


def _generate_print_pdf(jpg_file_ids, all_tickets, task_id):
    """合并 JPG 为 print.pdf 并上传"""
    A4_DPI = 150
    PAGE_W = int(210 / 25.4 * A4_DPI)
    PAGE_H = int(297 / 25.4 * A4_DPI)
    MARGIN = 60
    SPACING = 24

    trains = sorted([t for t in all_tickets if t['ticketType'] == '火车'],
                    key=lambda x: x['travelDate'])
    flights = sorted([t for t in all_tickets if t['ticketType'] == '飞机'],
                     key=lambda x: x['travelDate'])

    # 从云存储下载 JPG 并生成页面
    def make_pages(ticket_list, cols, rows):
        pages = []
        per_page = cols * rows
        cell_w = (PAGE_W - 2 * MARGIN - (cols - 1) * SPACING) / cols
        cell_h = (PAGE_H - 2 * MARGIN - (rows - 1) * SPACING) / rows

        for i in range(0, len(ticket_list), per_page):
            page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
            batch = ticket_list[i:i + per_page]

            for j, t in enumerate(batch):
                jpg_id = t.get('jpgFileId', '')
                if not jpg_id:
                    continue
                try:
                    tmp_path = _download_from_cloud(jpg_id)
                    img = Image.open(tmp_path)
                    img_ratio = img.width / img.height
                    cell_ratio = cell_w / cell_h
                    if img_ratio > cell_ratio:
                        new_w = cell_w
                        new_h = new_w / img_ratio
                    else:
                        new_h = cell_h
                        new_w = new_h * img_ratio
                    img_resized = img.resize((int(new_w), int(new_h)), Image.LANCZOS)
                    col = j % cols
                    row = j // cols
                    x = MARGIN + col * (cell_w + SPACING) + (cell_w - new_w) / 2
                    y = MARGIN + row * (cell_h + SPACING) + (cell_h - new_h) / 2
                    page.paste(img_resized, (int(x), int(y)))
                    os.unlink(tmp_path)
                except Exception:
                    continue

            pages.append(page)
        return pages

    train_pages = make_pages(trains, cols=2, rows=4)
    flight_pages = make_pages(flights, cols=2, rows=2)
    all_pages = train_pages + flight_pages

    if not all_pages:
        return ''

    for img in all_pages:
        img.info['dpi'] = (A4_DPI, A4_DPI)

    pdf_buffer = io.BytesIO()
    all_pages[0].save(pdf_buffer, save_all=True, append_images=all_pages[1:], format='PDF')
    pdf_bytes = pdf_buffer.getvalue()

    return _upload_to_cloud(pdf_bytes, f"tickets/{task_id}/print.pdf")


def _download_from_cloud(file_id):
    """从云存储下载到临时文件"""
    import tempfile
    from wechatcloudbase import tcb
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
    tmp.close()
    tcb.download_file(file_id, tmp.name)
    return tmp.name


def _save_tickets(db, task_id, all_tickets):
    """批量写入票据到云数据库"""
    for t in all_tickets:
        t['_taskId'] = task_id
        try:
            db.collection('tickets').add({'data': t})
        except Exception:
            pass
```

- [ ] **步骤 3：Commit**

```bash
git add cloudfunctions/fetchTickets/
git commit -m "feat: implement fetchTickets cloud function with streaming pipeline"
```

---

## 任务 5：sendEmail 云函数

**文件：**
- 创建：`cloudfunctions/sendEmail/main.py`
- 创建：`cloudfunctions/sendEmail/config.json`

- [ ] **步骤 1：创建 `config.json`**

```json
{
  "permissions": {
    "openapi": []
  },
  "timeout": 60,
  "memorySize": 256
}
```

- [ ] **步骤 2：创建 `main.py`**

```python
"""sendEmail 云函数主入口"""
import io
import zipfile
import smtplib
import tempfile
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders


def main(event, context):
    """打包所有文件为 ZIP 并通过 SMTP 发送"""
    email_addr = event['email']
    auth_code = event['code']
    to_address = event['toAddress']
    file_ids = event['fileIds']  # {jpgs: [...], csv: '...', pdf: '...'}

    # 1. 收集所有文件 ID
    all_file_ids = []
    if file_ids.get('jpgs'):
        all_file_ids.extend(file_ids['jpgs'])
    if file_ids.get('csv'):
        all_file_ids.append(file_ids['csv'])
    if file_ids.get('pdf'):
        all_file_ids.append(file_ids['pdf'])

    if not all_file_ids:
        return {'success': False, 'error': '没有可发送的文件'}

    # 2. 从云存储下载并打包为 ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fid in all_file_ids:
            try:
                data, name = _download_file(fid)
                zf.writestr(name, data)
            except Exception as e:
                continue

    zip_bytes = zip_buffer.getvalue()

    # 3. 构建邮件
    msg = MIMEMultipart()
    msg['From'] = email_addr
    msg['To'] = to_address
    msg['Subject'] = 'Qmail-Ticket 票据提取结果'

    body = MIMEText('请查收附件中的票据文件。', 'plain', 'utf-8')
    msg.attach(body)

    part = MIMEBase('application', 'zip')
    part.set_payload(zip_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment',
                    filename=('utf-8', '', 'tickets.zip'))
    msg.attach(part)

    # 4. SMTP 发送
    with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=30) as server:
        server.login(email_addr, auth_code)
        server.send_message(msg)

    return {'success': True, 'to': to_address}


def _download_file(file_id):
    """从云存储下载文件，返回 (bytes, filename)"""
    from wechatcloudbase import tcb
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
    tmp.close()
    tcb.download_file(file_id, tmp.name)
    with open(tmp.name, 'rb') as f:
        data = f.read()
    os.unlink(tmp.name)
    name = file_id.split('/')[-1]
    return data, name
```

- [ ] **步骤 3：Commit**

```bash
git add cloudfunctions/sendEmail/
git commit -m "feat: implement sendEmail cloud function with SMTP"
```

---

## 任务 6：ticket-card 组件

**文件：**
- 创建：`miniprogram/components/ticket-card/ticket-card.wxml`
- 创建：`miniprogram/components/ticket-card/ticket-card.wxss`
- 创建：`miniprogram/components/ticket-card/ticket-card.js`
- 创建：`miniprogram/components/ticket-card/ticket-card.json`

- [ ] **步骤 1：创建 `ticket-card.json`**

```json
{
  "component": true
}
```

- [ ] **步骤 2：创建 `ticket-card.wxml`**

```html
<view class="ticket-card">
  <view class="ticket-header">
    <text class="ticket-date">{{ticket.travelDate}}</text>
    <text class="ticket-type {{ticket.ticketType === '火车' ? 'type-train' : 'type-plane'}}">
      {{ticket.ticketType === '火车' ? '🚄' : '✈️'}} {{ticket.carrier}}
    </text>
  </view>
  <view class="ticket-body">
    <view class="ticket-route">
      <text class="route-text">{{ticket.route}}</text>
      <text class="ticket-vehicle">{{ticket.vehicle}}</text>
    </view>
    <text class="ticket-amount">¥{{ticket.amount}}</text>
  </view>
</view>
```

- [ ] **步骤 3：创建 `ticket-card.wxss`**

```css
.ticket-card {
  background-color: #fff;
  border-radius: 16rpx;
  padding: 24rpx 30rpx;
  margin-bottom: 20rpx;
  box-shadow: 0 2rpx 12rpx rgba(0, 0, 0, 0.06);
}

.ticket-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16rpx;
}

.ticket-date {
  font-size: 26rpx;
  color: #999;
}

.ticket-type {
  font-size: 28rpx;
  font-weight: 500;
}

.type-train {
  color: #1890ff;
}

.type-plane {
  color: #722ed1;
}

.ticket-body {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ticket-route {
  flex: 1;
}

.route-text {
  font-size: 32rpx;
  font-weight: 600;
  color: #333;
  display: block;
  margin-bottom: 4rpx;
}

.ticket-vehicle {
  font-size: 24rpx;
  color: #999;
}

.ticket-amount {
  font-size: 36rpx;
  font-weight: 700;
  color: #ff4d4f;
}
```

- [ ] **步骤 4：创建 `ticket-card.js`**

```javascript
Component({
  properties: {
    ticket: {
      type: Object,
      value: {},
    },
  },
})
```

- [ ] **步骤 5：Commit**

```bash
git add miniprogram/components/ticket-card/
git commit -m "feat: add ticket-card component"
```

---

## 任务 7：首页（index 页面）

**文件：**
- 创建：`miniprogram/pages/index/index.wxml`
- 创建：`miniprogram/pages/index/index.wxss`
- 创建：`miniprogram/pages/index/index.js`
- 创建：`miniprogram/pages/index/index.json`

- [ ] **步骤 1：创建 `index.json`**

```json
{
  "navigationBarTitleText": "Qmail-Ticket"
}
```

- [ ] **步骤 2：创建 `index.wxml`**

```html
<view class="container">
  <view class="header">
    <text class="title">Qmail-Ticket</text>
    <text class="subtitle">火车票 · 机票 提取工具</text>
  </view>

  <view class="form">
    <view class="form-item">
      <text class="label">QQ邮箱</text>
      <input class="input" type="text" placeholder="your@qq.com"
             value="{{email}}" bindinput="onEmailInput" />
    </view>

    <view class="form-item">
      <text class="label">授权码</text>
      <input class="input" type="text" password placeholder="邮箱授权码"
             value="{{code}}" bindinput="onCodeInput" />
    </view>

    <view class="form-item">
      <text class="label">起始日期（可选）</text>
      <picker mode="date" value="{{startDate}}" bindchange="onStartDateChange">
        <view class="picker">{{startDate || '不限'}}</view>
      </picker>
    </view>

    <view class="form-item">
      <text class="label">截止日期（可选）</text>
      <picker mode="date" value="{{endDate}}" bindchange="onEndDateChange">
        <view class="picker">{{endDate || '不限'}}</view>
      </picker>
    </view>

    <button class="btn-primary" bindtap="onStartFetch"
            disabled="{{loading || !email || !code}}">
      {{loading ? progress || '正在连接...' : '开始提取'}}
    </button>
  </view>

  <view class="tips">
    <text class="tips-title">使用说明</text>
    <text class="tips-text">1. 授权码在QQ邮箱设置 → 账户 → POP3/IMAP 中生成</text>
    <text class="tips-text">2. 仅支持 12306 火车票和携程机票邮件</text>
    <text class="tips-text">3. 首次输入后会自动保存，无需重复输入</text>
  </view>
</view>
```

- [ ] **步骤 3：创建 `index.wxss`**

```css
.header {
  text-align: center;
  padding: 60rpx 0 40rpx;
}

.title {
  font-size: 48rpx;
  font-weight: 700;
  color: var(--primary-color);
  display: block;
}

.subtitle {
  font-size: 28rpx;
  color: var(--text-secondary);
  display: block;
  margin-top: 8rpx;
}

.form {
  background-color: var(--card-bg);
  border-radius: 16rpx;
  padding: 30rpx;
  margin-bottom: 30rpx;
}

.form-item {
  margin-bottom: 30rpx;
}

.label {
  font-size: 26rpx;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 12rpx;
}

.input {
  border: 2rpx solid var(--border-color);
  border-radius: 8rpx;
  padding: 20rpx;
  font-size: 28rpx;
}

.picker {
  border: 2rpx solid var(--border-color);
  border-radius: 8rpx;
  padding: 20rpx;
  font-size: 28rpx;
  color: var(--text-color);
}

.tips {
  background-color: var(--card-bg);
  border-radius: 16rpx;
  padding: 30rpx;
}

.tips-title {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--text-color);
  display: block;
  margin-bottom: 16rpx;
}

.tips-text {
  font-size: 24rpx;
  color: var(--text-secondary);
  display: block;
  line-height: 1.8;
}
```

- [ ] **步骤 4：创建 `index.js`**

```javascript
const { fetchTickets, createTask, watchTask } = require('../../utils/cloud')

Page({
  data: {
    email: '',
    code: '',
    startDate: '',
    endDate: '',
    loading: false,
    progress: '',
    taskId: '',
    pollTimer: null,
  },

  onLoad() {
    // 从本地 storage 恢复保存的配置
    const saved = wx.getStorageSync('imap_config')
    if (saved) {
      this.setData({
        email: saved.email || '',
        code: saved.code || '',
      })
    }
  },

  onUnload() {
    if (this.data.pollTimer) {
      clearInterval(this.data.pollTimer)
    }
  },

  onEmailInput(e) {
    this.setData({ email: e.detail.value })
  },

  onCodeInput(e) {
    this.setData({ code: e.detail.value })
  },

  onStartDateChange(e) {
    this.setData({ startDate: e.detail.value })
  },

  onEndDateChange(e) {
    this.setData({ endDate: e.detail.value })
  },

  async onStartFetch() {
    const { email, code, startDate, endDate } = this.data
    if (!email || !code) {
      wx.showToast({ title: '请输入邮箱和授权码', icon: 'none' })
      return
    }

    // 保存配置到本地
    wx.setStorageSync('imap_config', { email, code })

    this.setData({ loading: true, progress: '正在连接...' })

    try {
      // 创建任务记录
      const taskId = await createTask()
      this.setData({ taskId })

      // 调用云函数（异步，不等待返回）
      fetchTickets({ email, code, startDate, endDate, taskId })

      // 轮询进度
      const timer = watchTask(taskId, (taskData) => {
        const statusMap = {
          connecting: '正在连接邮箱...',
          connected: '已连接，开始解析...',
          parsing: `正在解析票面 ${taskData.progress}`,
          generating: '正在生成文件...',
          done: '完成！',
          error: `出错: ${taskData.progress}`,
        }
        this.setData({ progress: statusMap[taskData.status] || taskData.status })

        if (taskData.status === 'done') {
          this.setData({ loading: false })
          clearInterval(this.data.pollTimer)
          wx.showToast({ title: '提取完成', icon: 'success' })
          wx.switchTab({ url: '/pages/tickets/tickets' })
        } else if (taskData.status === 'error') {
          this.setData({ loading: false })
          clearInterval(this.data.pollTimer)
          wx.showToast({ title: '提取失败', icon: 'none' })
        }
      })
      this.setData({ pollTimer: timer })
    } catch (e) {
      this.setData({ loading: false })
      wx.showToast({ title: '调用失败: ' + e.message, icon: 'none' })
    }
  },
})
```

- [ ] **步骤 5：Commit**

```bash
git add miniprogram/pages/index/
git commit -m "feat: add index page with email config and progress polling"
```

---

## 任务 8：票据列表页（tickets 页面）

**文件：**
- 创建：`miniprogram/pages/tickets/tickets.wxml`
- 创建：`miniprogram/pages/tickets/tickets.wxss`
- 创建：`miniprogram/pages/tickets/tickets.js`
- 创建：`miniprogram/pages/tickets/tickets.json`

- [ ] **步骤 1：创建 `tickets.json`**

```json
{
  "navigationBarTitleText": "票据列表",
  "usingComponents": {
    "ticket-card": "/components/ticket-card/ticket-card"
  }
}
```

- [ ] **步骤 2：创建 `tickets.wxml`**

```html
<view class="container">
  <view class="summary" wx:if="{{tickets.length}}">
    <text class="summary-text">合计: </text>
    <text class="summary-amount">¥{{totalAmount}}</text>
    <text class="summary-count">共 {{tickets.length}} 张</text>
  </view>

  <view class="empty" wx:if="{{!tickets.length && !loading}}">
    <text class="empty-text">暂无票据数据</text>
    <text class="empty-hint">请先在首页提取票据</text>
  </view>

  <view class="month-group" wx:for="{{groupedTickets}}" wx:key="month">
    <text class="month-title">{{item.month}}</text>
    <ticket-card
      wx:for="{{item.tickets}}"
      wx:for-item="ticket"
      wx:key="travelDate"
      ticket="{{ticket}}"
    />
  </view>

  <button class="btn-primary export-btn" wx:if="{{tickets.length}}"
          bindtap="goExport">
    导出文件 →
  </button>
</view>
```

- [ ] **步骤 3：创建 `tickets.wxss`**

```css
.summary {
  background-color: var(--card-bg);
  border-radius: 16rpx;
  padding: 30rpx;
  margin-bottom: 30rpx;
  display: flex;
  align-items: baseline;
  gap: 12rpx;
}

.summary-text {
  font-size: 28rpx;
  color: var(--text-secondary);
}

.summary-amount {
  font-size: 44rpx;
  font-weight: 700;
  color: #ff4d4f;
}

.summary-count {
  font-size: 24rpx;
  color: #999;
  margin-left: auto;
}

.empty {
  text-align: center;
  padding: 120rpx 0;
}

.empty-text {
  font-size: 32rpx;
  color: var(--text-secondary);
  display: block;
}

.empty-hint {
  font-size: 26rpx;
  color: #999;
  display: block;
  margin-top: 16rpx;
}

.month-title {
  font-size: 28rpx;
  font-weight: 600;
  color: var(--text-secondary);
  display: block;
  margin-bottom: 16rpx;
  margin-top: 20rpx;
}

.month-group:first-child .month-title {
  margin-top: 0;
}

.export-btn {
  margin-top: 40rpx;
}
```

- [ ] **步骤 4：创建 `tickets.js`**

```javascript
const { getTickets, getTask } = require('../../utils/cloud')

Page({
  data: {
    tickets: [],
    groupedTickets: [],
    totalAmount: '0.00',
    loading: true,
  },

  onShow() {
    this.loadTickets()
  },

  async loadTickets() {
    this.setData({ loading: true })
    try {
      // 获取最新任务
      const db = require('../../utils/cloud').db
      const { data: tasks } = await db.collection('tasks')
        .where({ status: 'done' })
        .orderBy('createTime', 'desc')
        .limit(1)
        .get()

      if (!tasks.length) {
        this.setData({ tickets: [], groupedTickets: [], loading: false })
        return
      }

      const taskId = tasks[0]._id
      const tickets = await getTickets(taskId)

      // 计算总金额
      const totalAmount = tickets.reduce((sum, t) => sum + t.amount, 0).toFixed(2)

      // 按月份分组
      const grouped = this._groupByMonth(tickets)

      this.setData({
        tickets,
        groupedTickets: grouped,
        totalAmount,
        loading: false,
      })
    } catch (e) {
      console.error('加载票据失败:', e)
      this.setData({ loading: false })
    }
  },

  _groupByMonth(tickets) {
    const map = {}
    tickets.forEach(t => {
      const month = t.travelDate.substring(0, 7) // "2026-04"
      if (!map[month]) {
        map[month] = { month: `${month.substring(0,4)}年${month.substring(5,7)}月`, tickets: [] }
      }
      map[month].tickets.push(t)
    })
    return Object.values(map).sort((a, b) => b.month.localeCompare(a.month))
  },

  goExport() {
    wx.switchTab({ url: '/pages/export/export' })
  },
})
```

- [ ] **步骤 5：Commit**

```bash
git add miniprogram/pages/tickets/
git commit -m "feat: add tickets page with monthly grouping"
```

---

## 任务 9：导出页（export 页面）

**文件：**
- 创建：`miniprogram/pages/export/export.wxml`
- 创建：`miniprogram/pages/export/export.wxss`
- 创建：`miniprogram/pages/export/export.js`
- 创建：`miniprogram/pages/export/export.json`

- [ ] **步骤 1：创建 `export.json`**

```json
{
  "navigationBarTitleText": "导出文件"
}
```

- [ ] **步骤 2：创建 `export.wxml`**

```html
<view class="container">
  <!-- 全部下载 -->
  <button class="btn-primary btn-download-all" bindtap="downloadAll"
          disabled="{{downloading}}">
    {{downloading ? downloadProgress || '正在下载...' : '⬇ 全部下载到手机'}}
  </button>

  <!-- 发送到邮箱 -->
  <view class="section">
    <text class="section-title">发送到邮箱</text>
    <view class="email-form">
      <input class="input" type="text" placeholder="收件地址"
             value="{{toAddress}}" bindinput="onToAddressInput" />
      <button class="btn-send" bindtap="sendEmail"
              disabled="{{sending || !toAddress}}">
        {{sending ? '发送中...' : '发送'}}
      </button>
    </view>
  </view>

  <!-- 票据图片 -->
  <view class="section" wx:if="{{fileIds.jpgs.length}}">
    <text class="section-title">票据图片 ({{fileIds.jpgs.length}}张)</text>
    <scroll-view scroll-x class="jpg-scroll">
      <view class="jpg-list">
        <image wx:for="{{jpgPreviews}}" wx:key="index"
               class="jpg-thumb" src="{{item}}" mode="aspectFill"
               bindtap="previewJpg" data-index="{{index}}" />
      </view>
    </scroll-view>
    <button class="btn-secondary" bindtap="saveAllJpgs"
            disabled="{{savingJpgs}}">
      {{savingJpgs ? jpgProgress || '保存中...' : '保存到相册'}}
    </button>
  </view>

  <!-- CSV 汇总表 -->
  <view class="section" wx:if="{{fileIds.csv}}">
    <text class="section-title">汇总表</text>
    <view class="file-card">
      <view class="file-info">
        <text class="file-icon">📊</text>
        <view class="file-detail">
          <text class="file-name">ticket_summary.csv</text>
          <text class="file-meta">{{ticketCount}}条记录</text>
        </view>
      </view>
      <button class="btn-download" bindtap="downloadCsv">下载</button>
    </view>
  </view>

  <!-- 合并打印 PDF -->
  <view class="section" wx:if="{{fileIds.pdf}}">
    <text class="section-title">合并打印</text>
    <view class="file-card">
      <view class="file-info">
        <text class="file-icon">📄</text>
        <view class="file-detail">
          <text class="file-name">print.pdf</text>
          <text class="file-meta">火车票8张/页 · 机票4张/页</text>
        </view>
      </view>
      <button class="btn-download" bindtap="downloadPdf">下载</button>
    </view>
  </view>
</view>
```

- [ ] **步骤 3：创建 `export.wxss`**

```css
.btn-download-all {
  margin-bottom: 40rpx;
  background-color: #52c41a;
}

.section {
  background-color: var(--card-bg);
  border-radius: 16rpx;
  padding: 30rpx;
  margin-bottom: 24rpx;
}

.section-title {
  font-size: 30rpx;
  font-weight: 600;
  color: var(--text-color);
  display: block;
  margin-bottom: 20rpx;
}

.email-form {
  display: flex;
  gap: 16rpx;
  align-items: center;
}

.email-form .input {
  flex: 1;
  border: 2rpx solid var(--border-color);
  border-radius: 8rpx;
  padding: 16rpx 20rpx;
  font-size: 28rpx;
}

.btn-send {
  background-color: var(--primary-color);
  color: #fff;
  border: none;
  border-radius: 8rpx;
  padding: 16rpx 32rpx;
  font-size: 28rpx;
  white-space: nowrap;
}

.jpg-scroll {
  margin-bottom: 20rpx;
}

.jpg-list {
  display: flex;
  gap: 16rpx;
  padding: 8rpx 0;
}

.jpg-thumb {
  width: 160rpx;
  height: 120rpx;
  border-radius: 8rpx;
  flex-shrink: 0;
  background-color: #f0f0f0;
}

.btn-secondary {
  background-color: #f0f0f0;
  color: var(--text-color);
  border: none;
  border-radius: 8rpx;
  padding: 16rpx;
  font-size: 28rpx;
}

.file-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.file-icon {
  font-size: 40rpx;
}

.file-name {
  font-size: 28rpx;
  color: var(--text-color);
  display: block;
}

.file-meta {
  font-size: 24rpx;
  color: #999;
  display: block;
  margin-top: 4rpx;
}

.btn-download {
  background-color: var(--primary-color);
  color: #fff;
  border: none;
  border-radius: 8rpx;
  padding: 12rpx 24rpx;
  font-size: 26rpx;
}
```

- [ ] **步骤 4：创建 `export.js`**

```javascript
const cloud = require('../../utils/cloud')

Page({
  data: {
    fileIds: { jpgs: [], csv: '', pdf: '' },
    jpgPreviews: [],
    ticketCount: 0,
    toAddress: '',
    downloading: false,
    downloadProgress: '',
    savingJpgs: false,
    jpgProgress: '',
    sending: false,
  },

  onLoad() {
    const saved = wx.getStorageSync('imap_config')
    if (saved && saved.lastToAddress) {
      this.setData({ toAddress: saved.lastToAddress })
    }
    this.loadFileIds()
  },

  async loadFileIds() {
    try {
      const db = cloud.db
      const { data: tasks } = await db.collection('tasks')
        .where({ status: 'done' })
        .orderBy('createTime', 'desc')
        .limit(1)
        .get()

      if (!tasks.length) return

      const task = tasks[0]
      const fileIds = task.fileIds || { jpgs: [], csv: '', pdf: '' }

      // 获取 JPG 预览临时链接
      const jpgPreviews = []
      for (const fid of fileIds.jpgs.slice(0, 10)) {
        try {
          const res = await wx.cloud.getTempFileURL({ fileList: [fid] })
          if (res.fileList[0].tempFileURL) {
            jpgPreviews.push(res.fileList[0].tempFileURL)
          }
        } catch (e) {}
      }

      this.setData({
        fileIds,
        jpgPreviews,
        ticketCount: task.ticketCount || 0,
      })
    } catch (e) {
      console.error('加载文件信息失败:', e)
    }
  },

  onToAddressInput(e) {
    this.setData({ toAddress: e.detail.value })
  },

  // 全部下载
  async downloadAll() {
    this.setData({ downloading: true, downloadProgress: '正在保存图片...' })
    try {
      await this.saveAllJpgs()
      this.setData({ downloadProgress: '正在打开 CSV...' })
      await this.downloadCsv()
      this.setData({ downloadProgress: '正在打开 PDF...' })
      await this.downloadPdf()
      wx.showToast({ title: '全部下载完成', icon: 'success' })
    } catch (e) {
      wx.showToast({ title: '部分下载失败', icon: 'none' })
    } finally {
      this.setData({ downloading: false, downloadProgress: '' })
    }
  },

  // 保存所有 JPG 到相册
  async saveAllJpgs() {
    if (!this.data.fileIds.jpgs.length) return
    this.setData({ savingJpgs: true })
    const total = this.data.fileIds.jpgs.length
    try {
      for (let i = 0; i < total; i++) {
        this.setData({ jpgProgress: `${i + 1}/${total}` })
        const tempPath = await cloud.downloadFile(this.data.fileIds.jpgs[i])
        await cloud.saveImageToAlbum(tempPath)
      }
      if (!this.data.downloading) {
        wx.showToast({ title: '已保存到相册', icon: 'success' })
      }
    } catch (e) {
      if (e.errMsg && e.errMsg.includes('auth deny')) {
        wx.showModal({
          title: '需要授权',
          content: '请在设置中允许保存到相册',
          confirmText: '去设置',
          success(res) {
            if (res.confirm) wx.openSetting()
          },
        })
      }
    } finally {
      this.setData({ savingJpgs: false, jpgProgress: '' })
    }
  },

  previewJpg(e) {
    const index = e.currentTarget.dataset.index
    wx.previewImage({
      urls: this.data.jpgPreviews,
      current: this.data.jpgPreviews[index],
    })
  },

  // 下载 CSV
  async downloadCsv() {
    if (!this.data.fileIds.csv) return
    try {
      const tempPath = await cloud.downloadFile(this.data.fileIds.csv)
      await cloud.openDocument(tempPath, 'csv')
    } catch (e) {
      wx.showToast({ title: 'CSV 下载失败', icon: 'none' })
    }
  },

  // 下载 PDF
  async downloadPdf() {
    if (!this.data.fileIds.pdf) return
    try {
      const tempPath = await cloud.downloadFile(this.data.fileIds.pdf)
      await cloud.openDocument(tempPath, 'pdf')
    } catch (e) {
      wx.showToast({ title: 'PDF 下载失败', icon: 'none' })
    }
  },

  // 发送到邮箱
  async sendEmail() {
    const { toAddress, fileIds } = this.data
    if (!toAddress) {
      wx.showToast({ title: '请输入收件地址', icon: 'none' })
      return
    }

    // 保存收件地址
    const saved = wx.getStorageSync('imap_config') || {}
    saved.lastToAddress = toAddress
    wx.setStorageSync('imap_config', saved)

    this.setData({ sending: true })
    try {
      const { email, code } = wx.getStorageSync('imap_config')
      const res = await cloud.sendEmail({ email, code, toAddress, fileIds })
      if (res.result && res.result.success) {
        wx.showToast({ title: `已发送至 ${toAddress}`, icon: 'success' })
      } else {
        wx.showToast({ title: '发送失败', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: '发送失败: ' + e.message, icon: 'none' })
    } finally {
      this.setData({ sending: false })
    }
  },
})
```

- [ ] **步骤 5：Commit**

```bash
git add miniprogram/pages/export/
git commit -m "feat: add export page with download and email sending"
```

---

## 任务 10：整体联调与清理

- [ ] **步骤 1：更新 `app.json` 注册所有页面和组件**

确认 `app.json` 中 `pages` 数组包含所有三个页面路径，`usingComponents` 如需全局组件则在此配置。

- [ ] **步骤 2：检查所有 import 路径**

```bash
# 检查云函数 import 是否正确
cd /Users/yangjie/Qmail-Ticket/cloudfunctions/fetchTickets
python -c "from sources.imap import ImapSource; print('OK')" 2>&1 || echo "需要检查 import"
python -c "from parsers import get_parser; print('OK')" 2>&1 || echo "需要检查 import"
```

- [ ] **步骤 3：检查小程序文件完整性**

```bash
cd /Users/yangjie/Qmail-Ticket
# 验证所有页面文件都存在
for page in index tickets export; do
  for ext in wxml wxss js json; do
    test -f miniprogram/pages/${page}/${page}.${ext} && echo "OK: ${page}.${ext}" || echo "MISSING: ${page}.${ext}"
  done
done
# 验证组件
for ext in wxml wxss js json; do
  test -f miniprogram/components/ticket-card/ticket-card.${ext} && echo "OK: ticket-card.${ext}" || echo "MISSING: ticket-card.${ext}"
done
```

- [ ] **步骤 4：创建 `.gitignore` 更新**

确认 `.gitignore` 包含：
```
__pycache__/
*.pyc
.DS_Store
node_modules/
miniprogram/miniprogram_npm/
```

- [ ] **步骤 5：Commit**

```bash
git add -A
git commit -m "feat: complete miniprogram project structure and integration"
```

---

## 任务 11：README 更新

**文件：**
- 修改：`README.md`

- [ ] **步骤 1：在 README 末尾添加小程序版说明**

在现有 README 末尾追加：

```markdown

---

## 微信小程序版

基于微信云开发的移动端版本，功能与 CLI 版一致。

### 项目结构

```
miniprogram/          # 小程序前端
cloudfunctions/       # 云函数（Python）
├── pymupdf-pillow-layer/  # PyMuPDF + Pillow 公共层
├── fetchTickets/          # 邮件提取 + 解析
└── sendEmail/             # ZIP 打包 + SMTP 发送
```

### 部署步骤

1. 在微信开发者工具中创建云开发项目
2. 上传 `pymupdf-pillow-layer` 作为公共层
3. 上传 `fetchTickets` 和 `sendEmail` 云函数
4. 在 `app.js` 中替换 `env: 'your-env-id'` 为实际云环境 ID
5. 在云开发控制台创建 `tasks` 和 `tickets` 两个数据库集合
6. 编译运行小程序

### 注意事项

- `fetchTickets` 函数超时设为 120 秒，邮件量大时可能需要申请延长
- 公共层需在 Linux x86_64 环境构建（使用 Docker 或 WSL）
- 微信小程序需要企业主体或个人主体备案才能使用 IMAP 等网络 API
```

- [ ] **步骤 2：Commit**

```bash
git add README.md
git commit -m "docs: add miniprogram section to README"
```
