"""邮件源抽象基类"""
from abc import ABC, abstractmethod

from ..models import RawEmail


class MailSource(ABC):
    @abstractmethod
    def connect(self, **kwargs) -> None:
        """建立连接"""

    @abstractmethod
    def search(self, start_date=None, end_date=None) -> list:
        """搜索目标邮件，返回原始邮件列表"""

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
