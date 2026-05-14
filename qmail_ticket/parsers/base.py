"""票面解析器抽象基类"""
from abc import ABC, abstractmethod

from qmail_ticket.models import RawEmail, Ticket


class TicketParser(ABC):
    @abstractmethod
    def can_parse(self, raw_email: RawEmail) -> bool:
        """判断是否能解析此邮件"""

    @abstractmethod
    def parse(self, raw_email: RawEmail) -> list[tuple[bytes, str, list[Ticket]]]:
        """解析邮件，返回 [(pdf_bytes, pdf_name, [ticket, ...]), ...]"""
