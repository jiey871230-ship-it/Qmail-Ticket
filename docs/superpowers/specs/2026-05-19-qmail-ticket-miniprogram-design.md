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

| 函数名 | 功能 | 输入 | 输出 |
|--------|------|------|------|
| `fetchTickets` | 连接邮箱、搜索邮件、解析票面 | email, code, startDate, endDate | tickets[] + 文件上传 |
| `exportAll` | 打包所有文件为 ZIP | taskId | cloudFileURL |
| `sendEmail` | ZIP 发送到指定邮箱 | taskId, toAddress | 发送结果 |

### 4.2 `fetchTickets` 流程

```python
def main(event, context):
    email = event['email']
    code = event['code']
    start_date = event.get('startDate')
    end_date = event.get('endDate')

    # 1. IMAP 连接（复用 sources/imap.py 逻辑）
    source = ImapSource(email, code)
    source.connect()
    raw_emails = source.search(start_date, end_date)
    source.disconnect()

    # 2. 解析票面（复用 parsers/ 逻辑）
    all_tickets = []
    pdf_data_list = []
    for raw in raw_emails:
        parser = get_parser(raw)
        if parser:
            results = parser.parse(raw)
            for pdf_bytes, pdf_name, tickets in results:
                all_tickets.extend(tickets)
                pdf_data_list.append((pdf_bytes, pdf_name))

    # 3. 生成 JPG/CSV/PDF，上传到云存储
    # 4. 票据元数据写入云数据库
    # 5. 返回结果
    return {
        'tickets': [asdict(t) for t in all_tickets],
        'fileIds': {
            'jpgs': [...],      # 云存储 fileID 列表
            'csv': 'fileID',
            'pdf': 'fileID',
        }
    }
```

### 4.3 `sendEmail` 流程

```python
def main(event, context):
    to_address = event['toAddress']
    file_ids = event['fileIds']  # 云存储 fileID 列表

    # 1. 从云存储下载所有文件
    # 2. 打包为 ZIP
    # 3. 通过 SMTP 发送（复用用户的 QQ邮箱配置）
    #    SMTP: smtp.qq.com:465, SSL
    #    使用同一个 email + authorization code
    # 4. 返回发送结果
```

## 5. 数据模型

### 5.1 云数据库集合：`tickets`

```json
{
  "_id": "auto",
  "_taskId": "fetch_20260519_001",
  "_createTime": "2026-05-19T10:00:00Z",
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

### 5.2 本地 Storage

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
# requirements.txt
PyMuPDF>=1.23.0
Pillow>=10.0.0
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
├── fetchTickets/
│   ├── main.py               # 主函数
│   ├── requirements.txt
│   └── parsers/              # 从 qmail_ticket/parsers/ 迁移
│       ├── base.py
│       ├── train_12306.py
│       └── ctrip.py
├── exportAll/
│   ├── main.py
│   └── requirements.txt
└── sendEmail/
    ├── main.py
    └── requirements.txt
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

- 云函数默认超时 20 秒，邮件量大时需申请延长（最长 600 秒）
- 云存储单文件上传限制 50MB，ZIP 包打包需注意大小
- SMTP 发送附件大小受 QQ邮箱限制（一般 50MB）
- PyMuPDF 在云函数环境中需要使用 Linux 版本的 wheel
- 微信小程序 `wx.saveImageToPhotosAlbum` 需要用户授权
