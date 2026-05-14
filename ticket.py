#!/usr/bin/env python3
"""
12306 + 携程 电子发票 / 报销凭证提取工具
从 Foxmail 本地邮件提取火车票 & 机票，解析 PDF 票面内容，转为 JPG，输出汇总表 (CSV)。

用法:
    python3 ticket.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]

依赖: pip3 install --break-system-packages PyMuPDF
"""

import argparse
import base64
import csv
import email.policy
import glob
import io
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime

# ============ 配置 ============

FOXMAIL_PROFILES = os.path.expanduser(
    "~/Library/Containers/com.tencent.Foxmail/Data/Library/Foxmail/Profiles"
)
SUBJECT_12306 = "zfjJz7m6xrHPtc2zLbXn19O3osaxzajWqg=="   # GBK Base64: 网上购票系统-电子发票通知
SUBJECT_CTRIP = "5pC656iLOiDnlLXlrZDmiqXplIDlh63or4E="     # UTF-8 Base64: 携程: 电子报销凭证

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(OUTPUT_DIR, "ticket_summary.csv")
JPG_DPI = 200
DELETE_PDF_AFTER = True


# ============ 日期工具 ============

def parse_email_date(filepath):
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


def parse_date_arg(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d") if s else None


# ============ 搜索 ============

def find_all_target_mails(start_date=None, end_date=None):
    train_files, flight_files = [], []
    for profile_dir in glob.glob(os.path.join(FOXMAIL_PROFILES, "*")):
        mail_root = os.path.join(profile_dir, "Mail")
        if not os.path.isdir(mail_root):
            continue

        for label, pattern, lst in [
            ("12306", SUBJECT_12306, train_files),
            ("携程", SUBJECT_CTRIP, flight_files),
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
                print(f"  搜索 {label} 出错: {e}", file=sys.stderr)

    if start_date or end_date:
        train_files = _filter(train_files, start_date, end_date, "12306")
        flight_files = _filter(flight_files, start_date, end_date, "携程")
    return train_files, flight_files


def _filter(files, start_date, end_date, label):
    out = []
    for fp in files:
        d = parse_email_date(fp)
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


# ============ 邮件附件提取 ============

def extract_12306_pdf(msg):
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


def extract_ctrip_pdfs(msg):
    """从携程邮件提取所有 PDF 附件和 HTML 正文。返回 ([pdf_bytes], html_text)。"""
    pdf_list = []
    html_text = None

    for part in msg.walk():
        ct = part.get_content_type()
        cd = part.get_content_disposition()
        fn = part.get_filename()

        # 提取 PDF（可能有多个）
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

        # 提取 HTML 正文
        if ct == 'text/html' and cd != 'attachment':
            payload = part.get_payload(decode=True)
            if payload:
                cs = part.get_content_charset() or 'utf-8'
                try:
                    html_text = payload.decode(cs, errors='replace')
                except Exception:
                    html_text = payload.decode('utf-8', errors='replace')

    return pdf_list, html_text


# ============ PDF 票面解析 ============

def parse_12306_pdf_text(text, pdf_bytes=None):
    """
    从 12306 PDF 文本提取车票信息。
    发站 = 左/有拼音, 到站 = 右/无拼音。
    """
    tickets = []

    lines = text.strip().split('\n')
    stations_cn = [l.strip() for l in lines if re.match(r'^[一-鿿]+站$', l.strip())]

    from_station = ''
    to_station = ''

    # 方法1: 用 PDF 块级拼音 x 坐标定位 (最可靠)
    if pdf_bytes and len(stations_cn) >= 2:
        try:
            import fitz
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            blocks = doc[0].get_text("blocks")
            doc.close()

            # 收集拼音块: (x0, pinyin_text)
            pinyin_blocks = []
            for b in blocks:
                x0, y0, x1, y1, bt, _, _ = b
                bt = bt.strip()
                # 拼音: 纯字母+首字母大写, 且不是英文单词
                if re.match(r'^[A-Z][a-z]+$', bt) and len(bt) > 3:
                    pinyin_blocks.append((x0, bt))

            if pinyin_blocks:
                # 按 x 排序: 左 = 发站
                pinyin_blocks.sort(key=lambda b: b[0])
                left_pinyin = pinyin_blocks[0][1]
                right_pinyin = pinyin_blocks[-1][1] if len(pinyin_blocks) > 1 else ''

                # 通过拼音匹配中文站名
                # 常见拼音-中文映射
                pinyin_map = {
                    'chengdudong': '成都东站', 'chengdunan': '成都南站', 'chengduxi': '成都西站',
                    'chongqingbei': '重庆北站', 'chongqingxi': '重庆西站',
                    'lesh an': '乐山站', 'leshan': '乐山站',
                    'yaan': '雅安站', 'ya\'an': '雅安站',
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
                    # 模糊匹配
                    for s in stations_cn:
                        s_no_zhan = s.replace('站', '')
                        # 取拼音前几个字母匹配站名首字母
                        if pk[:4] == s_no_zhan[:4].lower()[:4]:
                            return s
                    return ''

                from_station = match_station(left_pinyin)
                to_station = match_station(right_pinyin)

                # 如果只有一个拼音块 (只有发站有拼音)
                if not to_station and len(stations_cn) >= 2:
                    for s in stations_cn:
                        if s != from_station:
                            to_station = s
                            break

        except Exception:
            pass

    # 方法2: 纯文本拼音行定位 (只有一个拼音行的 PDF)
    if not from_station and len(stations_cn) >= 2:
        for i, line in enumerate(lines):
            sline = line.strip()
            if re.match(r'^[A-Z][a-z]+$', sline) and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if re.match(r'^[一-鿿]+站$', next_line):
                    from_station = next_line
                    for j in range(i + 2, len(lines)):
                        cand = lines[j].strip()
                        if re.match(r'^[一-鿿]+站$', cand):
                            to_station = cand
                            break
                    break

    # 方法3: 纯文本顺序回退
    if not from_station and len(stations_cn) >= 2:
        from_station = stations_cn[0]
        to_station = stations_cn[1]

    # ---- 找车次 ----
    trains = re.findall(r'\b([GCDKZT]\d{2,5})\b', text, re.IGNORECASE)
    trains = [t.upper() for t in trains]
    train = trains[0] if trains else ''

    # ---- 找乘车日期 ----
    travel_date = ''
    dates_all = re.findall(r'(\d{4})年(\d{2})月(\d{2})日', text)
    for y, m, d in dates_all:
        ds = f"{y}-{m}-{d}"
        pos = text.find(f"{y}年{m}月{d}日")
        prefix = text[max(0, pos - 8):pos]
        if '开票' not in prefix and '填开' not in prefix:
            travel_date = ds
            break
    if not travel_date and dates_all:
        y, m, d = dates_all[0]
        travel_date = f"{y}-{m}-{d}"

    # ---- 找座次 ----
    seat_class = ''
    seat_m = re.search(r'(二等座|一等座|商务座|特等座|软卧|硬卧|硬座|无座|动卧|软座)', text)
    if seat_m:
        seat_class = seat_m.group(1)
    seat_dm = re.search(r'(\d{2}车[A-F\d]{3}[号位])', text)
    seat_detail = seat_dm.group(1) if seat_dm else ''
    vehicle = seat_class or seat_detail or '火车'

    # ---- 找票价 ----
    amount = 0.0
    am1 = re.search(r'[票价退改签]+[费:]*\s*[￥¥]\s*(\d+\.?\d*)', text)
    if am1:
        amount = float(am1.group(1))
    else:
        am2 = re.search(r'[￥¥]\s*(\d+\.?\d{2})', text)
        if am2:
            amount = float(am2.group(1))

    # ---- 发票项目 ----
    item = '票价'
    if '退票' in text:
        item = '退票费'
    elif '改签' in text:
        item = '改签费'

    # ---- 组装 ----
    if from_station and to_station:
        from_short = from_station.replace('站', '')
        to_short = to_station.replace('站', '')
        station = f"{from_short}-{to_short}"

        tickets.append({
            'travel_date': travel_date,
            'train': train,
            'station': station,
            'amount': amount,
            'type': '火车',
            'vehicle': vehicle,
            'item': item,
        })

    return tickets


def parse_ctrip_pdf_text(text):
    """
    从携程 PDF 文本提取机票信息。
    PDF 双列布局: 标签列 + 值列。
    关键字段:
      - 自: {城市} / 至: {城市}
      - 航班号: ZH8848
      - 日期: 2026年04月28日
      - 合计: CNY 800.00
    """
    tickets = []

    # ---- 合计金额 (从合计单元格中提取 CNY 后面的数值) ----
    total = 0.0
    total_m = re.search(r'合计.*CNY\s*(\d+\.?\d*)', text, re.DOTALL)
    if total_m:
        total = float(total_m.group(1))

    # ---- 解析右列值块 ----
    # 标签列以 "自:" 开头，后续有多个 "至:" (每个航段一个)
    # 标签列结束后的值块格式:
    #   {from_city}\n{carrier}\n{flight#}\n{seat}\n{date}\n{time}\n{level}\n{baggage}\n{to_city}
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # 找到 "自:" 标签的开始位置
    zi_idx = None
    for i, line in enumerate(lines):
        if line == '自:':
            zi_idx = i
            break

    if zi_idx is None:
        return tickets

    # 计算标签数量 (自: + 至: 重复次数)
    label_count = 1  # "自:"
    for j in range(zi_idx + 1, len(lines)):
        if lines[j] == '至:':
            label_count += 1
        else:
            break

    # 值块从标签之后开始
    value_start = zi_idx + label_count
    values = []
    for j in range(value_start, min(value_start + 10, len(lines))):
        v = lines[j]
        # 值判断: 不是纯标签格式
        if v.endswith(':') and len(v) <= 5:
            break
        values.append(v)

    if len(values) < 5:
        return tickets

    # 解析值块
    # values[0] = 出发城市, values[-1] = 到达城市(如果只有一个航段)
    # 如果有多个航段, 值块中会有多个城市
    from_city = _clean_city(values[0])

    # 从后往前找到达城市 (城市名包含中文)
    to_city = ''
    for v in reversed(values):
        if re.search(r'[一-鿿]', v):
            to_city = _clean_city(v)
            break

    if not to_city:
        return tickets

    # 航班号 (至少一个字母, 4-7位字母数字)
    flight_no = ''
    for v in values:
        vc = re.sub(r'\s+', '', v)
        if re.match(r'^(?=.*[A-Z])[A-Z0-9]{4,7}$', vc):
            flight_no = vc
            break

    # 日期
    travel_date = ''
    for v in values:
        dm = re.search(r'(\d{4})年(\d{2})月(\d{2})日', v)
        if dm:
            travel_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
            break

    route = f"{from_city}-{to_city}"
    if not travel_date or not route:
        return tickets

    tickets.append({
        'travel_date': travel_date,
        'train': flight_no or _find_ctrip_flight(text),
        'station': route,
        'amount': total,
        'type': '飞机',
        'vehicle': '飞机',
        'item': '机票',
    })

    return tickets


def _clean_city(city):
    """清理城市名: 去掉机场/航站楼信息。"""
    # 去掉 T1/T2/T3 等
    city = re.sub(r'\s*T\d+\s*$', '', city)
    # 取第一个词 (城市名)
    parts = city.split()
    if parts and re.search(r'[一-鿿]', parts[0]):
        return parts[0]
    return city.strip()


def _find_ctrip_flight(text):
    """从文本中找航班号。"""
    for v in text.split('\n'):
        vc = v.strip()
        # 必须包含至少一个字母, 总长 4-7, 字母数字组合
        if re.match(r'^(?=.*[A-Z])[A-Z0-9]{4,7}$', vc):
            return vc
    m = re.search(r'承运人[:\s]*(.+?)(?:\n|$)', text)
    return m.group(1).strip() if m else '航班'


# ============ 处理入口 ============

def process_train_mail(filepath):
    """处理 12306 邮件。"""
    with open(filepath, 'rb') as f:
        msg = email.message_from_bytes(f.read(), policy=email.policy.default)

    pdf_data = extract_12306_pdf(msg)
    if not pdf_data:
        return []

    text = _pdf_to_text(pdf_data)
    if not text:
        return []

    tickets = parse_12306_pdf_text(text, pdf_data)
    results = []
    for t in tickets:
        safe_date = t['travel_date'].replace('/', '-')
        safe_station = t['station'].replace('/', '-').replace('\\', '-')
        pdf_name = f"{safe_date}-{safe_station}.pdf"
        results.append((pdf_data, pdf_name, [t]))
    return results


def process_flight_mail(filepath):
    """处理携程邮件。支持多个 PDF 附件，优先 PDF 文本解析，回退到 HTML。"""
    with open(filepath, 'rb') as f:
        msg = email.message_from_bytes(f.read(), policy=email.policy.default)

    pdf_list, html_text = extract_ctrip_pdfs(msg)
    if not pdf_list:
        return []

    results = []
    text_results = []  # (pdf_data, [tickets])

    for pdf_data in pdf_list:
        text = _pdf_to_text(pdf_data)
        if text.strip():
            tickets = parse_ctrip_pdf_text(text)
            if tickets:
                text_results.append((pdf_data, tickets))

    if text_results:
        # 有 PDF 成功解析出文本 → 每个 PDF 对应自己的票
        for pdf_data, tickets in text_results:
            for t in tickets:
                safe_date = t['travel_date'].replace('/', '-')
                safe_station = t['station'].replace('/', '-').replace('\\', '-')
                pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                results.append((pdf_data, pdf_name, [t]))
        return results

    # 全部是图片型 PDF → 用 HTML 回退
    if html_text:
        html_tickets = _parse_ctrip_html(html_text)
        for i, pdf_data in enumerate(pdf_list):
            if i < len(html_tickets):
                t = html_tickets[i]
                safe_date = t['travel_date'].replace('/', '-')
                safe_station = t['station'].replace('/', '-').replace('\\', '-')
                pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                results.append((pdf_data, pdf_name, [t]))

    return results


def _parse_ctrip_html(html_text):
    """从携程 HTML 正文回退解析机票信息。"""
    import quopri as _qp
    tickets = []
    # 可能已经是 decoded UTF-8，也可能需要 quoted-printable decode
    try:
        decoded = _qp.decodestring(html_text.encode('latin-1')).decode('utf-8', errors='replace')
    except Exception:
        decoded = html_text

    pattern = r'订单号[：:](\d+)[，,]\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*([一-鿿]+-[一-鿿]+)'
    for m in re.finditer(pattern, decoded):
        travel_date = f"{m.group(2)}-{m.group(3).zfill(2)}-{m.group(4).zfill(2)}"
        route = m.group(5)
        order_id = m.group(1)[-6:]
        tickets.append({
            'travel_date': travel_date,
            'train': f'订单{order_id}',
            'station': route,
            'amount': 0.0,
            'type': '飞机',
            'vehicle': '飞机',
            'item': '机票',
        })
    return tickets


def _pdf_to_text(pdf_bytes):
    """从 PDF 字节提取文本。"""
    import fitz
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception:
        return ""


# ============ PDF 转 JPG ============

def pdf_to_jpg(pdf_bytes, jpg_path):
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=JPG_DPI)
    pix.save(jpg_path)
    doc.close()


# ============ 汇总表 ============

def write_summary(all_tickets, jpg_files):
    jpg_set = {os.path.splitext(os.path.basename(j))[0] for j in jpg_files}

    verified, unmatched = [], []
    for t in all_tickets:
        suffix = "-机票" if t['type'] == '飞机' else ""
        expected = f"{t['travel_date']}-{t['station']}{suffix}"
        if expected in jpg_set:
            verified.append(t)
        else:
            unmatched.append(t)

    verified.sort(key=lambda x: (x['travel_date'], x['type']))

    header = f"  {'乘车日期':<12} {'交通工具':<10} {'车次/航班':<10} {'发到站':<20} {'票价':>8}"
    sep = f"  {'-'*12} {'-'*10} {'-'*10} {'-'*20} {'-'*8}"
    print(f"\n{header}\n{sep}")

    total = 0.0
    for t in verified:
        print(f"  {t['travel_date']:<12} {t['vehicle']:<10} {t['train']:<10} {t['station']:<20} {t['amount']:>8.2f}")
        total += t['amount']
    print(f"{sep}")
    print(f"  {'合计':<12} {'':<10} {'':<10} {'':<20} {total:>8.2f}")

    if unmatched:
        print(f"\n  !! {len(unmatched)} 条未匹配:")
        for t in unmatched:
            print(f"     {t.get('travel_date','')}-{t.get('station','')}")

    with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['乘车日期', '交通工具', '车次/航班', '发到站', '票价'])
        for t in verified:
            w.writerow([t['travel_date'], t['vehicle'], t['train'], t['station'], f"{t['amount']:.2f}"])
        w.writerow(['合计', '', '', '', f"{total:.2f}"])

    print(f"\n  汇总表: {CSV_PATH}  (共 {len(verified)} 条, 合计 ¥{total:.2f})")


# ============ PDF 合并排版 ============

def create_print_pdf(all_tickets, output_dir):
    """将火车票和机票 JPG 合并排版为 print.pdf。"""
    try:
        from PIL import Image
    except ImportError:
        print("  需要 Pillow 库: pip3 install Pillow")
        return

    A4_DPI = 200
    PAGE_W = int(210 / 25.4 * A4_DPI)
    PAGE_H = int(297 / 25.4 * A4_DPI)
    MARGIN = 80
    SPACING = 32

    trains = sorted(
        [t for t in all_tickets if t['type'] == '火车'],
        key=lambda x: x['travel_date']
    )
    flights = sorted(
        [t for t in all_tickets if t['type'] == '飞机'],
        key=lambda x: x['travel_date']
    )

    def get_jpg_path(t):
        suffix = "-机票" if t['type'] == '飞机' else ""
        return os.path.join(output_dir, f"{t['travel_date']}-{t['station']}{suffix}.jpg")

    def make_pages(tickets, cols, rows):
        pages = []
        per_page = cols * rows
        cell_w = (PAGE_W - 2 * MARGIN - (cols - 1) * SPACING) / cols
        cell_h = (PAGE_H - 2 * MARGIN - (rows - 1) * SPACING) / rows

        for i in range(0, len(tickets), per_page):
            page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
            batch = tickets[i:i + per_page]

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


# ============ 主流程 ============

def parse_args():
    p = argparse.ArgumentParser(description="12306 + 携程 电子发票/报销凭证提取工具")
    p.add_argument("--start", help="收件起始日期 (YYYY-MM-DD)")
    p.add_argument("--end", help="收件截止日期 (YYYY-MM-DD)")
    return p.parse_args()


def main():
    print("=" * 60)
    print("  12306 + 携程 电子发票 / 报销凭证提取工具")
    print("  (基于 PDF 票面内容解析)")
    print("=" * 60)

    args = parse_args()
    start_s = args.start or input("  收件起始日期 (YYYY-MM-DD, 回车跳过): ").strip()
    end_s = args.end or input("  收件截止日期 (YYYY-MM-DD, 回车跳过): ").strip()

    start_date = parse_date_arg(start_s) if start_s else None
    end_date = parse_date_arg(end_s) if end_s else None
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    if start_date or end_date:
        print(f"  筛选范围: {start_s or '不限'} ~ {end_s or '不限'}")

    # [1] 搜索
    print("\n[1/6] 搜索 Foxmail 中的邮件...")
    train_files, flight_files = find_all_target_mails(start_date, end_date)
    print(f"  12306 火车票: {len(train_files)} 封")
    print(f"  携程   机票: {len(flight_files)} 封")
    if not train_files and not flight_files:
        print("  未找到目标邮件，退出。")
        return

    # [2] 解析
    all_results = []
    for label, files, processor in [
        ("12306 火车票", train_files, process_train_mail),
        ("携程 机票", flight_files, process_flight_mail),
    ]:
        if not files:
            continue
        print(f"\n[2/6] 解析 {label} ({len(files)} 封)...")
        fail = 0
        for fp in files:
            results = processor(fp)
            if not results:
                fail += 1
            else:
                for r in results:
                    all_results.append(r)
                    tag = "机票" if "机票" in r[1] else "火车"
                    print(f"  [{tag}] {r[1]}")
        print(f"  成功: {len(files) - fail}, 跳过: {fail}")

    if not all_results:
        print("  没有可提取的附件，退出。")
        return

    # [3] PDF -> JPG
    print(f"\n[3/6] 转换 PDF 为 JPG ({JPG_DPI} DPI)...")
    jpg_count = 0
    jpg_files = []
    for pdf_data, pdf_name, _ in all_results:
        jpg_path = os.path.join(OUTPUT_DIR, os.path.splitext(pdf_name)[0] + ".jpg")
        try:
            pdf_to_jpg(pdf_data, jpg_path)
            jpg_files.append(jpg_path)
            jpg_count += 1
        except Exception as e:
            print(f"  {pdf_name} 转换失败: {e}", file=sys.stderr)
    print(f"  成功转换: {jpg_count}")

    # [4] 汇总
    print(f"\n[4/6] 验证并生成汇总表...")
    all_tickets = []
    for _, _, tickets in all_results:
        all_tickets.extend(tickets)
    write_summary(all_tickets, jpg_files)

    # [5] 生成 print.pdf
    print(f"\n[5/6] 生成 print.pdf...")
    create_print_pdf(all_tickets, OUTPUT_DIR)

    # [6] 完成
    print(f"\n[6/6] 完成!")
    print(f"  JPG 文件: {jpg_count} 个 -> {OUTPUT_DIR}")
    print(f"  汇总表格: {CSV_PATH}")
    print("=" * 60)


if __name__ == '__main__':
    main()
