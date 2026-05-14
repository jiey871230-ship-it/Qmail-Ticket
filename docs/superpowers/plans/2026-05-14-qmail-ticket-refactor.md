# Qmail-Ticket 重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 ticket.py（800 行）和 ticket_imap.py（327 行）重构为 qmail_ticket/ 包的 15 个模块插件式架构。

**架构：** 三层插件 — sources/（邮件源）、parsers/（票面解析器）、outputs/（输出器），通过 dataclass 和 context 字典传递数据。

**技术栈：** Python 3.10+、PyMuPDF（fitz）、Pillow、imaplib（标准库）

---

## 文件清单

| 文件 | 职责 | 来源 |
|------|------|------|
| `qmail_ticket/__init__.py` | 包标识 | 新建 |
| `qmail_ticket/models.py` | Ticket + RawEmail dataclass | 新建 |
| `qmail_ticket/email_utils.py` | 邮件附件提取 | ticket.py:113-169 |
| `qmail_ticket/pdf_utils.py` | PDF 文本提取/转 JPG | ticket.py:556-577 |
| `qmail_ticket/sources/__init__.py` | get_source() 工厂 | 新建 |
| `qmail_ticket/sources/base.py` | MailSource ABC | 新建 |
| `qmail_ticket/sources/foxmail.py` | Foxmail 本地邮件源 | ticket.py:41-108 |
| `qmail_ticket/sources/imap.py` | IMAP 通用邮件源 | ticket_imap.py:43-147 |
| `qmail_ticket/parsers/__init__.py` | get_parser() 工厂 | 新建 |
| `qmail_ticket/parsers/base.py` | TicketParser ABC | 新建 |
| `qmail_ticket/parsers/train_12306.py` | 12306 火车票解析 | ticket.py:174-333, 463-483 |
| `qmail_ticket/parsers/ctrip.py` | 携程机票解析 | ticket.py:336-553, 486-526 |
| `qmail_ticket/outputs/__init__.py` | WRITERS 列表 | 新建 |
| `qmail_ticket/outputs/base.py` | OutputWriter ABC | 新建 |
| `qmail_ticket/outputs/jpg_out.py` | PDF→JPG 输出 | ticket.py:572-577, 768-779 |
| `qmail_ticket/outputs/csv_out.py` | CSV 汇总表 | ticket.py:582-619 |
| `qmail_ticket/outputs/print_pdf.py` | 合并排版 PDF | ticket.py:624-704 |
| `qmail_ticket/cli.py` | CLI 入口 | ticket.py:709-800 + ticket_imap.py:220-327 |
| `qmail_ticket/__main__.py` | python -m 入口 | 新建 |

---

### 任务 1：包结构 + 数据模型

**文件：**
- 创建：`qmail_ticket/__init__.py`
- 创建：`qmail_ticket/models.py`

- [ ] **步骤 1：创建包目录**

```bash
mkdir -p qmail_ticket/sources qmail_ticket/parsers qmail_ticket/outputs
```

- [ ] **步骤 2：创建 `qmail_ticket/__init__.py`**

```python
"""Qmail-Ticket: 邮件票据提取工具"""
```

- [ ] **步骤 3：创建 `qmail_ticket/models.py`**

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
    source: str            # "foxmail" / "imap"
    uid: bytes | None      # IMAP UID，本地为 None
    raw_bytes: bytes       # 原始邮件 bytes
    subject: str           # 解码后的主题
```

- [ ] **步骤 4：验证导入**

```bash
cd /Users/yangjie/Desktop/Qmail-Ticket && python3 -c "from qmail_ticket.models import Ticket, RawEmail; print('OK')"
```

预期：`OK`

- [ ] **步骤 5：Commit**

```bash
git add qmail_ticket/
git commit -m "feat: 创建包结构和数据模型 (Ticket, RawEmail)"
```

---

### 任务 2：公共工具 — email_utils + pdf_utils

**文件：**
- 创建：`qmail_ticket/email_utils.py`
- 创建：`qmail_ticket/pdf_utils.py`

- [ ] **步骤 1：创建 `qmail_ticket/email_utils.py`**

从 ticket.py:113-169 迁移邮件附件提取函数：

```python
"""邮件附件提取工具"""
import base64
import io
import quopri
import zipfile
from email.message import EmailMessage


def extract_12306_pdf(msg: EmailMessage) -> bytes | None:
    """从 12306 邮件解压 ZIP 中的 PDF。返回 pdf_bytes 或 None。"""
    for part in msg.walk():
        cd = part.get_content_disposition()
        fn = part.get_filename()
        if (cd == 'attachment' or part.get_content_type() == 'application/octet-stream') \
                and fn and fn.lower().endswith('.zip'):
            data = part.get_payload(decode=True)
            if data is None and isinstance(part.get_payload(), str):
                try:
                    data = base64.b64decode(part.get_payload())
                except Exception:
                    pass
            if data:
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as zf:
                        for name in zf.namelist():
                            if name.lower().endswith('.pdf'):
                                return zf.read(name)
                except Exception:
                    pass
    return None


def extract_ctrip_pdfs(msg: EmailMessage) -> tuple[list[bytes], str | None]:
    """从携程邮件提取所有 PDF 附件和 HTML 正文。返回 ([pdf_bytes], html_text)。"""
    pdf_list = []
    html_text = None

    for part in msg.walk():
        ct = part.get_content_type()
        cd = part.get_content_disposition()
        fn = part.get_filename()

        if (cd == 'attachment' or ct in ('application/pdf', 'application/octet-stream')) \
                and fn and fn.lower().endswith('.pdf'):
            data = part.get_payload(decode=True)
            if data is None and isinstance(part.get_payload(), str):
                try:
                    data = base64.b64decode(part.get_payload())
                except Exception:
                    pass
            if data and len(data) > 100:
                pdf_list.append(data)

        if ct == 'text/html' and cd != 'attachment':
            payload = part.get_payload(decode=True)
            if payload:
                cs = part.get_content_charset() or 'utf-8'
                try:
                    html_text = payload.decode(cs, errors='replace')
                except Exception:
                    html_text = payload.decode('utf-8', errors='replace')

    return pdf_list, html_text
```

- [ ] **步骤 2：创建 `qmail_ticket/pdf_utils.py`**

从 ticket.py:556-577 迁移 PDF 工具函数：

```python
"""PDF 文本提取和图片转换工具"""
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


def pdf_to_jpg(pdf_bytes: bytes, jpg_path: str, dpi: int = 200) -> None:
    """将 PDF 第一页转为 JPG。"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    pix.save(jpg_path)
    doc.close()
```

- [ ] **步骤 3：验证导入**

```bash
python3 -c "from qmail_ticket.email_utils import extract_12306_pdf, extract_ctrip_pdfs; from qmail_ticket.pdf_utils import pdf_to_text, pdf_to_jpg; print('OK')"
```

预期：`OK`

- [ ] **步骤 4：Commit**

```bash
git add qmail_ticket/email_utils.py qmail_ticket/pdf_utils.py
git commit -m "feat: 提取邮件附件和PDF工具函数"
```

---

### 任务 3：邮件源接口 + Foxmail 源

**文件：**
- 创建：`qmail_ticket/sources/__init__.py`
- 创建：`qmail_ticket/sources/base.py`
- 创建：`qmail_ticket/sources/foxmail.py`

- [ ] **步骤 1：创建 `qmail_ticket/sources/base.py`**

```python
"""邮件源抽象基类"""
from abc import ABC, abstractmethod

from qmail_ticket.models import RawEmail


class MailSource(ABC):
    @abstractmethod
    def connect(self, **kwargs) -> None:
        """建立连接（本地源可为空操作）"""

    @abstractmethod
    def search(self, start_date=None, end_date=None) -> list[RawEmail]:
        """搜索目标邮件，返回原始邮件列表"""

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接（本地源可为空操作）"""
```

- [ ] **步骤 2：创建 `qmail_ticket/sources/foxmail.py`**

从 ticket.py:27-36, 41-108 迁移。Foxmail Base64 编码主题常量、`parse_email_date()`、`_filter()`、`find_all_target_mails()` 改写为类方法：

```python
"""Foxmail 本地邮件源"""
import glob
import os
import re
import subprocess
from datetime import datetime

from qmail_ticket.models import RawEmail
from qmail_ticket.sources.base import MailSource

FOXMAIL_PROFILES = os.path.expanduser(
    "~/Library/Containers/com.tencent.Foxmail/Data/Library/Foxmail/Profiles"
)

# Base64 编码的邮件主题（用于 grep 搜索）
_SUBJECT_12306_B64 = "zfjJz7m6xrHPtc2zLbXn19O3osaxzajWqg=="   # 网上购票系统-电子发票通知
_SUBJECT_CTRIP_B64 = "5pC656iLOiDnlLXlrZDmiqXplIDlh63or4E="     # 携程: 电子报销凭证


def _parse_email_date(filepath: str) -> datetime | None:
    """从邮件文件头部解析 Date 字段。"""
    try:
        with open(filepath, 'rb') as f:
            head = f.read(5120).decode('utf-8', errors='replace')
    except Exception:
        return None
    m = re.search(r'^Date:\s*(.+)$', head, re.MULTILINE | re.IGNORECASE)
    if not m:
        return None
    s = re.sub(r'\s*\([^)]*\)\s*$', '', m.group(1).strip().rstrip('\r'))
    for fmt in ('%a, %d %b %Y %H:%M:%S %z', '%d %b %Y %H:%M:%S %z',
                '%a, %d %b %Y %H:%M:%S', '%d %b %Y %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _filter_by_date(files: list[str], start_date: datetime | None,
                    end_date: datetime | None, label: str) -> list[str]:
    """按日期范围过滤邮件文件。"""
    out = []
    for fp in files:
        d = _parse_email_date(fp)
        if d is None:
            out.append(fp)
            continue
        d = d.replace(tzinfo=None)
        if start_date and d < start_date:
            continue
        if end_date and d > end_date:
            continue
        out.append(fp)
    print(f"  日期筛选 ({label}): {len(out)}/{len(files)} 封")
    return out


class FoxmailSource(MailSource):
    """Foxmail 本地邮件源"""

    def connect(self, **kwargs) -> None:
        pass  # 本地文件系统，无需连接

    def search(self, start_date=None, end_date=None) -> list[RawEmail]:
        """搜索 Foxmail 本地邮件文件。"""
        train_files, flight_files = [], []

        for profile_dir in glob.glob(os.path.join(FOXMAIL_PROFILES, "*")):
            mail_root = os.path.join(profile_dir, "Mail")
            if not os.path.isdir(mail_root):
                continue

            for pattern, lst in [
                (_SUBJECT_12306_B64, train_files),
                (_SUBJECT_CTRIP_B64, flight_files),
            ]:
                try:
                    r = subprocess.run(
                        ["grep", "-rl", pattern, mail_root, "--include=*.mail"],
                        capture_output=True, text=True, timeout=30
                    )
                    for line in r.stdout.strip().split("\n"):
                        if line:
                            lst.append(line)
                except Exception as e:
                    print(f"  搜索出错: {e}", file=__import__('sys').stderr)

        if start_date or end_date:
            train_files = _filter_by_date(train_files, start_date, end_date, "12306")
            flight_files = _filter_by_date(flight_files, start_date, end_date, "携程")

        # 转为 RawEmail
        results = []
        for filepath in train_files + flight_files:
            try:
                with open(filepath, 'rb') as f:
                    raw_bytes = f.read()
                # 从文件头部提取主题
                head = raw_bytes[:5120].decode('utf-8', errors='replace')
                m = re.search(r'^Subject:\s*(.+)$', head, re.MULTILINE | re.IGNORECASE)
                subject = m.group(1).strip() if m else ''
                results.append(RawEmail(
                    source='foxmail', uid=None,
                    raw_bytes=raw_bytes, subject=subject
                ))
            except Exception:
                continue

        return results

    def disconnect(self) -> None:
        pass
```

- [ ] **步骤 3：创建 `qmail_ticket/sources/__init__.py`**

```python
"""邮件源工厂"""
from qmail_ticket.sources.base import MailSource
from qmail_ticket.sources.foxmail import FoxmailSource


def get_source(name: str, **kwargs) -> MailSource:
    """根据名称获取邮件源实例。"""
    if name == 'foxmail':
        return FoxmailSource()
    if name == 'imap':
        from qmail_ticket.sources.imap import ImapSource
        return ImapSource(**kwargs)
    raise ValueError(f"未知邮件源: {name}")
```

- [ ] **步骤 4：验证导入**

```bash
python3 -c "from qmail_ticket.sources import get_source; s = get_source('foxmail'); print(type(s).__name__)"
```

预期：`FoxmailSource`

- [ ] **步骤 5：Commit**

```bash
git add qmail_ticket/sources/
git commit -m "feat: 添加邮件源接口和 Foxmail 本地源"
```

---

### 任务 4：IMAP 邮件源

**文件：**
- 创建：`qmail_ticket/sources/imap.py`

- [ ] **步骤 1：创建 `qmail_ticket/sources/imap.py`**

从 ticket_imap.py:14-49, 54-147 迁移。包含 IMAP 连接、主题解码、搜索逻辑：

```python
"""IMAP 通用邮件源（QQ邮箱/Gmail/Outlook）"""
import email.header
import imaplib
import re
from datetime import timedelta

from qmail_ticket.models import RawEmail
from qmail_ticket.sources.base import MailSource

# 搜索关键词（解码后的主题）
_SUBJECT_12306 = "网上购票系统"
_SUBJECT_CTRIP = "携程"


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
        print(f"  登录成功: {self._email}")

    def search(self, start_date=None, end_date=None) -> list[RawEmail]:
        self._conn.select('INBOX')

        criteria = 'ALL'
        if start_date:
            criteria = f'SINCE {start_date.strftime("%d-%b-%Y")}'
        if end_date:
            criteria += f' BEFORE {(end_date + timedelta(days=1)).strftime("%d-%b-%Y")}'

        _, data = self._conn.uid('SEARCH', criteria)
        all_uids = data[0].split() if data[0] else []

        if not all_uids:
            return []

        print(f"  扫描 {len(all_uids)} 封邮件的主题...")
        results = []

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
            if _SUBJECT_12306 in decoded or _SUBJECT_CTRIP in decoded:
                # 下载完整邮件
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

- [ ] **步骤 2：验证导入**

```bash
python3 -c "from qmail_ticket.sources.imap import ImapSource; print('OK')"
```

预期：`OK`

- [ ] **步骤 3：Commit**

```bash
git add qmail_ticket/sources/imap.py
git commit -m "feat: 添加 IMAP 通用邮件源"
```

---

### 任务 5：解析器接口 + 12306 解析器

**文件：**
- 创建：`qmail_ticket/parsers/__init__.py`
- 创建：`qmail_ticket/parsers/base.py`
- 创建：`qmail_ticket/parsers/train_12306.py`

- [ ] **步骤 1：创建 `qmail_ticket/parsers/base.py`**

```python
"""票面解析器抽象基类"""
from abc import ABC, abstractmethod

from qmail_ticket.models import RawEmail, Ticket


class TicketParser(ABC):
    @abstractmethod
    def can_parse(self, raw_email: RawEmail) -> bool:
        """判断是否能解析此邮件"""

    @abstractmethod
    def parse(self, raw_email: RawEmail) -> list[tuple[bytes, str, list[Ticket]]]:
        """解析邮件，返回 [(pdf_bytes, pdf_name, [ticket, ...]), ...]"""
```

- [ ] **步骤 2：创建 `qmail_ticket/parsers/train_12306.py`**

从 ticket.py:174-333, 463-483 迁移。`parse_12306_pdf_text()` 的全部逻辑（拼音匹配、车次/日期/座次/票价提取）移入 `parse()` 方法：

```python
"""12306 火车票解析器"""
import email.policy
import re
from email import message_from_bytes

from qmail_ticket.models import RawEmail, Ticket
from qmail_ticket.email_utils import extract_12306_pdf
from qmail_ticket.pdf_utils import pdf_to_text
from qmail_ticket.parsers.base import TicketParser


class Train12306Parser(TicketParser):
    """12306 火车票解析器"""

    def can_parse(self, raw_email: RawEmail) -> bool:
        return "网上购票系统" in raw_email.subject

    def parse(self, raw_email: RawEmail) -> list[tuple[bytes, str, list[Ticket]]]:
        msg = message_from_bytes(raw_email.raw_bytes, policy=email.policy.default)
        pdf_data = extract_12306_pdf(msg)
        if not pdf_data:
            return []

        text = pdf_to_text(pdf_data)
        if not text:
            return []

        tickets = _parse_12306_text(text, pdf_data)
        if not tickets:
            return []

        results = []
        for t in tickets:
            safe_date = t.travel_date.replace('/', '-')
            safe_station = t.route.replace('/', '-').replace('\\', '-')
            pdf_name = f"{safe_date}-{safe_station}.pdf"
            results.append((pdf_data, pdf_name, [t]))
        return results


# === 以下为从 ticket.py 迁移的解析逻辑 ===

def _parse_12306_text(text: str, pdf_bytes: bytes | None = None) -> list[Ticket]:
    """从 12306 PDF 文本提取车票信息。"""
    tickets = []
    lines = text.strip().split('\n')
    stations_cn = [l.strip() for l in lines if re.match(r'^[一-鿿]+站$', l.strip())]

    from_station, to_station = '', ''

    # 方法1: PDF 块级拼音 x 坐标定位
    if pdf_bytes and len(stations_cn) >= 2:
        from_station, to_station = _match_by_pinyin_blocks(pdf_bytes, stations_cn)

    # 方法2: 纯文本拼音行定位
    if not from_station and len(stations_cn) >= 2:
        from_station, to_station = _match_by_pinyin_lines(lines, stations_cn)

    # 方法3: 纯文本顺序回退
    if not from_station and len(stations_cn) >= 2:
        from_station, to_station = stations_cn[0], stations_cn[1]

    # 车次
    trains = re.findall(r'\b([GCDKZT]\d{2,5})\b', text, re.IGNORECASE)
    train = trains[0].upper() if trains else ''

    # 乘车日期
    travel_date = _extract_travel_date(text)

    # 座次
    seat_class_m = re.search(r'(二等座|一等座|商务座|特等座|软卧|硬卧|硬座|无座|动卧|软座)', text)
    seat_class = seat_class_m.group(1) if seat_class_m else ''
    seat_dm = re.search(r'(\d{2}车[A-F\d]{3}[号位])', text)
    seat_detail = seat_dm.group(1) if seat_dm else ''
    vehicle = seat_class or seat_detail or '火车'

    # 票价
    amount = _extract_amount(text)

    # 发票项目
    item = '票价'
    if '退票' in text:
        item = '退票费'
    elif '改签' in text:
        item = '改签费'

    if from_station and to_station:
        from_short = from_station.replace('站', '')
        to_short = to_station.replace('站', '')
        tickets.append(Ticket(
            travel_date=travel_date,
            carrier=train,
            route=f"{from_short}-{to_short}",
            amount=amount,
            ticket_type='火车',
            vehicle=vehicle,
            item=item,
        ))

    return tickets


def _match_by_pinyin_blocks(pdf_bytes, stations_cn):
    """通过 PDF 块级拼音 x 坐标定位发站和到站。"""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        blocks = doc[0].get_text("blocks")
        doc.close()

        pinyin_blocks = []
        for b in blocks:
            x0, y0, x1, y1, bt, _, _ = b
            bt = bt.strip()
            if re.match(r'^[A-Z][a-z]+$', bt) and len(bt) > 3:
                pinyin_blocks.append((x0, bt))

        if not pinyin_blocks:
            return '', ''

        pinyin_blocks.sort(key=lambda b: b[0])
        left_pinyin = pinyin_blocks[0][1]
        right_pinyin = pinyin_blocks[-1][1] if len(pinyin_blocks) > 1 else ''

        pinyin_map = {
            'chengdudong': '成都东站', 'chengdunan': '成都南站', 'chengduxi': '成都西站',
            'chongqingbei': '重庆北站', 'chongqingxi': '重庆西站',
            'lesh an': '乐山站', 'leshan': '乐山站',
            'yaan': '雅安站', "ya'an": '雅安站',
            'nanchong': '南充站', 'nanchongbei': '南充北站',
            'mianyang': '绵阳站', 'deyang': '德阳站',
            'guangyuan': '广元站', 'qianjiang': '黔江站',
            'shuangliujichang': '双流机场站', 'yibindong': '宜宾东站',
            'luzhou': '泸州站', 'panzhihu nan': '攀枝花南站',
            'xichangxi': '西昌西站', 'zigong': '自贡站',
            'neijiangbei': '内江北站', 'zunyi': '遵义站',
            'guiyangbei': '贵阳北站',
        }

        def match_station(pinyin):
            pk = pinyin.lower().replace(' ', '')
            if pk in pinyin_map:
                return pinyin_map[pk]
            for s in stations_cn:
                s_no_zhan = s.replace('站', '')
                if pk[:4] == s_no_zhan[:4].lower()[:4]:
                    return s
            return ''

        from_station = match_station(left_pinyin)
        to_station = match_station(right_pinyin)

        if not to_station and len(stations_cn) >= 2:
            for s in stations_cn:
                if s != from_station:
                    to_station = s
                    break

        return from_station, to_station
    except Exception:
        return '', ''


def _match_by_pinyin_lines(lines, stations_cn):
    """通过纯文本拼音行定位发站和到站。"""
    for i, line in enumerate(lines):
        sline = line.strip()
        if re.match(r'^[A-Z][a-z]+$', sline) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r'^[一-鿿]+站$', next_line):
                from_station = next_line
                to_station = ''
                for j in range(i + 2, len(lines)):
                    cand = lines[j].strip()
                    if re.match(r'^[一-鿿]+站$', cand):
                        to_station = cand
                        break
                return from_station, to_station
    return '', ''


def _extract_travel_date(text: str) -> str:
    """从 PDF 文本提取乘车日期（排除开票日期）。"""
    dates_all = re.findall(r'(\d{4})年(\d{2})月(\d{2})日', text)
    for y, m, d in dates_all:
        ds = f"{y}-{m}-{d}"
        pos = text.find(f"{y}年{m}月{d}日")
        prefix = text[max(0, pos - 8):pos]
        if '开票' not in prefix and '填开' not in prefix:
            return ds
    if dates_all:
        y, m, d = dates_all[0]
        return f"{y}-{m}-{d}"
    return ''


def _extract_amount(text: str) -> float:
    """从 PDF 文本提取票价。"""
    am1 = re.search(r'[票价退改签]+[费:]*\s*[￥¥]\s*(\d+\.?\d*)', text)
    if am1:
        return float(am1.group(1))
    am2 = re.search(r'[￥¥]\s*(\d+\.?\d{2})', text)
    if am2:
        return float(am2.group(1))
    return 0.0
```

- [ ] **步骤 3：创建 `qmail_ticket/parsers/__init__.py`**

```python
"""解析器工厂"""
from qmail_ticket.models import RawEmail
from qmail_ticket.parsers.base import TicketParser
from qmail_ticket.parsers.train_12306 import Train12306Parser

PARSERS: list[TicketParser] = [Train12306Parser()]

def get_parser(raw_email: RawEmail) -> TicketParser | None:
    """根据邮件内容匹配解析器。"""
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
```

- [ ] **步骤 4：验证导入**

```bash
python3 -c "from qmail_ticket.parsers import get_parser, PARSERS; print(f'{len(PARSERS)} parsers')"
```

预期：`1 parsers`

- [ ] **步骤 5：Commit**

```bash
git add qmail_ticket/parsers/
git commit -m "feat: 添加解析器接口和 12306 火车票解析器"
```

---

### 任务 6：携程机票解析器

**文件：**
- 创建：`qmail_ticket/parsers/ctrip.py`
- 修改：`qmail_ticket/parsers/__init__.py`

- [ ] **步骤 1：创建 `qmail_ticket/parsers/ctrip.py`**

从 ticket.py:336-553, 486-526 迁移。包含 `parse_ctrip_pdf_text()`、`_clean_city()`、`_find_ctrip_flight()`、`_parse_ctrip_html()` 的全部逻辑：

```python
"""携程机票解析器"""
import email.policy
import quopri
import re
from email import message_from_bytes

from qmail_ticket.models import RawEmail, Ticket
from qmail_ticket.email_utils import extract_ctrip_pdfs
from qmail_ticket.pdf_utils import pdf_to_text
from qmail_ticket.parsers.base import TicketParser


class CtripParser(TicketParser):
    """携程机票解析器"""

    def can_parse(self, raw_email: RawEmail) -> bool:
        return "携程" in raw_email.subject

    def parse(self, raw_email: RawEmail) -> list[tuple[bytes, str, list[Ticket]]]:
        msg = message_from_bytes(raw_email.raw_bytes, policy=email.policy.default)
        pdf_list, html_text = extract_ctrip_pdfs(msg)
        if not pdf_list:
            return []

        results = []
        text_results = []
        img_pdfs = []

        for pdf_data in pdf_list:
            text = pdf_to_text(pdf_data)
            if text.strip():
                tickets = _parse_ctrip_pdf_text(text)
                if tickets:
                    text_results.append((pdf_data, tickets))
                else:
                    img_pdfs.append(pdf_data)
            else:
                img_pdfs.append(pdf_data)

        if text_results:
            for pdf_data, tickets in text_results:
                for t in tickets:
                    safe_date = t.travel_date.replace('/', '-')
                    safe_station = t.route.replace('/', '-').replace('\\', '-')
                    pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                    results.append((pdf_data, pdf_name, [t]))
            return results

        # 全部是图片型 PDF → HTML 回退
        if img_pdfs and html_text:
            html_tickets = _parse_ctrip_html(html_text)
            for i, pdf_data in enumerate(img_pdfs):
                if i < len(html_tickets):
                    t = html_tickets[i]
                    safe_date = t.travel_date.replace('/', '-')
                    safe_station = t.route.replace('/', '-').replace('\\', '-')
                    pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                    results.append((pdf_data, pdf_name, [t]))

        return results


# === 以下为从 ticket.py 迁移的解析逻辑 ===

def _parse_ctrip_pdf_text(text: str) -> list[Ticket]:
    """从携程 PDF 文本提取机票信息。"""
    tickets = []

    total = 0.0
    total_m = re.search(r'合计.*CNY\s*(\d+\.?\d*)', text, re.DOTALL)
    if total_m:
        total = float(total_m.group(1))

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    zi_idx = None
    for i, line in enumerate(lines):
        if line == '自:':
            zi_idx = i
            break
    if zi_idx is None:
        return tickets

    label_count = 1
    for j in range(zi_idx + 1, len(lines)):
        if lines[j] == '至:':
            label_count += 1
        else:
            break

    value_start = zi_idx + label_count
    values = []
    for j in range(value_start, min(value_start + 10, len(lines))):
        v = lines[j]
        if v.endswith(':') and len(v) <= 5:
            break
        values.append(v)

    if len(values) < 5:
        return tickets

    from_city = _clean_city(values[0])
    to_city = ''
    for v in reversed(values):
        if re.search(r'[一-鿿]', v):
            to_city = _clean_city(v)
            break
    if not to_city:
        return tickets

    flight_no = ''
    for v in values:
        vc = re.sub(r'\s+', '', v)
        if re.match(r'^(?=.*[A-Z])[A-Z0-9]{4,7}$', vc):
            flight_no = vc
            break

    travel_date = ''
    for v in values:
        dm = re.search(r'(\d{4})年(\d{2})月(\d{2})日', v)
        if dm:
            travel_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
            break

    route = f"{from_city}-{to_city}"
    if not travel_date or not route:
        return tickets

    tickets.append(Ticket(
        travel_date=travel_date,
        carrier=flight_no or _find_ctrip_flight(text),
        route=route,
        amount=total,
        ticket_type='飞机',
        vehicle='飞机',
        item='机票',
    ))
    return tickets


def _clean_city(city: str) -> str:
    """清理城市名: 去掉机场/航站楼信息。"""
    city = re.sub(r'\s*T\d+\s*$', '', city)
    parts = city.split()
    if parts and re.search(r'[一-鿿]', parts[0]):
        return parts[0]
    return city.strip()


def _find_ctrip_flight(text: str) -> str:
    """从文本中找航班号。"""
    for v in text.split('\n'):
        vc = v.strip()
        if re.match(r'^(?=.*[A-Z])[A-Z0-9]{4,7}$', vc):
            return vc
    m = re.search(r'承运人[:\s]*(.+?)(?:\n|$)', text)
    return m.group(1).strip() if m else '航班'


def _parse_ctrip_html(html_text: str) -> list[Ticket]:
    """从携程 HTML 正文回退解析机票信息。"""
    tickets = []
    try:
        decoded = quopri.decodestring(html_text.encode('latin-1')).decode('utf-8', errors='replace')
    except Exception:
        decoded = html_text

    pattern = r'订单号[：:](\d+)[，,]\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*([一-鿿]+-[一-鿿]+)'
    for m in re.finditer(pattern, decoded):
        travel_date = f"{m.group(2)}-{m.group(3).zfill(2)}-{m.group(4).zfill(2)}"
        route = m.group(5)
        order_id = m.group(1)[-6:]
        tickets.append(Ticket(
            travel_date=travel_date,
            carrier=f'订单{order_id}',
            route=route,
            amount=0.0,
            ticket_type='飞机',
            vehicle='飞机',
            item='机票',
        ))
    return tickets
```

- [ ] **步骤 2：更新 `qmail_ticket/parsers/__init__.py`**

```python
"""解析器工厂"""
from qmail_ticket.models import RawEmail
from qmail_ticket.parsers.base import TicketParser
from qmail_ticket.parsers.train_12306 import Train12306Parser
from qmail_ticket.parsers.ctrip import CtripParser

PARSERS: list[TicketParser] = [Train12306Parser(), CtripParser()]


def get_parser(raw_email: RawEmail) -> TicketParser | None:
    """根据邮件内容匹配解析器。"""
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
```

- [ ] **步骤 3：验证导入**

```bash
python3 -c "from qmail_ticket.parsers import get_parser, PARSERS; print(f'{len(PARSERS)} parsers')"
```

预期：`2 parsers`

- [ ] **步骤 4：Commit**

```bash
git add qmail_ticket/parsers/
git commit -m "feat: 添加携程机票解析器"
```

---

### 任务 7：输出器接口 + JPG 输出器

**文件：**
- 创建：`qmail_ticket/outputs/__init__.py`
- 创建：`qmail_ticket/outputs/base.py`
- 创建：`qmail_ticket/outputs/jpg_out.py`

- [ ] **步骤 1：创建 `qmail_ticket/outputs/base.py`**

```python
"""输出器抽象基类"""
from abc import ABC, abstractmethod

from qmail_ticket.models import Ticket


class OutputWriter(ABC):
    @abstractmethod
    def write(self, tickets: list[Ticket], context: dict) -> None:
        """输出结果"""
```

- [ ] **步骤 2：创建 `qmail_ticket/outputs/jpg_out.py`**

从 ticket.py:572-577, 768-779 迁移：

```python
"""PDF→JPG 输出器"""
import os
import sys

from qmail_ticket.models import Ticket
from qmail_ticket.pdf_utils import pdf_to_jpg
from qmail_ticket.outputs.base import OutputWriter

DEFAULT_DPI = 200


class JpgWriter(OutputWriter):
    """将 PDF 转为 JPG"""

    def write(self, tickets: list[Ticket], context: dict) -> None:
        output_dir = context['output_dir']
        pdf_data_list = context['pdf_data_list']
        dpi = context.get('jpg_dpi', DEFAULT_DPI)

        jpg_count = 0
        jpg_paths = []

        for pdf_data, pdf_name in pdf_data_list:
            jpg_path = os.path.join(output_dir, os.path.splitext(pdf_name)[0] + ".jpg")
            try:
                pdf_to_jpg(pdf_data, jpg_path, dpi)
                jpg_paths.append(jpg_path)
                jpg_count += 1
            except Exception as e:
                print(f"  {pdf_name} 转换失败: {e}", file=sys.stderr)

        context['jpg_paths'] = jpg_paths
        print(f"  成功转换: {jpg_count}")
```

- [ ] **步骤 3：创建 `qmail_ticket/outputs/__init__.py`**

```python
"""输出器注册"""
from qmail_ticket.outputs.base import OutputWriter
from qmail_ticket.outputs.jpg_out import JpgWriter

WRITERS: list[OutputWriter] = [JpgWriter()]
```

- [ ] **步骤 4：验证导入**

```bash
python3 -c "from qmail_ticket.outputs import WRITERS; print(f'{len(WRITERS)} writers')"
```

预期：`1 writers`

- [ ] **步骤 5：Commit**

```bash
git add qmail_ticket/outputs/
git commit -m "feat: 添加输出器接口和 JPG 输出器"
```

---

### 任务 8：CSV 汇总输出器

**文件：**
- 创建：`qmail_ticket/outputs/csv_out.py`
- 修改：`qmail_ticket/outputs/__init__.py`

- [ ] **步骤 1：创建 `qmail_ticket/outputs/csv_out.py`**

从 ticket.py:582-619 迁移：

```python
"""CSV 汇总表输出器"""
import csv
import os

from qmail_ticket.models import Ticket
from qmail_ticket.outputs.base import OutputWriter


class CsvWriter(OutputWriter):
    """生成 CSV 汇总表"""

    def write(self, tickets: list[Ticket], context: dict) -> None:
        output_dir = context['output_dir']
        jpg_paths = context.get('jpg_paths', [])
        csv_path = os.path.join(output_dir, "ticket_summary.csv")

        jpg_set = {os.path.splitext(os.path.basename(j))[0] for j in jpg_paths}

        verified, unmatched = [], []
        for t in tickets:
            suffix = "-机票" if t.ticket_type == '飞机' else ""
            expected = f"{t.travel_date}-{t.route}{suffix}"
            if expected in jpg_set:
                verified.append(t)
            else:
                unmatched.append(t)

        verified.sort(key=lambda x: (x.travel_date, x.ticket_type))

        # 终端输出
        header = f"  {'乘车日期':<12} {'交通工具':<10} {'车次/航班':<10} {'发到站':<20} {'票价':>8}"
        sep = f"  {'-'*12} {'-'*10} {'-'*10} {'-'*20} {'-'*8}"
        print(f"\n{header}\n{sep}")

        total = 0.0
        for t in verified:
            print(f"  {t.travel_date:<12} {t.vehicle:<10} {t.carrier:<10} {t.route:<20} {t.amount:>8.2f}")
            total += t.amount
        print(f"{sep}")
        print(f"  {'合计':<12} {'':<10} {'':<10} {'':<20} {total:>8.2f}")

        if unmatched:
            print(f"\n  !! {len(unmatched)} 条未匹配:")
            for t in unmatched:
                print(f"     {t.travel_date}-{t.route}")

        # 写 CSV
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['乘车日期', '交通工具', '车次/航班', '发到站', '票价'])
            for t in verified:
                w.writerow([t.travel_date, t.vehicle, t.carrier, t.route, f"{t.amount:.2f}"])
            w.writerow(['合计', '', '', '', f"{total:.2f}"])

        print(f"\n  汇总表: {csv_path}  (共 {len(verified)} 条, 合计 ¥{total:.2f})")
```

- [ ] **步骤 2：更新 `qmail_ticket/outputs/__init__.py`**

```python
"""输出器注册"""
from qmail_ticket.outputs.base import OutputWriter
from qmail_ticket.outputs.jpg_out import JpgWriter
from qmail_ticket.outputs.csv_out import CsvWriter

WRITERS: list[OutputWriter] = [JpgWriter(), CsvWriter()]
```

- [ ] **步骤 3：Commit**

```bash
git add qmail_ticket/outputs/
git commit -m "feat: 添加 CSV 汇总表输出器"
```

---

### 任务 9：合并排版 PDF 输出器

**文件：**
- 创建：`qmail_ticket/outputs/print_pdf.py`
- 修改：`qmail_ticket/outputs/__init__.py`

- [ ] **步骤 1：创建 `qmail_ticket/outputs/print_pdf.py`**

从 ticket.py:624-704 迁移：

```python
"""合并排版 PDF 输出器"""
import os

from qmail_ticket.models import Ticket
from qmail_ticket.outputs.base import OutputWriter

A4_DPI = 200


class PrintPdfWriter(OutputWriter):
    """将火车票和机票 JPG 合并排版为 print.pdf"""

    def write(self, tickets: list[Ticket], context: dict) -> None:
        try:
            from PIL import Image
        except ImportError:
            print("  需要 Pillow 库: pip3 install Pillow")
            return

        output_dir = context['output_dir']
        jpg_paths = context.get('jpg_paths', [])

        if not jpg_paths:
            print("  没有可合并的 JPG，跳过。")
            return

        PAGE_W = int(210 / 25.4 * A4_DPI)
        PAGE_H = int(297 / 25.4 * A4_DPI)
        MARGIN = 80
        SPACING = 32

        trains = sorted(
            [t for t in tickets if t.ticket_type == '火车'],
            key=lambda x: x.travel_date
        )
        flights = sorted(
            [t for t in tickets if t.ticket_type == '飞机'],
            key=lambda x: x.travel_date
        )

        def get_jpg_path(t):
            suffix = "-机票" if t.ticket_type == '飞机' else ""
            return os.path.join(output_dir, f"{t.travel_date}-{t.route}{suffix}.jpg")

        def make_pages(ticket_list, cols, rows):
            pages = []
            per_page = cols * rows
            cell_w = (PAGE_W - 2 * MARGIN - (cols - 1) * SPACING) / cols
            cell_h = (PAGE_H - 2 * MARGIN - (rows - 1) * SPACING) / rows

            for i in range(0, len(ticket_list), per_page):
                page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
                batch = ticket_list[i:i + per_page]

                for j, t in enumerate(batch):
                    jpg_path = get_jpg_path(t)
                    if not os.path.isfile(jpg_path):
                        continue

                    img = Image.open(jpg_path)
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

                pages.append(page)
            return pages

        train_pages = make_pages(trains, cols=2, rows=4)
        flight_pages = make_pages(flights, cols=2, rows=2)
        all_pages = train_pages + flight_pages

        if not all_pages:
            print("  没有可合并的 JPG，跳过。")
            return

        pdf_path = os.path.join(output_dir, "print.pdf")
        for img in all_pages:
            img.info['dpi'] = (A4_DPI, A4_DPI)
        all_pages[0].save(
            pdf_path,
            save_all=True,
            append_images=all_pages[1:],
        )
        print(f"  print.pdf 已生成: {pdf_path} (共 {len(all_pages)} 页)")
```

- [ ] **步骤 2：更新 `qmail_ticket/outputs/__init__.py`**

```python
"""输出器注册"""
from qmail_ticket.outputs.base import OutputWriter
from qmail_ticket.outputs.jpg_out import JpgWriter
from qmail_ticket.outputs.csv_out import CsvWriter
from qmail_ticket.outputs.print_pdf import PrintPdfWriter

WRITERS: list[OutputWriter] = [JpgWriter(), CsvWriter(), PrintPdfWriter()]
```

- [ ] **步骤 3：Commit**

```bash
git add qmail_ticket/outputs/
git commit -m "feat: 添加合并排版 PDF 输出器"
```

---

### 任务 10：CLI 入口

**文件：**
- 创建：`qmail_ticket/cli.py`
- 创建：`qmail_ticket/__main__.py`

- [ ] **步骤 1：创建 `qmail_ticket/cli.py`**

整合 ticket.py:709-800 和 ticket_imap.py:220-327 的主流程：

```python
"""CLI 入口"""
import argparse
import os
import sys
from datetime import datetime

from qmail_ticket.sources import get_source
from qmail_ticket.parsers import get_parser
from qmail_ticket.outputs import WRITERS

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def parse_date_arg(s: str) -> datetime | None:
    return datetime.strptime(s.strip(), "%Y-%m-%d") if s else None


def parse_args():
    p = argparse.ArgumentParser(description="12306 + 携程 电子发票/报销凭证提取工具")
    p.add_argument("--source", choices=["foxmail", "imap"], default="foxmail",
                   help="邮件源 (默认 foxmail)")
    p.add_argument("--email", help="邮箱地址 (imap 源必需)")
    p.add_argument("--code", help="授权码 (imap 源必需)")
    p.add_argument("--start", help="起始日期 (YYYY-MM-DD)")
    p.add_argument("--end", help="截止日期 (YYYY-MM-DD)")
    return p.parse_args()


def main():
    print("=" * 60)
    print("  12306 + 携程 电子发票 / 报销凭证提取工具")
    print("=" * 60)

    args = parse_args()

    # 日期处理
    start_s = args.start or (input("  起始日期 (YYYY-MM-DD, 回车跳过): ").strip()
                              if args.source == 'foxmail' else args.start)
    end_s = args.end or (input("  截止日期 (YYYY-MM-DD, 回车跳过): ").strip()
                          if args.source == 'foxmail' else args.end)

    start_date = parse_date_arg(start_s) if start_s else None
    end_date = parse_date_arg(end_s) if end_s else None
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    if start_date or end_date:
        print(f"  筛选范围: {start_s or '不限'} ~ {end_s or '不限'}")

    # [1] 连接并搜索
    print(f"\n[1/4] 连接 {args.source}...")
    source_kwargs = {}
    if args.source == 'imap':
        if not args.email or not args.code:
            print("  错误: imap 源需要 --email 和 --code 参数", file=sys.stderr)
            sys.exit(1)
        source_kwargs = {'email': args.email, 'code': args.code}

    source = get_source(args.source, **source_kwargs)
    source.connect()
    raw_emails = source.search(start_date, end_date)
    source.disconnect()

    print(f"  找到 {len(raw_emails)} 封目标邮件")
    if not raw_emails:
        print("  未找到目标邮件，退出。")
        return

    # [2] 解析票面
    print(f"\n[2/4] 解析票面...")
    all_tickets = []
    pdf_data_list = []

    for raw in raw_emails:
        parser = get_parser(raw)
        if not parser:
            continue
        results = parser.parse(raw)
        if not results:
            continue
        for pdf_bytes, pdf_name, tickets in results:
            all_tickets.extend(tickets)
            pdf_data_list.append((pdf_bytes, pdf_name))
            tag = "机票" if "机票" in pdf_name else "火车"
            print(f"  [{tag}] {pdf_name}")

    print(f"  成功解析: {len(all_tickets)} 张票据")
    if not all_tickets:
        print("  没有可提取的附件，退出。")
        return

    # [3] 输出
    print(f"\n[3/4] 输出结果...")
    context = {
        'output_dir': OUTPUT_DIR,
        'pdf_data_list': pdf_data_list,
    }
    for writer in WRITERS:
        writer.write(all_tickets, context)

    # [4] 完成
    print(f"\n[4/4] 完成!")
    print("=" * 60)
```

- [ ] **步骤 2：创建 `qmail_ticket/__main__.py`**

```python
"""python -m qmail_ticket 入口"""
from qmail_ticket.cli import main

if __name__ == '__main__':
    main()
```

- [ ] **步骤 3：验证 CLI 帮助**

```bash
python3 -m qmail_ticket --help
```

预期：显示帮助信息，包含 `--source`、`--email`、`--code`、`--start`、`--end` 参数。

- [ ] **步骤 4：Commit**

```bash
git add qmail_ticket/cli.py qmail_ticket/__main__.py
git commit -m "feat: 添加 CLI 入口，统一 Foxmail/IMAP 两种模式"
```

---

### 任务 11：端到端验证 + 清理

**文件：**
- 删除：`ticket.py`（可选，先保留作备份）
- 删除：`ticket_imap.py`（可选，先保留作备份）

- [ ] **步骤 1：验证包完整性**

```bash
cd /Users/yangjie/Desktop/Qmail-Ticket
python3 -c "
from qmail_ticket.models import Ticket, RawEmail
from qmail_ticket.sources import get_source
from qmail_ticket.parsers import get_parser, PARSERS
from qmail_ticket.outputs import WRITERS
print(f'Models: OK')
print(f'Sources: foxmail, imap')
print(f'Parsers: {len(PARSERS)}')
print(f'Writers: {len(WRITERS)}')
print('All imports OK!')
"
```

预期：`All imports OK!`

- [ ] **步骤 2：验证 CLI Foxmail 模式**

```bash
python3 -m qmail_ticket --source foxmail --help
```

预期：显示帮助信息。

- [ ] **步骤 3：验证 CLI IMAP 模式参数检查**

```bash
python3 -m qmail_ticket --source imap 2>&1
```

预期：提示需要 `--email` 和 `--code` 参数。

- [ ] **步骤 4：重命名旧文件作备份**

```bash
cd /Users/yangjie/Desktop/Qmail-Ticket
mv ticket.py ticket.py.bak
mv ticket_imap.py ticket_imap.py.bak
```

- [ ] **步骤 5：最终验证**

```bash
python3 -m qmail_ticket --help
```

预期：正常显示帮助。

- [ ] **步骤 6：Commit**

```bash
git add -A
git commit -m "refactor: 完成重构，旧文件备份为 .bak"
```

---

## 自检

**规格覆盖度：**
- [x] §3 数据模型 → 任务 1
- [x] §4 邮件源 → 任务 3, 4
- [x] §5 解析器 → 任务 5, 6
- [x] §6 输出器 → 任务 7, 8, 9
- [x] §7 公共工具 → 任务 2
- [x] §8 CLI → 任务 10
- [x] §9 配置 → 分散在各模块中（foxmail.py 常量、imap.py 默认值、cli.py OUTPUT_DIR）
- [x] §11 迁移策略 → 任务 11

**占位符扫描：** 无 TODO/待定/后续实现。

**类型一致性：** `Ticket` dataclass 字段名在 parsers（构造）和 outputs（读取）间一致：`travel_date`、`carrier`、`route`、`amount`、`ticket_type`、`vehicle`、`item`。
