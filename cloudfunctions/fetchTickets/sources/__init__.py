"""邮件源模块"""
from sources.base import MailSource
from sources.imap import ImapSource

__all__ = ['MailSource', 'ImapSource']
