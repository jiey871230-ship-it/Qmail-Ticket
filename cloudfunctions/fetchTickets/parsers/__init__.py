"""解析器模块"""
from parsers.train_12306 import Train12306Parser
from parsers.ctrip import CtripParser
from models import RawEmail

PARSERS = [Train12306Parser(), CtripParser()]


def get_parser(raw_email: RawEmail):
    """根据邮件主题选择解析器"""
    for p in PARSERS:
        if p.can_parse(raw_email):
            return p
    return None
