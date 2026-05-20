"""fetchTickets 云函数主入口

职责：IMAP 连接 + 邮件解析
只返回票据元数据，不返回文件
"""
from sources.imap import ImapSource
from parsers import get_parser


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


def main(event, context):
    """云函数入口"""
    email = event['email']
    code = event['code']
    start_date = _parse_date(event.get('startDate'))
    end_date = _parse_date(event.get('endDate'))

    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)

    try:
        source = ImapSource(email, code)
        source.connect()
        raw_emails = source.search(start_date, end_date)
        source.disconnect()

        if not raw_emails:
            return {'tickets': [], 'summary': {'count': 0, 'totalAmount': 0}}

        all_tickets = []
        for raw in raw_emails:
            parser = get_parser(raw)
            if not parser:
                continue
            results = parser.parse(raw)
            if not results:
                continue
            for pdf_bytes, pdf_name, tickets in results:
                for t in tickets:
                    all_tickets.append(_ticket_to_dict(t))

        total_amount = sum(t['amount'] for t in all_tickets)

        return {
            'tickets': all_tickets,
            'summary': {
                'count': len(all_tickets),
                'totalAmount': round(total_amount, 2),
            },
        }

    except Exception as e:
        return {'error': str(e), 'tickets': [], 'summary': {'count': 0, 'totalAmount': 0}}


def _parse_date(s):
    if not s:
        return None
    from datetime import datetime
    return datetime.strptime(s.strip(), "%Y-%m-%d")
