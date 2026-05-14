"""邮件源工厂"""
from qmail_ticket.sources.base import MailSource
from qmail_ticket.sources.foxmail import FoxmailSource


def get_source(name: str, **kwargs) -> MailSource:
    """根据名称获取邮件源实例。"""
    if name == 'foxmail':
        return FoxmailSource()
    if name == 'imap':
        from qmail_ticket.sources.imap import ImapSource
        return ImapSource(**kwargs)
    raise ValueError(f"未知邮件源: {name}")
