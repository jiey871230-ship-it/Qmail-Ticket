# Qmail-Ticket 微信小程序版设计文档

## 1. 概述

将 Qmail-Ticket Python CLI 工具移植为微信小程序版本，用户通过小程序连接 QQ邮箱，自动提取 12306 火车票和携程机票电子发票，解析票面信息，并支持导出 JPG/CSV/PDF 文件。

### 1.1 功能范围

- **邮件源**：仅 QQ邮箱 IMAP（不支持 Foxmail 本地邮件）
- **解析**：12306 火车票 + 携程机票
- **导出**：
  - JPG 票据图片 → 保存到手机相册
  - CSV 汇总表 → 下载/预览
  - 合并排版 PDF → 下载/预览
  - 全部下载（一键保存所有文件）
  - 打包发送到指定邮箱（ZIP 附件通过 SMTP 发送）

### 1.2 不支持的功能

- Foxmail 本地邮件提取（小程序无法访问本地文件系统）
- 交互式命令行界面

## 2. 技术架构

```
┌──────────────────┐     云函数调用     ┌─────────────────────┐
│  微信小程序前端    │ ───────────────→ │  云函数 (Python)     │
│  WXML/WXSS/JS    │ ←─────────────── │  IMAP连接/解析/打包   │
└──────────────────┘     返回结果      └─────────────────────┘
         │                                      │
         │ wx API                               │
         ▼                                      ▼
┌──────────────────┐                   ┌─────────────────────┐
│  手机相册/文件     │                   │  云存储 + 云数据库    │
│  (下载目标)       │                   │  (文件+票据元数据)    │
└──────────────────┘                   └─────────────────────┘
```

### 2.1 前端：微信小程序

- 框架：原生微信小程序（WXML + WXSS + JavaScript）
- 页面：3 个主页面 + 相关组件
- 网络：通过 `wx.cloud.callFunction` 调用云函数

### 2.2 后端：微信云开发（Python）

- 云函数：Python 3.x 运行时
- 核心依赖：`PyMuPDF`（fitz）、`Pillow`、`imaplib`（标准库）
- 复用现有解析逻辑：`parsers/train_12306.py`、`parsers/ctrip.py`、`email_utils.py`、`pdf_utils.py`

### 2.3 存储

- **云数据库**：存储票据元数据（用于列表展示和历史记录）
- **云存储**：存放生成的 JPG/PDF/CSV 文件（临时，导出后可清理）

### 2.4 云函数优化策略

#### 2.4.1 公共层（Layer）解决依赖体积

PyMuPDF + Pillow 的原生二进制约 120MB，超过云函数 50MB 代码包限制。方案：

- 将 PyMuPDF + Pillow 打包为**云函数公共层**（Layer），函数代码本身仅含业务逻辑（< 5MB）
- 层可被多个函数共享，只需上传一次
- 冷启动时层已预加载，比内联依赖更快

```
layer: pymupdf-pillow-layer (120MB)
  └── python/lib/python3.x/site-packages/
      ├── fitz/          # PyMuPDF
      └── PIL/           # Pillow

function: fetchTickets (< 5MB)
  └── main.py + parsers/ + sources/ + utils/
```

#### 2.4.2 函数拆分避免超时

单个函数串联 IMAP + 解析 + 图片生成 + 上传，容易超过 20 秒默认超时。拆分为：

| 函数 | 职责 | 超时 | 内存 | 依赖层 |
|------|------|------|------|--------|
| `fetchTickets` | IMAP 连接 + 邮件搜索 + 票面解析 + 文件生成 + 上传 | 120s | 512MB | pymupdf-pillow |
| `sendEmail` | 从云存储下载文件 + ZIP 打包 + SMTP 发送 | 60s | 256MB | 无（标准库） |

> `fetchTickets` 是主要耗时函数，设置 120 秒超时（微信云开发可申请延长至 600 秒）。如果邮件量极大（> 100 封），可在前端轮询进度或分批处理。

#### 2.4.3 IMAP 连接优化

原项目 `ImapSource.search()` 逐封 FETCH 全文，邮件量大时极慢。优化：

1. **先扫主题再取全文**：先用 `BODY.PEEK[HEADER.FIELDS (SUBJECT)]` 只取主题头，匹配后再用 `RFC822` 取全文。避免下载无关邮件。
2. **日期前置过滤**：IMAP `SINCE/BEFORE` 在服务端过滤，减少返回的 UID 数量。
3. **单次连接**：connect → search → disconnect 在同一个函数调用中完成，不保持长连接。

```python
# 优化后的搜索流程
def search(self, start_date, end_date):
    # 1. 服务端日期过滤（减少 UID 数量）
    criteria = 'SINCE 01-Jan-2026 BEFORE 20-May-2026'
    _, data = conn.uid('SEARCH', criteria)
    all_uids = data[0].split()

    # 2. 只取主题头（极小数据量）
    matching_uids = []
    for uid in all_uids:
        _, hdr = conn.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
        if is_target_subject(hdr):
            matching_uids.append(uid)

    # 3. 只对匹配的邮件取全文
    results = []
    for uid in matching_uids:
        _, full = conn.uid('FETCH', uid, '(RFC822)')
        results.append(...)
    return results
```

#### 2.4.4 流式处理避免内存溢出

不将所有邮件和 PDF 同时加载到内存，改为逐封处理、逐个上传：

```python
# 逐封处理：解析一张 → 上传一张 → 释放内存
all_tickets = []
for raw in raw_emails:
    parser = get_parser(raw)
    if not parser:
        continue
    for pdf_bytes, pdf_name, tickets in parser.parse(raw):
        # 立即转 JPG 并上传
        jpg_bytes = pdf_to_jpg_bytes(pdf_bytes)
        jpg_file_id = upload_to_cloud(jpg_bytes, f"{pdf_name}.jpg")
        # 立即释放 PDF 内存
        del pdf_bytes
        all_tickets.append({
            'ticket': tickets[0],
            'jpgFileId': jpg_file_id,
        })

# 最后一次性生成 CSV 和 print.pdf（基于已上传的 JPG）
csv_file_id = generate_csv(all_tickets)
pdf_file_id = generate_print_pdf(all_tickets)  # 从云存储下载 JPG 合并
```

#### 2.4.5 压缩上传减少耗时

- JPG 质量设为 85%（而非 200 DPI 原图），单张约 200-400KB
- CSV 用 UTF-8 BOM 编码（兼容 Excel 打开）
- print.pdf 从已上传的 JPG 生成（不重新解码 PDF）

#### 2.4.6 前端轮询进度

`fetchTickets` 执行时间可能较长，前端通过云数据库轮询进度：

```python
# 云函数中写入进度
db.collection('tasks').doc(task_id).update({
    'status': 'parsing',
    'progress': '3/15',  # 已解析 3 封，共 15 封
})
```

```javascript
// 前端轮询
const timer = setInterval(async () => {
  const { data } = await db.collection('tasks').doc(taskId).get()
  this.setData({ progress: data.progress })
  if (data.status === 'done') {
    clearInterval(timer)
    wx.navigateTo({ url: '/pages/tickets/tickets' })
  }
}, 2000)
```

## 3. 页面设计

### 3.1 首页（提取配置）

```
┌─────────────────────────────┐
│        Qmail-Ticket          │
│    火车票 · 机票 提取工具     │
├─────────────────────────────┤
│                             │
│  QQ邮箱:                    │
│  ┌─────────────────────────┐│
│  │ your@qq.com             ││
│  └─────────────────────────┘│
│                             │
│  授权码:                     │
│  ┌─────────────────────────┐│
│  │ ••••••••                ││
│  └─────────────────────────┘│
│                             │
│  日期范围:                   │
│  ┌──────────┐ ┌──────────┐ ││
│  │ 2026-01-01│ │ 2026-12-31│ ││
│  └──────────┘ └──────────┘ ││
│                             │
│  ╔═════════════════════════╗│
│  ║      开始提取            ║│
│  ╚═════════════════════════╝│
│                             │
│  提示: 授权码在QQ邮箱设置    │
│  → 账户 → POP3/IMAP 中生成  │
│                             │
├─────────────────────────────┤
│  首页  │  票据列表  │  导出  │
└─────────────────────────────┘
```

**交互流程：**
1. 输入 QQ邮箱地址和授权码（首次输入后自动保存到本地 storage）
2. 选择日期范围（可选，默认不限）
3. 点击"开始提取"，调用云函数
4. 加载中显示进度提示："正在连接邮箱..." → "正在解析票面..."
5. 完成后跳转到票据列表页

### 3.2 票据列表页

```
┌─────────────────────────────┐
│  ← 返回      票据列表 (20)   │
├─────────────────────────────┤
│                             │
│  合计: ¥8,560.00            │
│                             │
│  ┌─ 2026年4月 ─────────────┐│
│  │                         ││
│  │  04-28  🚄 G8888        ││
│  │         重庆北 → 成都东   ││
│  │         二等座   ¥154.00 ││
│  │  ───────────────────────││
│  │  04-22  🚄 G8652        ││
│  │         成都东 → 重庆北   ││
│  │         二等座   ¥154.00 ││
│  └─────────────────────────┘│
│                             │
│  ┌─ 2026年3月 ─────────────┐│
│  │  ...                    ││
│  └─────────────────────────┘│
│                             │
│  ╔═════════════════════════╗│
│  ║      导出文件 →          ║│
│  ╚═════════════════════════╝│
│                             │
├─────────────────────────────┤
│  首页  │  票据列表  │  导出  │
└─────────────────────────────┘
```

**功能：**
- 按月份分组显示票据列表
- 每条记录：日期、车次/航班号（高铁🚄/飞机✈️图标）、路线、座次、票价
- 顶部显示总金额汇总
- 底部按钮跳转导出页

### 3.3 导出页

```
┌─────────────────────────────┐
│  ← 返回        导出文件      │
├─────────────────────────────┤
│                             │
│  ╔═════════════════════════╗│
│  ║  ⬇  全部下载到手机       ║│
│  ╚═════════════════════════╝│
│                             │
│  ┌─ 发送到邮箱 ────────────┐│
│  │                         ││
│  │  收件地址:               ││
│  │  ┌─────────────────┐    ││
│  │  │ xxxxx@qq.com    │    ││
│  │  └─────────────────┘    ││
│  │                  [发送] ││
│  └─────────────────────────┘│
│                             │
│  ┌─ 票据图片 (20张) ───────┐│
│  │                         ││
│  │  ┌───┐ ┌───┐ ┌───┐     ││
│  │  │JPG│ │JPG│ │JPG│ ... ││
│  │  └───┘ └───┘ └───┘     ││
│  │                         ││
│  │  [保存到相册]            ││
│  └─────────────────────────┘│
│                             │
│  ┌─ 汇总表 ────────────────┐│
│  │  📊 ticket_summary.csv  ││
│  │     20条记录  12KB      ││
│  │                  [下载] ││
│  └─────────────────────────┘│
│                             │
│  ┌─ 合并打印 ──────────────┐│
│  │  📄 print.pdf           ││
│  │     共6页  2.1MB        ││
│  │                  [下载] ││
│  └─────────────────────────┘│
│                             │
├─────────────────────────────┤
│  首页  │  票列列表  │  导出  │
└─────────────────────────────┘
```

**导出方式：**

| 操作 | 实现方式 |
|------|----------|
| 保存到相册 | `wx.saveImageToPhotosAlbum`，逐张或批量 |
| 下载 CSV/PDF | `wx.cloud.downloadFile` → `wx.openDocument` 预览 |
| 全部下载 | 依次执行：JPG 存相册 → CSV 预览 → PDF 预览，toast 显示进度 |
| 发送邮箱 | 云函数打包 ZIP → SMTP 发送，toast 提示结果 |

## 4. 云函数设计

### 4.1 云函数列表

| 函数名 | 功能 | 超时 | 内存 | 输入 | 输出 |
|--------|------|------|------|------|------|
| `fetchTickets` | IMAP 连接 + 邮件搜索 + 票面解析 + 文件生成 + 上传 | 120s | 512MB | email, code, startDate, endDate, taskId | tickets[] + fileIds |
| `sendEmail` | 从云存储下载 + ZIP 打包 + SMTP 发送 | 60s | 256MB | email, code, taskId, toAddress | 发送结果 |

两个函数共享 `pymupdf-pillow` 公共层。`sendEmail` 仅需标准库（imaplib/smtplib/zipfile），不强制依赖该层。

### 4.2 `fetchTickets` 流程

```python
import os
import fitz                           # 来自公共层
from PIL import Image                # 来自公共层
from sources.imap import ImapSource  # 本地模块
from parsers import get_parser       # 本地模块

def main(event, context):
    email = event['email']
    code = event['code']
    task_id = event['taskId']
    start_date = event.get('startDate')
    end_date = event.get('endDate')

    db = get_db()  # 云数据库引用

    # [1/4] IMAP 连接（日期服务端过滤 + 主题预筛选）
    source = ImapSource(email, code)
    source.connect()
    raw_emails = source.search(start_date, end_date)
    source.disconnect()

    _update_progress(db, task_id, 'connected', f'0/{len(raw_emails)}')

    # [2/4] 逐封解析，流式处理
    all_tickets = []
    jpg_file_ids = []

    for i, raw in enumerate(raw_emails):
        parser = get_parser(raw)
        if not parser:
            continue
        for pdf_bytes, pdf_name, tickets in parser.parse(raw):
            # 立即转 JPG 并上传
            jpg_bytes = _pdf_to_jpg_bytes(pdf_bytes, dpi=150)
            jpg_id = _upload_cloud(jpg_bytes, f"tickets/{task_id}/{pdf_name}.jpg")
            jpg_file_ids.append(jpg_id)

            # PDF 原文也上传（供下载）
            pdf_id = _upload_cloud(pdf_bytes, f"tickets/{task_id}/{pdf_name}")
            for t in tickets:
                all_tickets.append({
                    **asdict(t),
                    'jpgFileId': jpg_id,
                    'pdfFileId': pdf_id,
                })
            del pdf_bytes, jpg_bytes  # 立即释放

        _update_progress(db, task_id, 'parsing', f'{i+1}/{len(raw_emails)}')

    # [3/4] 生成 CSV 和 print.pdf
    csv_id = _generate_csv(all_tickets, task_id)
    print_pdf_id = _generate_print_pdf(jpg_file_ids, all_tickets, task_id)

    # [4/4] 写入数据库
    _save_tickets(db, task_id, all_tickets)

    return {
        'taskId': task_id,
        'tickets': all_tickets,
        'fileIds': {
            'jpgs': jpg_file_ids,
            'csv': csv_id,
            'pdf': print_pdf_id,
        },
    }
```

### 4.3 `sendEmail` 流程

```python
import io
import zipfile
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

def main(event, context):
    email_addr = event['email']
    auth_code = event['code']
    to_address = event['toAddress']
    file_ids = event['fileIds']    # 云存储 fileID 列表

    # 1. 从云存储下载所有文件到临时目录
    files = []
    for fid in file_ids:
        data = download_from_cloud(fid)
        name = get_filename_from_cloud(fid)
        files.append((name, data))

    # 2. 打包为 ZIP（内存中）
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    zip_bytes = zip_buffer.getvalue()

    # 3. SMTP 发送
    msg = MIMEMultipart()
    msg['From'] = email_addr
    msg['To'] = to_address
    msg['Subject'] = 'Qmail-Ticket 票据提取结果'

    part = MIMEBase('application', 'zip')
    part.set_payload(zip_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment', filename='tickets.zip')
    msg.attach(part)

    with smtplib.SMTP_SSL('smtp.qq.com', 465) as server:
        server.login(email_addr, auth_code)
        server.send_message(msg)

    return {'success': True, 'to': to_address}
```

### 4.4 进度更新机制

`fetchTickets` 在关键节点写入云数据库，前端轮询获取进度：

```python
def _update_progress(db, task_id, status, progress):
    db.collection('tasks').doc(task_id).update({
        'data': {
            'status': status,
            'progress': progress,
            'updateTime': db.serverDate(),
        }
    })
```

任务状态流转：`connecting` → `connected` → `parsing` → `generating` → `done`

## 5. 数据模型

### 5.1 云数据库集合：`tasks`

任务级元数据，用于进度跟踪和历史记录：

```json
{
  "_id": "fetch_20260519_001",
  "_openid": "user_openid",
  "_createTime": "2026-05-19T10:00:00Z",
  "status": "done",
  "progress": "15/15",
  "ticketCount": 20,
  "totalAmount": 8560.00,
  "fileIds": {
    "jpgs": ["cloud://xxx/1.jpg", "cloud://xxx/2.jpg"],
    "csv": "cloud://xxx/ticket_summary.csv",
    "pdf": "cloud://xxx/print.pdf"
  }
}
```

### 5.2 云数据库集合：`tickets`

单条票据数据，关联到任务：

```json
{
  "_id": "auto",
  "_openid": "user_openid",
  "_taskId": "fetch_20260519_001",
  "travelDate": "2026-04-28",
  "carrier": "G8888",
  "route": "重庆北-成都东",
  "amount": 154.00,
  "ticketType": "火车",
  "vehicle": "二等座",
  "item": "票价",
  "jpgFileId": "cloud://xxx/2026-04-28-重庆北-成都东.jpg",
  "pdfFileId": "cloud://xxx/2026-04-28-重庆北-成都东.pdf"
}
```

### 5.3 本地 Storage

```json
{
  "email": "your@qq.com",
  "code": "authorization-code",
  "lastToAddress": "xxxxx@qq.com"
}
```

## 6. 权限配置

### 6.1 小程序权限

- `wx.saveImageToPhotosAlbum` — 需要用户授权"保存到相册"
- `wx.openDocument` — 打开文档预览
- `wx.cloud` — 云开发调用

### 6.2 云函数依赖

```
# cloudfunctions/pymupdf-pillow-layer/requirements.txt
# 仅用于构建公共层，不包含在函数代码包中
PyMuPDF>=1.23.0
Pillow>=10.0.0

# cloudfunctions/fetchTickets/requirements.txt
# 无额外依赖，PyMuPDF 和 Pillow 来自公共层

# cloudfunctions/sendEmail/requirements.txt
# 无额外依赖，全部使用标准库
```

## 7. 项目结构

```
miniprogram/
├── app.js                    # 小程序入口
├── app.json                  # 全局配置
├── app.wxss                  # 全局样式
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
├── components/               # 自定义组件
│   └── ticket-card/          # 票据卡片组件
├── utils/
│   └── cloud.js              # 云函数封装
└── images/                   # 图标资源

cloudfunctions/
├── pymupdf-pillow-layer/     # 公共层（PyMuPDF + Pillow）
│   ├── requirements.txt
│   └── build.sh              # 打包脚本
├── fetchTickets/
│   ├── main.py               # 主函数（< 5MB）
│   ├── sources/
│   │   ├── base.py
│   │   └── imap.py           # 从 sources/imap.py 迁移
│   ├── parsers/
│   │   ├── base.py
│   │   ├── train_12306.py    # 从 parsers/train_12306.py 迁移
│   │   └── ctrip.py          # 从 parsers/ctrip.py 迁移
│   └── utils/
│       ├── email_utils.py    # 从 email_utils.py 迁移
│       └── pdf_utils.py      # 从 pdf_utils.py 迁移
└── sendEmail/
    └── main.py               # 主函数（纯标准库，无额外依赖）
```

## 8. 与原项目的关系

### 8.1 可复用的代码

| 模块 | 复用方式 |
|------|----------|
| `sources/imap.py` | 直接迁移到云函数，作为邮件连接模块 |
| `parsers/train_12306.py` | 直接迁移，12306 解析逻辑完全复用 |
| `parsers/ctrip.py` | 直接迁移，携程解析逻辑完全复用 |
| `email_utils.py` | 直接迁移，附件提取逻辑完全复用 |
| `pdf_utils.py` | 直接迁移，PDF 文本提取和转 JPG 完全复用 |
| `models.py` | 直接迁移，数据模型不变 |

### 8.2 需要新写的代码

- 小程序前端（3 个页面 + 组件）
- 云函数胶水代码（连接解析逻辑与云存储/数据库）
- SMTP 发送功能（新增，原项目无此功能）
- 全部下载打包功能（新增）
- 输出器适配（原项目写本地文件，改为上传云存储）

### 8.3 不迁移的部分

- `sources/foxmail.py` — 小程序无法访问本地文件
- `cli.py` — 命令行交互界面
- `config.py` — 配置改为小程序本地 Storage
- `outputs/` — 输出逻辑重写为云存储上传

## 9. 限制与约束

- 云函数默认超时 20 秒，已在函数配置中设为 120 秒（可申请延长至 600 秒）
- 云函数代码包限制 50MB，通过公共层（Layer）解决 PyMuPDF + Pillow 体积问题
- 云存储单文件上传限制 50MB，ZIP 包打包需注意大小
- SMTP 发送附件大小受 QQ邮箱限制（一般 50MB）
- PyMuPDF 公共层需使用 Linux x86_64 版本的 wheel（云函数运行环境）
- 微信小程序 `wx.saveImageToPhotosAlbum` 需要用户授权
- 云函数并发实例数默认 1000，单用户不会触发限制
- 免费额度：云函数 40 万次/月、云存储 5GB、云数据库 2GB，对个人使用完全足够
