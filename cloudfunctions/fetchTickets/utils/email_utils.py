"""邮件附件提取工具"""
import base64
import io
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


def extract_ctrip_pdfs(msg: EmailMessage) -> tuple[list, str | None]:
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
