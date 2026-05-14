#!/usr/bin/env python3
"""
QQ邮箱 IMAP 版 12306 + 携程 电子发票 / 报销凭证提取工具

通过 IMAP 从 QQ邮箱 搜索并下载电子发票/报销凭证邮件，
解析 PDF 票面内容，转为 JPG，输出汇总表 (CSV) 和 print.pdf。

用法:
    python3 ticket_imap.py [--email user@qq.com] [--code 授权码] [--start YYYY-MM-DD] [--end YYYY-MM-DD]

依赖: pip3 install --break-system-packages PyMuPDF Pillow
"""

import argparse
import email.header
import email.policy
import imaplib
import os
import re
import sys
from datetime import datetime, timedelta
from email import message_from_bytes

# ============ 导入 ticket.py 的公共函数 ============

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from ticket import (
    extract_12306_pdf,
    extract_ctrip_pdfs,
    parse_12306_pdf_text,
    parse_ctrip_pdf_text,
    _parse_ctrip_html,
    _pdf_to_text,
    pdf_to_jpg,
    write_summary,
    create_print_pdf,
)

# ============ 配置 ============

IMAP_SERVER = "imap.qq.com"
IMAP_PORT = 993
JPG_DPI = 200

# 搜索关键词（解码后的主题）
SUBJECT_12306 = "网上购票系统"
SUBJECT_CTRIP = "携程"


# ============ 工具函数 ============

def parse_date_arg(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d") if s else None


def decode_subject_from_header(raw_bytes):
    """
    从 IMAP FETCH 返回的原始 header bytes 中解码 Subject。
    raw_bytes 可能是 b'Subject: =?GBK?B?...?=\r\n' 或 b'Subject: 网上购票系统\r\n'
    """
    text = raw_bytes.decode('utf-8', errors='replace')
    m = re.search(r'Subject:\s*(.+?)(?:\r?\n\s*\r?\n|\r?\n$|$)', text, re.DOTALL)
    if not m:
        return ''
    subject_raw = m.group(1).strip()
    # 如果是 RFC 2047 编码（如 =?UTF-8?B?...?=），用 decode_header 解码
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


# ============ IMAP 操作 ============

def connect_imap(email_addr, auth_code):
    """连接 QQ邮箱 IMAP。"""
    conn = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    conn.login(email_addr, auth_code)
    print(f"  登录成功: {email_addr}")
    return conn


def search_target_uids(conn, start_date=None, end_date=None):
    """
    搜索 12306 和携程的邮件。
    方法：按日期范围获取所有邮件 UID，逐封读取 Subject 头，客户端过滤。
    返回 (train_uids, flight_uids)。
    """
    conn.select('INBOX')

    # 构建日期搜索条件
    criteria = 'ALL'
    if start_date:
        criteria = f'SINCE {start_date.strftime("%d-%b-%Y")}'
    if end_date:
        criteria += f' BEFORE {(end_date + timedelta(days=1)).strftime("%d-%b-%Y")}'

    _, data = conn.uid('SEARCH', criteria)
    all_uids = data[0].split() if data[0] else []

    if not all_uids:
        return [], []

    print(f"  扫描 {len(all_uids)} 封邮件的主题...")
    train_uids, flight_uids = [], []

    for raw_uid in all_uids:
        _, hdr_data = conn.uid('FETCH', raw_uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
        if not hdr_data or not hdr_data[0]:
            continue

        # 从 FETCH 响应提取 header bytes
        raw_bytes = None
        for part in hdr_data:
            if isinstance(part, tuple):
                raw_bytes = part[1]
                break

        if raw_bytes is None:
            continue

        decoded = decode_subject_from_header(raw_bytes)
        if SUBJECT_12306 in decoded:
            train_uids.append(raw_uid)
        elif SUBJECT_CTRIP in decoded:
            flight_uids.append(raw_uid)

    return train_uids, flight_uids


def fetch_raw(conn, uid):
    """下载指定 UID 的完整邮件原始 bytes。"""
    _, data = conn.uid('FETCH', uid, '(RFC822)')
    if data and data[0]:
        return data[0][1]
    return None


# ============ 邮件处理 ============

def process_12306_raw(raw_bytes):
    """处理 IMAP 下载的 12306 邮件。"""
    msg = message_from_bytes(raw_bytes, policy=email.policy.default)
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


def process_ctrip_raw(raw_bytes):
    """处理 IMAP 下载的携程邮件（支持多 PDF 附件）。"""
    msg = message_from_bytes(raw_bytes, policy=email.policy.default)
    pdf_list, html_text = extract_ctrip_pdfs(msg)
    if not pdf_list:
        return []

    results = []
    text_results = []
    img_pdfs = []

    for pdf_data in pdf_list:
        text = _pdf_to_text(pdf_data)
        if text.strip():
            tickets = parse_ctrip_pdf_text(text)
            if tickets:
                text_results.append((pdf_data, tickets))
            else:
                img_pdfs.append(pdf_data)
        else:
            img_pdfs.append(pdf_data)

    if text_results:
        for pdf_data, tickets in text_results:
            for t in tickets:
                safe_date = t['travel_date'].replace('/', '-')
                safe_station = t['station'].replace('/', '-').replace('\\', '-')
                pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                results.append((pdf_data, pdf_name, [t]))
        return results

    # 全部是图片型 PDF → HTML 回退
    if img_pdfs and html_text:
        html_tickets = _parse_ctrip_html(html_text)
        for i, pdf_data in enumerate(img_pdfs):
            if i < len(html_tickets):
                t = html_tickets[i]
                safe_date = t['travel_date'].replace('/', '-')
                safe_station = t['station'].replace('/', '-').replace('\\', '-')
                pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                results.append((pdf_data, pdf_name, [t]))

    return results


# ============ 主流程 ============

def parse_args():
    p = argparse.ArgumentParser(
        description="QQ邮箱 IMAP 版 12306 + 携程 电子发票/报销凭证提取工具"
    )
    p.add_argument("--email", help="QQ邮箱地址")
    p.add_argument("--code", help="QQ邮箱授权码（非登录密码，需在邮箱设置中生成）")
    p.add_argument("--start", help="起始日期 (YYYY-MM-DD)")
    p.add_argument("--end", help="截止日期 (YYYY-MM-DD)")
    return p.parse_args()


def main():
    print("=" * 60)
    print("  QQ邮箱 IMAP 版 车票提取工具")
    print("  (需要 QQ邮箱 授权码，非登录密码)")
    print("=" * 60)

    args = parse_args()
    email_addr = args.email or input("  QQ邮箱: ").strip()
    auth_code = args.code or input("  授权码: ").strip()
    start_s = args.start or input("  起始日期 (YYYY-MM-DD, 回车跳过): ").strip()
    end_s = args.end or input("  截止日期 (YYYY-MM-DD, 回车跳过): ").strip()

    start_date = parse_date_arg(start_s) if start_s else None
    end_date = parse_date_arg(end_s) if end_s else None
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    if start_date or end_date:
        print(f"  筛选范围: {start_s or '不限'} ~ {end_s or '不限'}")

    # [1] 连接并搜索
    print("\n[1/5] 连接 QQ邮箱 IMAP...")
    conn = connect_imap(email_addr, auth_code)
    train_uids, flight_uids = search_target_uids(conn, start_date, end_date)
    print(f"  12306 火车票: {len(train_uids)} 封")
    print(f"  携程   机票: {len(flight_uids)} 封")
    if not train_uids and not flight_uids:
        conn.logout()
        print("  未找到目标邮件，退出。")
        return

    # [2] 下载并解析（保持同一个连接，INBOX 已经是 SELECTED 状态）
    all_results = []

    for label, uids, processor in [
        ("12306 火车票", train_uids, process_12306_raw),
        ("携程 机票", flight_uids, process_ctrip_raw),
    ]:
        if not uids:
            continue
        print(f"\n[2/5] 下载并解析 {label} ({len(uids)} 封)...")
        fail = 0
        for uid in uids:
            raw = fetch_raw(conn, uid)
            if raw is None:
                fail += 1
                continue
            results = processor(raw)
            if not results:
                fail += 1
            else:
                for r in results:
                    all_results.append(r)
                    tag = "机票" if "机票" in r[1] else "火车"
                    print(f"  [{tag}] {r[1]}")
        success = len(uids) - fail
        print(f"  成功: {success}, 跳过: {fail}")

    conn.logout()

    if not all_results:
        print("  没有可提取的附件，退出。")
        return

    # [3] PDF -> JPG
    print(f"\n[3/5] 转换 PDF 为 JPG ({JPG_DPI} DPI)...")
    jpg_count = 0
    jpg_files = []
    for pdf_data, pdf_name, _ in all_results:
        jpg_path = os.path.join(SCRIPT_DIR, os.path.splitext(pdf_name)[0] + ".jpg")
        try:
            pdf_to_jpg(pdf_data, jpg_path)
            jpg_files.append(jpg_path)
            jpg_count += 1
        except Exception as e:
            print(f"  {pdf_name} 转换失败: {e}", file=sys.stderr)
    print(f"  成功转换: {jpg_count}")

    # [4] 汇总
    print(f"\n[4/5] 验证并生成汇总表...")
    all_tickets = []
    for _, _, tickets in all_results:
        all_tickets.extend(tickets)
    write_summary(all_tickets, jpg_files)

    # [5] 生成 print.pdf
    print(f"\n[5/5] 生成 print.pdf...")
    create_print_pdf(all_tickets, SCRIPT_DIR)

    # 完成
    print(f"\n[5/5] 完成!")
    print(f"  JPG 文件: {jpg_count} 个 -> {SCRIPT_DIR}")
    print("=" * 60)


if __name__ == '__main__':
    main()
