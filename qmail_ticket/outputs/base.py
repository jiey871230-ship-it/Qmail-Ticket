"""输出器抽象基类"""
from abc import ABC, abstractmethod

from qmail_ticket.models import Ticket


class OutputWriter(ABC):
    @abstractmethod
    def write(self, tickets: list[Ticket], context: dict) -> None:
        """输出结果"""
