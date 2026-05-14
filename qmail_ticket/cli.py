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
    start_s = args.start
    end_s = args.end

    if args.source == 'foxmail' and not start_s:
        start_s = input("  起始日期 (YYYY-MM-DD, 回车跳过): ").strip() or None
    if args.source == 'foxmail' and not end_s:
        end_s = input("  截止日期 (YYYY-MM-DD, 回车跳过): ").strip() or None

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
