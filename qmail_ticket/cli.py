"""CLI 入口"""
import os
import sys
from datetime import datetime

from qmail_ticket.sources import get_source
from qmail_ticket.parsers import get_parser
from qmail_ticket.outputs import WRITERS

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')


def parse_date_arg(s: str) -> datetime | None:
    return datetime.strptime(s.strip(), "%Y-%m-%d") if s else None


def show_menu() -> str:
    """显示菜单，返回用户选择 ('foxmail' 或 'imap')"""
    print()
    print("请选择邮件源：")
    print("  1. Foxmail 本地邮件")
    print("     - 自动扫描本地 Foxmail 邮件")
    print("     - 无需登录，直接提取")
    print()
    print("  2. QQ邮箱 IMAP (默认)")
    print("     - 通过 IMAP 协议连接 QQ邮箱")
    print("     - 需要邮箱地址和授权码")
    print()

    while True:
        choice = input("请输入选项 (1/2, 直接回车选择 2): ").strip()
        if choice == '' or choice == '2':
            return 'imap'
        elif choice == '1':
            return 'foxmail'
        else:
            print("  无效选项，请输入 1 或 2")


def main():
    print("=" * 60)
    print("  12306 + 携程 电子发票 / 报销凭证提取工具")
    print("=" * 60)

    # 显示菜单，获取用户选择
    source_choice = show_menu()

    # 获取登录信息（如果需要）
    source_kwargs = {}
    if source_choice == 'imap':
        from qmail_ticket.config import get_imap_config, save_imap_config

        # 检查是否有保存的配置
        imap_config = get_imap_config()
        if imap_config:
            print(f"\n  使用已保存的配置: {imap_config['email']}")
            source_kwargs = {
                'email': imap_config['email'],
                'code': imap_config['code']
            }
        else:
            # 提示用户输入
            print("\n  首次使用 IMAP，请输入登录信息：")
            email_addr = input("  QQ邮箱: ").strip()
            auth_code = input("  授权码: ").strip()

            if not email_addr or not auth_code:
                print("  错误: imap 源需要邮箱地址和授权码", file=sys.stderr)
                sys.exit(1)

            # 保存配置
            save_imap_config(email_addr, auth_code)
            print("  登录信息已保存到 ~/.qmail-ticket/config.json")

            source_kwargs = {
                'email': email_addr,
                'code': auth_code
            }

    # 获取日期范围
    print()
    start_s = input("  起始日期 (YYYY-MM-DD, 回车跳过): ").strip() or None
    end_s = input("  截止日期 (YYYY-MM-DD, 回车跳过): ").strip() or None

    start_date = parse_date_arg(start_s) if start_s else None
    end_date = parse_date_arg(end_s) if end_s else None
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    if start_date or end_date:
        print(f"  筛选范围: {start_s or '不限'} ~ {end_s or '不限'}")

    # [1] 连接并搜索
    print(f"\n[1/4] 连接 {source_choice}...")

    source = get_source(source_choice, **source_kwargs)
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

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    context = {
        'output_dir': OUTPUT_DIR,
        'pdf_data_list': pdf_data_list,
    }
    for writer in WRITERS:
        writer.write(all_tickets, context)

    # [4] 完成
    print(f"\n[4/4] 完成!")
    print("=" * 60)
