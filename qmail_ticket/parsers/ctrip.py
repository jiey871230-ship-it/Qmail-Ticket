"""携程机票解析器"""
import email.policy
import quopri
import re
from email import message_from_bytes

from qmail_ticket.models import RawEmail, Ticket
from qmail_ticket.email_utils import extract_ctrip_pdfs
from qmail_ticket.pdf_utils import pdf_to_text
from qmail_ticket.parsers.base import TicketParser


class CtripParser(TicketParser):
    """携程机票解析器"""

    def can_parse(self, raw_email: RawEmail) -> bool:
        return "携程" in raw_email.subject

    def parse(self, raw_email: RawEmail) -> list[tuple[bytes, str, list[Ticket]]]:
        msg = message_from_bytes(raw_email.raw_bytes, policy=email.policy.default)
        pdf_list, html_text = extract_ctrip_pdfs(msg)
        if not pdf_list:
            return []

        results = []
        text_results = []
        img_pdfs = []

        for pdf_data in pdf_list:
            text = pdf_to_text(pdf_data)
            if text.strip():
                tickets = _parse_ctrip_pdf_text(text)
                if tickets:
                    text_results.append((pdf_data, tickets))
                else:
                    img_pdfs.append(pdf_data)
            else:
                img_pdfs.append(pdf_data)

        if text_results:
            for pdf_data, tickets in text_results:
                for t in tickets:
                    safe_date = t.travel_date.replace('/', '-')
                    safe_station = t.route.replace('/', '-').replace('\\', '-')
                    pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                    results.append((pdf_data, pdf_name, [t]))
            return results

        # 全部是图片型 PDF → HTML 回退
        if img_pdfs and html_text:
            html_tickets = _parse_ctrip_html(html_text)
            for i, pdf_data in enumerate(img_pdfs):
                if i < len(html_tickets):
                    t = html_tickets[i]
                    safe_date = t.travel_date.replace('/', '-')
                    safe_station = t.route.replace('/', '-').replace('\\', '-')
                    pdf_name = f"{safe_date}-{safe_station}-机票.pdf"
                    results.append((pdf_data, pdf_name, [t]))

        return results


def _parse_ctrip_pdf_text(text: str) -> list[Ticket]:
    """从携程 PDF 文本提取机票信息。"""
    tickets = []

    total = 0.0
    total_m = re.search(r'合计.*CNY\s*(\d+\.?\d*)', text, re.DOTALL)
    if total_m:
        total = float(total_m.group(1))

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    zi_idx = None
    for i, line in enumerate(lines):
        if line == '自:':
            zi_idx = i
            break
    if zi_idx is None:
        return tickets

    label_count = 1
    for j in range(zi_idx + 1, len(lines)):
        if lines[j] == '至:':
            label_count += 1
        else:
            break

    value_start = zi_idx + label_count
    values = []
    for j in range(value_start, min(value_start + 10, len(lines))):
        v = lines[j]
        if v.endswith(':') and len(v) <= 5:
            break
        values.append(v)

    if len(values) < 5:
        return tickets

    from_city = _clean_city(values[0])
    to_city = ''
    for v in reversed(values):
        if re.search(r'[一-鿿]', v):
            to_city = _clean_city(v)
            break
    if not to_city:
        return tickets

    flight_no = ''
    for v in values:
        vc = re.sub(r'\s+', '', v)
        if re.match(r'^(?=.*[A-Z])[A-Z0-9]{4,7}$', vc):
            flight_no = vc
            break

    travel_date = ''
    for v in values:
        dm = re.search(r'(\d{4})年(\d{2})月(\d{2})日', v)
        if dm:
            travel_date = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
            break

    route = f"{from_city}-{to_city}"
    if not travel_date or not route:
        return tickets

    tickets.append(Ticket(
        travel_date=travel_date,
        carrier=flight_no or _find_ctrip_flight(text),
        route=route,
        amount=total,
        ticket_type='飞机',
        vehicle='飞机',
        item='机票',
    ))
    return tickets


def _clean_city(city: str) -> str:
    """清理城市名: 去掉机场/航站楼信息。"""
    city = re.sub(r'\s*T\d+\s*$', '', city)
    parts = city.split()
    if parts and re.search(r'[一-鿿]', parts[0]):
        return parts[0]
    return city.strip()


def _find_ctrip_flight(text: str) -> str:
    """从文本中找航班号。"""
    for v in text.split('\n'):
        vc = v.strip()
        if re.match(r'^(?=.*[A-Z])[A-Z0-9]{4,7}$', vc):
            return vc
    m = re.search(r'承运人[:\s]*(.+?)(?:\n|$)', text)
    return m.group(1).strip() if m else '航班'


def _parse_ctrip_html(html_text: str) -> list[Ticket]:
    """从携程 HTML 正文回退解析机票信息。"""
    tickets = []
    try:
        decoded = quopri.decodestring(html_text.encode('latin-1')).decode('utf-8', errors='replace')
    except Exception:
        decoded = html_text

    pattern = r'订单号[：:](\d+)[，,]\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*([一-鿿]+-[一-鿿]+)'
    for m in re.finditer(pattern, decoded):
        travel_date = f"{m.group(2)}-{m.group(3).zfill(2)}-{m.group(4).zfill(2)}"
        route = m.group(5)
        order_id = m.group(1)[-6:]
        tickets.append(Ticket(
            travel_date=travel_date,
            carrier=f'订单{order_id}',
            route=route,
            amount=0.0,
            ticket_type='飞机',
            vehicle='飞机',
            item='机票',
        ))
    return tickets
