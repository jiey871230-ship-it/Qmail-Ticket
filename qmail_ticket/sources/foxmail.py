"""Foxmail 本地邮件源"""
import glob
import os
import re
import subprocess
import sys
from datetime import datetime

from qmail_ticket.models import RawEmail
from qmail_ticket.sources.base import MailSource

FOXMAIL_PROFILES = os.path.expanduser(
    "~/Library/Containers/com.tencent.Foxmail/Data/Library/Foxmail/Profiles"
)

# Base64 编码的邮件主题（用于 grep 搜索）
_SUBJECT_12306_B64 = "zfjJz7m6xrHPtc2zLbXn19O3osaxzajWqg=="
_SUBJECT_CTRIP_B64 = "5pC656iLOiDnlLXlrZDmiqXplIDlh63or4E=="


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
        pass

    def search(self, start_date=None, end_date=None) -> list[RawEmail]:
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
                    print(f"  搜索出错: {e}", file=sys.stderr)

        if start_date or end_date:
            train_files = _filter_by_date(train_files, start_date, end_date, "12306")
            flight_files = _filter_by_date(flight_files, start_date, end_date, "携程")

        results = []
        for filepath in train_files + flight_files:
            try:
                with open(filepath, 'rb') as f:
                    raw_bytes = f.read()
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
