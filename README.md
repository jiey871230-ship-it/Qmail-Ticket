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

### Foxmail 本地邮件（默认）

```bash
python -m qmail_ticket --source foxmail
python -m qmail_ticket --source foxmail --start 2026-01-01 --end 2026-12-31
```

### QQ邮箱 IMAP

需要先在 QQ邮箱设置中生成授权码（非登录密码）。

```bash
python -m qmail_ticket --source imap --email your@qq.com --code 授权码
python -m qmail_ticket --source imap --email your@qq.com --code 授权码 --start 2026-01-01
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--source` | 邮件源：`foxmail`（默认）或 `imap` |
| `--email` | 邮箱地址（imap 源必需） |
| `--code` | 授权码（imap 源必需） |
| `--start` | 起始日期，格式 YYYY-MM-DD |
| `--end` | 截止日期，格式 YYYY-MM-DD |

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
