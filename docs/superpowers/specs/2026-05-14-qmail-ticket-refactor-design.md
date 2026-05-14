# Qmail-Ticket 重构设计规格

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 2 个单文件（~1100 行）重构为 15 个模块的插件式架构，支持新邮件源、新票型、新输出格式的扩展。

**架构：** 三层插件设计 — sources/（邮件源）、parsers/（票面解析器）、outputs/（输出器），通过 models.py 的数据类和 context 字典传递数据。

**技术栈：** Python 3.10+、PyMuPDF（fitz）、Pillow、imaplib（标准库）

---

## 1. 现状

### 1.1 文件

- `ticket.py`（800 行）— Foxmail 本地版：配置、日期工具、邮件搜索（grep）、附件提取、PDF 解析（12306/携程）、PDF→JPG、CSV 汇总、PDF 合并排版、主流程
- `ticket_imap.py`（327 行）— IMAP 版：IMAP 连接/搜索、邮件处理，导入 ticket.py 的 8 个函数

### 1.2 问题

1. `ticket.py` 是单文件大杂烩，职责混杂
2. 两个文件主流程几乎一样（搜索→解析→JPG→CSV→print.pdf），大量重复
3. `ticket_imap.py` 紧耦合 ticket.py（直接导入内部函数）
4. 无测试、无模块化、扩展困难

---

## 2. 目标架构

```
qmail_ticket/
├── __init__.py
├── cli.py                 # CLI 入口
├── models.py              # Ticket + RawEmail 数据类
├── email_utils.py         # 邮件附件提取
├── pdf_utils.py           # PDF 文本/图片工具
├── sources/
│   ├── __init__.py        # get_source() 工厂
│   ├── base.py            # MailSource ABC
│   ├── foxmail.py         # Foxmail 本地
│   └── imap.py            # IMAP 通用
├── parsers/
│   ├── __init__.py        # get_parser() 工厂
│   ├── base.py            # TicketParser ABC
│   ├── train_12306.py     # 12306 火车票
│   └── ctrip.py           # 携程机票
└── outputs/
    ├── __init__.py         # WRITERS 列表
    ├── base.py             # OutputWriter ABC
    ├── csv_out.py          # CSV 汇总
    ├── jpg_out.py          # PDF→JPG
    └── print_pdf.py        # 合并排版 PDF
```

共 15 个文件，平均每个 ~60-80 行。

---

## 3. 数据模型

### 3.1 models.py

```python
from dataclasses import dataclass

@dataclass
class Ticket:
    travel_date: str       # "2026-04-28"
    carrier: str           # 车次 "G8888" 或航班号 "ZH8848"
    route: str             # "成都东-重庆北" 或 "成都-北京"
    amount: float          # 票价
    ticket_type: str       # "火车" / "飞机"
    vehicle: str           # "二等座" / "飞机" / "硬卧"
    item: str              # "票价" / "机票" / "退票费"

@dataclass
class RawEmail:
    source: str            # "foxmail" / "imap"
    uid: str | None        # IMAP UID，本地为 None
    raw_bytes: bytes       # 原始邮件 bytes
    subject: str           # 解码后的主题
```

### 3.2 Context 字典

输出器之间通过 context 传递中间产物：

```python
context = {
    'output_dir': str,                    # 输出目录
    'pdf_data_list': [(bytes, str)],      # (pdf_bytes, pdf_name) 列表
    'jpg_paths': [str],                   # JPG 文件路径（由 jpg_out 填充）
}
```

---

## 4. 邮件源（sources/）

### 4.1 base.py — MailSource ABC

```python
from abc import ABC, abstractmethod
from qmail_ticket.models import RawEmail

class MailSource(ABC):
    @abstractmethod
    def connect(self, **kwargs) -> None: ...

    @abstractmethod
    def search(self, start_date=None, end_date=None) -> list[RawEmail]: ...

    @abstractmethod
    def disconnect(self) -> None: ...
```

### 4.2 foxmail.py — Foxmail 本地邮件源

- `connect()`: 无操作（本地文件系统）
- `search()`: 从 ticket.py 迁移 `find_all_target_mails()` + `_filter()` + `parse_email_date()`
- `disconnect()`: 无操作
- 返回 `RawEmail(source="foxmail", uid=None, raw_bytes=文件内容, subject=从文件解析)`

### 4.3 imap.py — IMAP 通用邮件源

- 构造函数接收 `server`、`port`、`email`、`auth_code`
- `connect()`: 从 ticket_imap.py 迁移 `connect_imap()`
- `search()`: 从 ticket_imap.py 迁移 `search_target_uids()`，返回 `list[RawEmail]`
- `disconnect()`: 调用 `conn.logout()`
- 保留 `decode_subject_from_header()` 作为私有函数
- 默认配置：QQ邮箱 `imap.qq.com:993`

### 4.4 __init__.py — 工厂

```python
def get_source(name: str, **kwargs) -> MailSource:
    if name == 'foxmail':
        return FoxmailSource()
    elif name == 'imap':
        return ImapSource(**kwargs)
    raise ValueError(f"未知邮件源: {name}")
```

---

## 5. 解析器（parsers/）

### 5.1 base.py — TicketParser ABC

```python
from abc import ABC, abstractmethod
from qmail_ticket.models import RawEmail, Ticket

class TicketParser(ABC):
    @abstractmethod
    def can_parse(self, raw_email: RawEmail) -> bool: ...

    @abstractmethod
    def parse(self, raw_email: RawEmail) -> list[tuple[bytes, str, list[Ticket]]]:
        """返回 [(pdf_bytes, pdf_name, [ticket, ...]), ...]"""
```

### 5.2 train_12306.py — 12306 火车票解析器

- `can_parse()`: 主题包含 "网上购票系统"
- `parse()`: 从 ticket.py 迁移 `extract_12306_pdf()` + `parse_12306_pdf_text()`
- 命名规则：`{date}-{station}.pdf`

### 5.3 ctrip.py — 携程机票解析器

- `can_parse()`: 主题包含 "携程"
- `parse()`: 从 ticket.py 迁移 `extract_ctrip_pdfs()` + `parse_ctrip_pdf_text()` + `_parse_ctrip_html()` 回退
- 命名规则：`{date}-{station}-机票.pdf`

### 5.4 __init__.py — 自动匹配

```python
PARSERS = [Train12306Parser(), CtripParser()]

def get_parser(raw_email: RawEmail) -> TicketParser | None:
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
```

---

## 6. 输出器（outputs/）

### 6.1 base.py — OutputWriter ABC

```python
from abc import ABC, abstractmethod
from qmail_ticket.models import Ticket

class OutputWriter(ABC):
    @abstractmethod
    def write(self, tickets: list[Ticket], context: dict) -> None: ...
```

### 6.2 jpg_out.py — PDF→JPG

- 遍历 `context['pdf_data_list']`，调用 `pdf_utils.pdf_to_jpg()`
- 将生成的 jpg_paths 写回 `context['jpg_paths']`
- 从 ticket.py 迁移 `pdf_to_jpg()` 逻辑

### 6.3 csv_out.py — CSV 汇总表

- 从 ticket.py 迁移 `write_summary()` 逻辑
- 使用 `context['jpg_paths']` 做验证匹配
- 输出 `ticket_summary.csv`

### 6.4 print_pdf.py — 合并排版 PDF

- 从 ticket.py 迁移 `create_print_pdf()` 逻辑
- 使用 `context['jpg_paths']` 读取 JPG
- 输出 `print.pdf`

### 6.5 __init__.py

```python
WRITERS = [JpgWriter(), CsvWriter(), PrintPdfWriter()]
```

输出顺序：JPG → CSV → print PDF（CSV 依赖 JPG 验证，print PDF 依赖 JPG 文件）。

---

## 7. 公共工具

### 7.1 email_utils.py

从 ticket.py 迁移：
- `extract_12306_pdf(msg)` — 从 12306 邮件提取 ZIP→PDF
- `extract_ctrip_pdfs(msg)` — 从携程邮件提取 PDF 附件 + HTML 正文

### 7.2 pdf_utils.py

从 ticket.py 迁移：
- `pdf_to_text(pdf_bytes)` — PDF 文本提取
- `pdf_to_jpg(pdf_bytes, jpg_path, dpi=200)` — PDF 转 JPG

---

## 8. CLI 入口

### 8.1 cli.py

```python
def main():
    args = parse_args()
    
    # 1. 选择邮件源
    source = get_source(args.source, email=args.email, code=args.code)
    
    # 2. 搜索邮件
    source.connect()
    raw_emails = source.search(start_date, end_date)
    source.disconnect()
    
    # 3. 解析票面
    all_tickets, pdf_data_list = [], []
    for raw in raw_emails:
        parser = get_parser(raw)
        if not parser: continue
        results = parser.parse(raw)
        for pdf_bytes, pdf_name, tickets in results:
            all_tickets.extend(tickets)
            pdf_data_list.append((pdf_bytes, pdf_name))
    
    # 4. 输出
    context = {'output_dir': OUTPUT_DIR, 'pdf_data_list': pdf_data_list}
    for writer in WRITERS:
        writer.write(all_tickets, context)
```

### 8.2 CLI 参数

```
python -m qmail_ticket --source foxmail [--start DATE] [--end DATE]
python -m qmail_ticket --source imap --email user@qq.com --code AUTH [--start DATE] [--end DATE]
```

---

## 9. 配置常量

集中在 `cli.py` 或单独的 `config.py`：

```python
FOXMAIL_PROFILES = os.path.expanduser("~/Library/Containers/com.tencent.Foxmail/...")
IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
JPG_DPI = 200
SUBJECT_12306 = "网上购票系统"    # 解码后的主题关键词
SUBJECT_CTRIP = "携程"
```

Foxmail 的 Base64 编码主题常量（`SUBJECT_12306`、`SUBJECT_CTRIP`）迁移到 foxmail.py 中用于 grep 搜索。

---

## 10. 扩展方式

| 扩展方向 | 操作 |
|---------|------|
| 新邮件源（Gmail） | `sources/gmail.py` 实现 `MailSource`，`__init__.py` 注册 |
| 新票型（酒店） | `parsers/hotel.py` 实现 `TicketParser`，`__init__.py` 注册 |
| 新输出（Excel） | `outputs/excel_out.py` 实现 `OutputWriter`，`__init__.py` 注册 |

---

## 11. 迁移策略

1. 先建目录结构和接口（models、base 类）
2. 逐个迁移：email_utils → pdf_utils → sources → parsers → outputs → cli
3. 每迁移一个模块后验证功能不变
4. 旧文件保留到全部迁移完成后删除

---

## 12. 依赖

- PyMuPDF（fitz）— PDF 解析和转 JPG
- Pillow — 图片处理（print.pdf 排版）
- Python 标准库：imaplib、email、csv、zipfile、argparse、dataclasses
