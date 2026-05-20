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


def _ticket_to_dict(t):
    """Ticket dataclass → camelCase dict"""
    return {
        'travelDate': t.travel_date,
        'carrier': t.carrier,
        'route': t.route,
        'amount': t.amount,
        'ticketType': t.ticket_type,
        'vehicle': t.vehicle,
        'item': t.item,
    }


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
                    ticket_dict = _ticket_to_dict(t)
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
