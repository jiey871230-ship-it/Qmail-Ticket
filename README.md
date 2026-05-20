# Qmail-Ticket 邮件票据提取工具

从 QQ邮箱/Foxmail 中搜索 12306 火车票和携程机票邮件，自动提取 PDF 附件，解析票面信息，生成 JPG 图片、CSV 汇总表和合并排版 PDF。

## 功能

- **12306 火车票**：自动识别发站/到站、车次、乘车日期、座次、票价
- **携程机票**：自动识别出发/到达城市、航班号、日期、票价；支持 PDF 文本解析和 HTML 回退
- **两种邮件源**：Foxmail 本地邮件、QQ邮箱 IMAP（可扩展 Gmail/Outlook）
- **输出**：JPG 图片（200 DPI）、CSV 汇总表、合并排版 print.pdf

## 安装

```bash
pip install PyMuPDF Pillow
```

## 使用方法

直接运行即可，未提供的参数会交互式提示输入：

### Foxmail 本地邮件（默认）

```bash
python -m qmail_ticket
# 交互式提示：
#   起始日期 (YYYY-MM-DD, 回车跳过): 2026-01-01
#   截止日期 (YYYY-MM-DD, 回车跳过): 2026-12-31
```

### QQ邮箱 IMAP

需要先在 QQ邮箱设置中生成授权码（非登录密码）。

```bash
python -m qmail_ticket --source imap
# 交互式提示：
#   QQ邮箱: your@qq.com
#   授权码: your-auth-code
#   起始日期 (YYYY-MM-DD, 回车跳过):
#   截止日期 (YYYY-MM-DD, 回车跳过):
```

也可以通过命令行参数一次性传入：

```bash
python -m qmail_ticket --source imap --email your@qq.com --code 授权码 --start 2026-01-01 --end 2026-12-31
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--source` | 邮件源：`foxmail`（默认）或 `imap` |
| `--email` | 邮箱地址（不填则交互提示） |
| `--code` | 授权码（不填则交互提示） |
| `--start` | 起始日期，格式 YYYY-MM-DD（不填则交互提示） |
| `--end` | 截止日期，格式 YYYY-MM-DD（不填则交互提示） |

## 输出文件

运行后在脚本所在目录生成：

| 文件 | 说明 |
|------|------|
| `{日期}-{出发}-{到达}.jpg` | 火车票 JPG 图片 |
| `{日期}-{出发}-{到达}-机票.jpg` | 机票 JPG 图片 |
| `ticket_summary.csv` | CSV 汇总表 |
| `print.pdf` | 合并排版 PDF（火车票每页 8 张，机票每页 4 张） |

## 项目结构

```
qmail_ticket/
├── __init__.py
├── __main__.py          # python -m 入口
├── cli.py               # CLI 入口
├── models.py            # Ticket + RawEmail 数据类
├── email_utils.py       # 邮件附件提取
├── pdf_utils.py         # PDF 文本/图片工具
├── sources/             # 邮件源（可扩展）
│   ├── base.py          # MailSource 抽象基类
│   ├── foxmail.py       # Foxmail 本地邮件源
│   └── imap.py          # IMAP 通用邮件源
├── parsers/             # 票面解析器（可扩展）
│   ├── base.py          # TicketParser 抽象基类
│   ├── train_12306.py   # 12306 火车票解析
│   └── ctrip.py         # 携程机票解析
└── outputs/             # 输出器（可扩展）
    ├── base.py          # OutputWriter 抽象基类
    ├── jpg_out.py       # PDF→JPG 转换
    ├── csv_out.py       # CSV 汇总表
    └── print_pdf.py     # 合并排版 PDF
```

## 扩展开发

### 新增邮件源

在 `sources/` 目录创建新文件，实现 `MailSource` 接口：

```python
from qmail_ticket.sources.base import MailSource

class GmailSource(MailSource):
    def connect(self, **kwargs): ...
    def search(self, start_date=None, end_date=None): ...
    def disconnect(self): ...
```

然后在 `sources/__init__.py` 的 `get_source()` 中注册。

### 新增票型

在 `parsers/` 目录创建新文件，实现 `TicketParser` 接口：

```python
from qmail_ticket.parsers.base import TicketParser

class HotelParser(TicketParser):
    def can_parse(self, raw_email): ...
    def parse(self, raw_email): ...
```

然后在 `parsers/__init__.py` 的 `PARSERS` 列表中注册。

### 新增输出格式

在 `outputs/` 目录创建新文件，实现 `OutputWriter` 接口：

```python
from qmail_ticket.outputs.base import OutputWriter

class ExcelWriter(OutputWriter):
    def write(self, tickets, context): ...
```

然后在 `outputs/__init__.py` 的 `WRITERS` 列表中注册。

## 依赖

- Python 3.10+
- [PyMuPDF](https://pymupdf.readthedocs.io/) (fitz) — PDF 解析和转 JPG
- [Pillow](https://pillow.readthedocs.io/) — 图片处理（print.pdf 排版）
- Python 标准库：imaplib、email、csv、zipfile、argparse

---

## 微信小程序版

基于微信云开发的移动端版本，功能与 CLI 版一致。

### 项目结构

```
miniprogram/                  # 小程序前端
├── app.js / app.json / app.wxss
├── pages/
│   ├── index/                # 首页（提取配置）
│   ├── tickets/              # 票据列表
│   └── export/               # 导出页
├── components/ticket-card/   # 票据卡片组件
└── utils/cloud.js            # 云函数封装

cloudfunctions/               # 云函数（Python）
├── pymupdf-pillow-layer/     # PyMuPDF + Pillow 公共层
├── fetchTickets/             # 邮件提取 + 解析
└── sendEmail/                # ZIP 打包 + SMTP 发送
```

### 部署步骤

1. 在微信开发者工具中创建云开发项目
2. 运行 `cloudfunctions/pymupdf-pillow-layer/build.sh` 构建公共层（需 Linux 环境）
3. 在云开发控制台上传 `pymupdf-pillow-layer.zip` 作为公共层
4. 上传 `fetchTickets` 和 `sendEmail` 云函数
5. 在 `miniprogram/app.js` 中替换 `env: 'your-env-id'` 为实际云环境 ID
6. 在云开发控制台创建 `tasks` 和 `tickets` 两个数据库集合
7. 编译运行小程序

### 注意事项

- `fetchTickets` 函数超时设为 120 秒，邮件量大时可能需要申请延长
- 公共层需在 Linux x86_64 环境构建（使用 Docker 或 WSL）
- 免费额度：云函数 40 万次/月、云存储 5GB、云数据库 2GB
