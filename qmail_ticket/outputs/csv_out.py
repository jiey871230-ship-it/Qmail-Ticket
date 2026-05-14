"""CSV 汇总表输出器"""
import csv
import os

from qmail_ticket.models import Ticket
from qmail_ticket.outputs.base import OutputWriter


class CsvWriter(OutputWriter):
    """生成 CSV 汇总表"""

    def write(self, tickets: list[Ticket], context: dict) -> None:
        output_dir = context['output_dir']
        jpg_paths = context.get('jpg_paths', [])
        csv_path = os.path.join(output_dir, "ticket_summary.csv")

        jpg_set = {os.path.splitext(os.path.basename(j))[0] for j in jpg_paths}

        verified, unmatched = [], []
        for t in tickets:
            suffix = "-机票" if t.ticket_type == '飞机' else ""
            expected = f"{t.travel_date}-{t.route}{suffix}"
            if expected in jpg_set:
                verified.append(t)
            else:
                unmatched.append(t)

        verified.sort(key=lambda x: (x.travel_date, x.ticket_type))

        # 终端输出
        header = f"  {'乘车日期':<12} {'交通工具':<10} {'车次/航班':<10} {'发到站':<20} {'票价':>8}"
        sep = f"  {'-'*12} {'-'*10} {'-'*10} {'-'*20} {'-'*8}"
        print(f"\n{header}\n{sep}")

        total = 0.0
        for t in verified:
            print(f"  {t.travel_date:<12} {t.vehicle:<10} {t.carrier:<10} {t.route:<20} {t.amount:>8.2f}")
            total += t.amount
        print(f"{sep}")
        print(f"  {'合计':<12} {'':<10} {'':<10} {'':<20} {total:>8.2f}")

        if unmatched:
            print(f"\n  !! {len(unmatched)} 条未匹配:")
            for t in unmatched:
                print(f"     {t.travel_date}-{t.route}")

        # 写 CSV
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['乘车日期', '交通工具', '车次/航班', '发到站', '票价'])
            for t in verified:
                w.writerow([t.travel_date, t.vehicle, t.carrier, t.route, f"{t.amount:.2f}"])
            w.writerow(['合计', '', '', '', f"{total:.2f}"])

        print(f"\n  汇总表: {csv_path}  (共 {len(verified)} 条, 合计 ¥{total:.2f})")
