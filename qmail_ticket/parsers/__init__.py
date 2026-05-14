"""解析器工厂"""
from qmail_ticket.models import RawEmail
from qmail_ticket.parsers.base import TicketParser
from qmail_ticket.parsers.train_12306 import Train12306Parser
from qmail_ticket.parsers.ctrip import CtripParser

PARSERS: list[TicketParser] = [Train12306Parser(), CtripParser()]


def get_parser(raw_email: RawEmail) -> TicketParser | None:
    """根据邮件内容匹配解析器。"""
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
