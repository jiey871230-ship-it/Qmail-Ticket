"""邮件源模块"""
from .base import MailSource
from .imap import ImapSource

__all__ = ['MailSource', 'ImapSource']
