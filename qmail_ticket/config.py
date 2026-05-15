"""配置文件管理模块"""
import json
import os

CONFIG_DIR = os.path.expanduser("~/.qmail-ticket")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def get_config_path() -> str:
    """获取配置文件路径"""
    return CONFIG_FILE


def load_config() -> dict:
    """加载配置文件，不存在则返回空字典"""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_config(config: dict) -> None:
    """保存配置文件"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_imap_config() -> dict | None:
    """获取 IMAP 配置，不存在则返回 None"""
    config = load_config()
    imap_config = config.get('imap', {})
    if imap_config.get('email') and imap_config.get('code'):
        return imap_config
    return None


def save_imap_config(email: str, code: str) -> None:
    """保存 IMAP 配置"""
    config = load_config()
    config['imap'] = {
        'email': email,
        'code': code
    }
    save_config(config)
