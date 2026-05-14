"""IMAP 通用邮件源（QQ邮箱/Gmail/Outlook）"""
import email.header
import imaplib
import re
from datetime import timedelta

from qmail_ticket.models import RawEmail
from qmail_ticket.sources.base import MailSource

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
