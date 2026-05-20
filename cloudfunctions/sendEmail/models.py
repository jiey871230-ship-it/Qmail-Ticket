"""数据模型"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Ticket:
    """一张票据"""
    travel_date: str       # "2026-04-28"
    carrier: str           # 车次 "G8888" 或航班号 "ZH8848"
    route: str             # "成都东-重庆北"
    amount: float          # 票价
    ticket_type: str       # "火车" / "飞机"
    vehicle: str           # "二等座" / "飞机" / "硬卧"
    item: str              # "票价" / "机票" / "退票费"


@dataclass
class RawEmail:
    """一封原始邮件"""
    source: str            # "imap"
    uid: Optional[bytes]   # IMAP UID
    raw_bytes: bytes       # 原始邮件 bytes
    subject: str           # 解码后的主题
