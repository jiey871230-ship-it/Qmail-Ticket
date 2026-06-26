"""本地测试服务器 — 模拟微信云函数 API"""
import csv
import io
import json
import os
import sys
import uuid
import zipfile
from dataclasses import asdict
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, unquote

# 将 cloud 函数目录加入 path
ROOT = os.path.dirname(os.path.abspath(__file__))
CF_DIR = os.path.join(ROOT, 'cloudfunctions', 'fetchTickets')
sys.path.insert(0, CF_DIR)

import fitz
from PIL import Image
from sources.imap import ImapSource
from parsers import get_parser
from models import Ticket

OUTPUT_DIR = os.path.join(ROOT, 'local_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    """处理 API 请求和静态文件"""

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == '/api/fetchTickets':
            self._handle_fetch(body)
        elif path == '/api/sendEmail':
            self._handle_send_email(body)
        else:
            self._json_response(404, {'error': 'Not found'})

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == '/' or path == '':
            self._serve_file(os.path.join(ROOT, 'preview', 'app.html'), 'text/html')
        elif path.startswith('/output/'):
            file_name = path[len('/output/'):]
            file_path = os.path.join(OUTPUT_DIR, file_name)
            if os.path.exists(file_path):
                ct = 'image/jpeg' if file_name.endswith('.jpg') else \
                     'application/pdf' if file_name.endswith('.pdf') else \
                     'text/csv' if file_name.endswith('.csv') else \
                     'application/octet-stream'
                self._serve_file(file_path, ct)
            else:
                self._json_response(404, {'error': 'File not found'})
        else:
            # 尝试从 preview 目录提供静态文件
            file_path = os.path.join(ROOT, 'preview', path.lstrip('/'))
            if os.path.exists(file_path):
                ct = self.guess_type(file_path)
                self._serve_file(file_path, ct)
            else:
                self._json_response(404, {'error': 'Not found'})

    # ── fetchTickets ──

    def _handle_fetch(self, body):
        email_addr = body.get('email', '')
        code = body.get('code', '')
        start_date = body.get('startDate')
        end_date = body.get('endDate')

        if not email_addr or not code:
            self._json_response(400, {'error': '邮箱和授权码不能为空'})
            return

        task_id = str(uuid.uuid4())[:8]
        task_dir = os.path.join(OUTPUT_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)

        try:
            # 1. IMAP 连接
            from datetime import datetime
            sd = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
            ed = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None

            source = ImapSource(email_addr, code)
            source.connect()
            raw_emails = source.search(sd, ed)
            source.disconnect()

            if not raw_emails:
                self._json_response(200, {
                    'taskId': task_id,
                    'tickets': [],
                    'fileIds': {'jpgs': [], 'csv': '', 'pdf': ''},
                })
                return

            # 2. 逐封解析
            all_tickets = []
            jpg_paths = []

            for raw in raw_emails:
                parser = get_parser(raw)
                if not parser:
                    continue
                results = parser.parse(raw)
                if not results:
                    continue
                for pdf_bytes, pdf_name, tickets in results:
                    # 转 JPG
                    jpg_bytes = _pdf_to_jpg_bytes(pdf_bytes)
                    jpg_name = pdf_name.replace('.pdf', '.jpg')
                    jpg_path = os.path.join(task_dir, jpg_name)
                    with open(jpg_path, 'wb') as f:
                        f.write(jpg_bytes)
                    jpg_paths.append(f'{task_id}/{jpg_name}')

                    # 保存原始 PDF
                    pdf_path = os.path.join(task_dir, pdf_name)
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_bytes)

                    for t in tickets:
                        td = _ticket_to_dict(t)
                        td['jpgFileId'] = f'{task_id}/{jpg_name}'
                        td['pdfFileId'] = f'{task_id}/{pdf_name}'
                        all_tickets.append(td)

            if not all_tickets:
                self._json_response(200, {
                    'taskId': task_id,
                    'tickets': [],
                    'fileIds': {'jpgs': [], 'csv': '', 'pdf': ''},
                })
                return

            # 3. 生成 CSV
            csv_name = 'ticket_summary.csv'
            csv_path = os.path.join(task_dir, csv_name)
            _generate_csv_file(all_tickets, csv_path)

            # 4. 生成 print.pdf
            pdf_name = 'print.pdf'
            pdf_out_path = os.path.join(task_dir, pdf_name)
            _generate_print_pdf_file(jpg_paths, pdf_out_path, task_dir)

            self._json_response(200, {
                'taskId': task_id,
                'tickets': all_tickets,
                'fileIds': {
                    'jpgs': jpg_paths,
                    'csv': f'{task_id}/{csv_name}',
                    'pdf': f'{task_id}/{pdf_name}',
                },
            })

        except Exception as e:
            self._json_response(500, {'error': str(e)})

    # ── sendEmail ──

    def _handle_send_email(self, body):
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email.mime.text import MIMEText
        from email import encoders

        email_addr = body.get('email', '')
        auth_code = body.get('code', '')
        to_address = body.get('toAddress', '')
        file_ids = body.get('fileIds', {})

        if not all([email_addr, auth_code, to_address]):
            self._json_response(400, {'error': '参数不完整'})
            return

        all_file_ids = []
        if file_ids.get('jpgs'):
            all_file_ids.extend(file_ids['jpgs'])
        if file_ids.get('csv'):
            all_file_ids.append(file_ids['csv'])
        if file_ids.get('pdf'):
            all_file_ids.append(file_ids['pdf'])

        if not all_file_ids:
            self._json_response(400, {'error': '没有可发送的文件'})
            return

        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for fid in all_file_ids:
                    fpath = os.path.join(OUTPUT_DIR, fid)
                    if os.path.exists(fpath):
                        zf.write(fpath, os.path.basename(fid))

            msg = MIMEMultipart()
            msg['From'] = email_addr
            msg['To'] = to_address
            msg['Subject'] = '车票管家 - 票据提取结果'
            msg.attach(MIMEText('请查收附件中的票据文件。', 'plain', 'utf-8'))

            part = MIMEBase('application', 'zip')
            part.set_payload(zip_buffer.getvalue())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=('utf-8', '', 'tickets.zip'))
            msg.attach(part)

            with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=30) as server:
                server.login(email_addr, auth_code)
                server.send_message(msg)

            self._json_response(200, {'success': True, 'to': to_address})
        except Exception as e:
            self._json_response(500, {'error': str(e)})

    # ── 工具方法 ──

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _json_response(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path, content_type):
        with open(path, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def guess_type(self, path):
        if path.endswith('.html'):
            return 'text/html'
        if path.endswith('.css'):
            return 'text/css'
        if path.endswith('.js'):
            return 'application/javascript'
        if path.endswith('.json'):
            return 'application/json'
        return 'application/octet-stream'


# ── 文件生成函数 ──

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


def _pdf_to_jpg_bytes(pdf_bytes, dpi=150):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    jpg_bytes = pix.tobytes("jpeg")
    doc.close()
    return jpg_bytes


def _generate_csv_file(all_tickets, path):
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(['乘车日期', '交通工具', '车次/航班', '发到站', '票价'])
    total = 0.0
    for t in sorted(all_tickets, key=lambda x: x['travelDate']):
        w.writerow([t['travelDate'], t['vehicle'], t['carrier'],
                     t['route'], f"{t['amount']:.2f}"])
        total += t['amount']
    w.writerow(['合计', '', '', '', f'{total:.2f}'])
    with open(path, 'wb') as f:
        f.write(output.getvalue().encode('utf-8-sig'))


def _generate_print_pdf_file(jpg_file_ids, out_path, task_dir):
    A4_DPI = 150
    PAGE_W = int(210 / 25.4 * A4_DPI)
    PAGE_H = int(297 / 25.4 * A4_DPI)
    MARGIN = 60
    SPACING = 24

    # 按类型分组：机票行程单 vs 火车票
    train_images = []
    flight_images = []
    for fid in jpg_file_ids:
        fpath = os.path.join(OUTPUT_DIR, fid)
        if os.path.exists(fpath):
            img = Image.open(fpath)
            if '机票' in fid:
                flight_images.append(img)
            else:
                train_images.append(img)

    pages = []

    # 火车票排版：2列4行
    if train_images:
        cols, rows = 2, 4
        per_page = cols * rows
        cell_w = (PAGE_W - 2 * MARGIN - (cols - 1) * SPACING) / cols
        cell_h = (PAGE_H - 2 * MARGIN - (rows - 1) * SPACING) / rows

        for i in range(0, len(train_images), per_page):
            page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
            batch = train_images[i:i + per_page]
            for j, img in enumerate(batch):
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

    # 机票行程单排版：1列3行，横跨整行宽度
    if flight_images:
        cols_f, rows_f = 1, 3
        per_page_f = cols_f * rows_f
        cell_w_f = PAGE_W - 2 * MARGIN
        cell_h_f = (PAGE_H - 2 * MARGIN - (rows_f - 1) * SPACING) / rows_f

        for i in range(0, len(flight_images), per_page_f):
            page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
            batch = flight_images[i:i + per_page_f]
            for j, img in enumerate(batch):
                img_ratio = img.width / img.height
                cell_ratio = cell_w_f / cell_h_f
                if img_ratio > cell_ratio:
                    new_w = cell_w_f
                    new_h = new_w / img_ratio
                else:
                    new_h = cell_h_f
                    new_w = new_h * img_ratio
                img_resized = img.resize((int(new_w), int(new_h)), Image.LANCZOS)
                x = MARGIN + (cell_w_f - new_w) / 2
                y = MARGIN + j * (cell_h_f + SPACING) + (cell_h_f - new_h) / 2
                page.paste(img_resized, (int(x), int(y)))
            pages.append(page)

    if pages:
        for img in pages:
            img.info['dpi'] = (A4_DPI, A4_DPI)
        pdf_buffer = io.BytesIO()
        pages[0].save(pdf_buffer, save_all=True, append_images=pages[1:], format='PDF')
        with open(out_path, 'wb') as f:
            f.write(pdf_buffer.getvalue())


if __name__ == '__main__':
    port = 8080
    server = HTTPServer(('127.0.0.1', port), Handler)
    print(f'本地测试服务已启动: http://localhost:{port}')
    print(f'输出目录: {OUTPUT_DIR}')
    print('按 Ctrl+C 停止')
    server.serve_forever()
