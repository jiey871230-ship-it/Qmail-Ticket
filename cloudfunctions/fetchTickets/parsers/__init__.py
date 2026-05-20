"""解析器模块"""
from .train_12306 import Train12306Parser
from .ctrip import CtripParser
from ..models import RawEmail

PARSERS = [Train12306Parser(), CtripParser()]


def get_parser(raw_email: RawEmail):
    """根据邮件主题选择解析器"""
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
