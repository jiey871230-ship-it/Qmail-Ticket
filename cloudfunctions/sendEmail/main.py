"""sendEmail 云函数主入口"""
import io
import zipfile
import smtplib
import tempfile
import os
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders


def main(event, context):
    """打包所有文件为 ZIP 并通过 SMTP 发送"""
    email_addr = event['email']
    auth_code = event['code']
    to_address = event['toAddress']
    file_ids = event['fileIds']  # {jpgs: [...], csv: '...', pdf: '...'}

    # 1. 收集所有文件 ID
    all_file_ids = []
    if file_ids.get('jpgs'):
        all_file_ids.extend(file_ids['jpgs'])
    if file_ids.get('csv'):
        all_file_ids.append(file_ids['csv'])
    if file_ids.get('pdf'):
        all_file_ids.append(file_ids['pdf'])

    if not all_file_ids:
        return {'success': False, 'error': '没有可发送的文件'}

    # 2. 从云存储下载并打包为 ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fid in all_file_ids:
            try:
                data, name = _download_file(fid)
                zf.writestr(name, data)
            except Exception as e:
                continue

    zip_bytes = zip_buffer.getvalue()

    # 3. 构建邮件
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

    # 4. SMTP 发送
    with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=30) as server:
        server.login(email_addr, auth_code)
        server.send_message(msg)

    return {'success': True, 'to': to_address}


def _download_file(file_id):
    """从云存储下载文件，返回 (bytes, filename)"""
    from wechatcloudbase import tcb
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.tmp')
    tmp.close()
    tcb.download_file(file_id, tmp.name)
    with open(tmp.name, 'rb') as f:
        data = f.read()
    os.unlink(tmp.name)
    name = file_id.split('/')[-1]
    return data, name
