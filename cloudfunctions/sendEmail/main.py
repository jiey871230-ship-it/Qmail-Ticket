"""sendEmail 云函数主入口

重新连接 IMAP → 解析邮件 → 生成文件 → SMTP 发送
"""
import base64
import csv
import io
import zipfile
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

import fitz
from PIL import Image

from sources.imap import ImapSource
from parsers import get_parser


def main(event, context):
    """云函数入口：重新解析邮件并发送"""
    email_addr = event['email']
    auth_code = event['code']
    to_address = event['toAddress']
    start_date = _parse_date(event.get('startDate'))
    end_date = _parse_date(event.get('endDate'))

    t0 = time.time()

    try:
        # [1] IMAP 连接 & 搜索
        source = ImapSource(email_addr, auth_code)
        source.connect()
        raw_emails = source.search(start_date, end_date)
        source.disconnect()

        if not raw_emails:
            return {'success': False, 'error': '未找到邮件'}

        t1 = time.time()

        # [2] 解析邮件，生成文件
        all_tickets = []
        all_jpgs = []    # [(name, bytes)]

        for raw in raw_emails:
            parser = get_parser(raw)
            if not parser:
                continue
            results = parser.parse(raw)
            if not results:
                continue
            for pdf_bytes, pdf_name, tickets in results:
                jpg_bytes = _pdf_to_jpg_bytes(pdf_bytes, dpi=150)
                jpg_name = pdf_name.replace('.pdf', '.jpg')
                all_jpgs.append((jpg_name, jpg_bytes))
                for t in tickets:
                    all_tickets.append(t)

        t2 = time.time()

        if not all_tickets:
            return {'success': False, 'error': '未找到票据'}

        # [3] 生成 CSV
        csv_bytes = _generate_csv(all_tickets)

        # [4] 生成合并排版 PDF
        print_pdf_bytes = _generate_print_pdf(all_jpgs, all_tickets)

        t3 = time.time()

        # [5] 打包为 ZIP
        zip_bytes = _pack_zip(all_jpgs, csv_bytes, print_pdf_bytes)

        t4 = time.time()

        # [6] SMTP 发送
        _send_email(email_addr, auth_code, to_address, zip_bytes)

        t5 = time.time()

        return {
            'success': True,
            'to': to_address,
            'ticketCount': len(all_tickets),
            'timing': {
                'imap': round(t1 - t0, 1),
                'parse': round(t2 - t1, 1),
                'generate': round(t3 - t2, 1),
                'zip': round(t4 - t3, 1),
                'smtp': round(t5 - t4, 1),
                'total': round(t5 - t0, 1),
            },
            'zipSize': len(zip_bytes),
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}


def _parse_date(s):
    if not s:
        return None
    from datetime import datetime
    return datetime.strptime(s.strip(), "%Y-%m-%d")


def _pdf_to_jpg_bytes(pdf_bytes, dpi=150):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    jpg_bytes = pix.tobytes("jpeg")
    doc.close()
    return jpg_bytes


def _generate_csv(tickets):
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['乘车日期', '交通工具', '车次/航班', '发到站', '票价'])
    total = 0.0
    for t in sorted(tickets, key=lambda x: x.travel_date):
        w.writerow([t.travel_date, t.vehicle, t.carrier, t.route, f"{t.amount:.2f}"])
        total += t.amount
    w.writerow(['合计', '', '', '', f"{total:.2f}"])
    return output.getvalue().encode('utf-8-sig')


def _generate_print_pdf(jpgs, tickets):
    """合并 JPG 为排版 PDF"""
    A4_DPI = 150
    PAGE_W = int(210 / 25.4 * A4_DPI)
    PAGE_H = int(297 / 25.4 * A4_DPI)
    MARGIN = 60
    SPACING = 24

    jpg_map = {name: data for name, data in jpgs}

    # 按类型分组
    train_tickets = [t for t in tickets if t.ticket_type == '火车']
    flight_tickets = [t for t in tickets if t.ticket_type == '飞机']

    def make_pages(ticket_list, cols, rows):
        pages = []
        per_page = cols * rows
        cell_w = (PAGE_W - 2 * MARGIN - (cols - 1) * SPACING) / cols
        cell_h = (PAGE_H - 2 * MARGIN - (rows - 1) * SPACING) / rows

        for i in range(0, len(ticket_list), per_page):
            page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
            batch = ticket_list[i:i + per_page]

            for j, t in enumerate(batch):
                jpg_name = t.travel_date + '-' + t.route.replace('/', '-') + '.jpg'
                jpg_data = jpg_map.get(jpg_name)
                if not jpg_data:
                    continue
                try:
                    img = Image.open(io.BytesIO(jpg_data))
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
                except Exception:
                    continue
            pages.append(page)
        return pages

    train_pages = make_pages(train_tickets, cols=2, rows=4)
    flight_pages = make_pages(flight_tickets, cols=2, rows=2)
    all_pages = train_pages + flight_pages

    if not all_pages:
        return b''

    for img in all_pages:
        img.info['dpi'] = (A4_DPI, A4_DPI)

    pdf_buffer = io.BytesIO()
    all_pages[0].save(pdf_buffer, save_all=True, append_images=all_pages[1:], format='PDF')
    return pdf_buffer.getvalue()


def _pack_zip(jpgs, csv_bytes, print_pdf_bytes):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in jpgs:
            zf.writestr(f'jpgs/{name}', data)
        zf.writestr('ticket_summary.csv', csv_bytes)
        if print_pdf_bytes:
            zf.writestr('print.pdf', print_pdf_bytes)
    return buf.getvalue()


def _send_email(email_addr, auth_code, to_address, zip_bytes):
    msg = MIMEMultipart()
    msg['From'] = email_addr
    msg['To'] = to_address
    msg['Subject'] = '车票管家 - 票据提取结果'

    body = MIMEText('请查收附件中的票据文件。', 'plain', 'utf-8')
    msg.attach(body)

    part = MIMEBase('application', 'zip')
    part.set_payload(zip_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment',
                    filename=('utf-8', '', 'tickets.zip'))
    msg.attach(part)

    with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=60) as server:
        server.login(email_addr, auth_code)
        server.send_message(msg)
