# 交互式菜单和配置管理实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 改善用户体验，添加交互式菜单、记住登录信息、优化输出目录结构

**架构：** 新增配置管理模块，修改 CLI 入口添加交互式菜单，修改输出模块支持新目录结构

**技术栈：** Python 3.10+、json（标准库）、os（标准库）

---

## 文件清单

| 文件 | 职责 | 操作 |
|------|------|------|
| `qmail_ticket/config.py` | 配置文件读写管理 | 新增 |
| `qmail_ticket/cli.py` | CLI 入口，添加交互式菜单 | 修改 |
| `qmail_ticket/outputs/jpg_out.py` | JPG 输出，修改输出目录 | 修改 |
| `qmail_ticket/outputs/csv_out.py` | CSV 输出，修改输出目录 | 修改 |
| `qmail_ticket/outputs/print_pdf.py` | PDF 输出，修改输出目录 | 修改 |

---

### 任务 1：配置管理模块

**文件：**
- 创建：`qmail_ticket/config.py`

- [ ] **步骤 1：创建配置管理模块**

```python
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
```

- [ ] **步骤 2：验证导入**

```bash
python3 -c "from qmail_ticket.config import get_config_path, load_config, save_config, get_imap_config, save_imap_config; print('OK')"
```

预期：`OK`

- [ ] **步骤 3：Commit**

```bash
git add qmail_ticket/config.py
git commit -m "feat: 添加配置管理模块"
```

---

### 任务 2：交互式菜单

**文件：**
- 修改：`qmail_ticket/cli.py`

- [ ] **步骤 1：添加菜单显示函数**

在 `cli.py` 中添加以下函数：

```python
def show_menu() -> str:
    """显示菜单，返回用户选择 ('foxmail' 或 'imap')"""
    print()
    print("请选择邮件源：")
    print("  1. Foxmail 本地邮件")
    print("     - 自动扫描本地 Foxmail 邮件")
    print("     - 无需登录，直接提取")
    print()
    print("  2. QQ邮箱 IMAP (默认)")
    print("     - 通过 IMAP 协议连接 QQ邮箱")
    print("     - 需要邮箱地址和授权码")
    print()

    while True:
        choice = input("请输入选项 (1/2, 直接回车选择 2): ").strip()
        if choice == '' or choice == '2':
            return 'imap'
        elif choice == '1':
            return 'foxmail'
        else:
            print("  无效选项，请输入 1 或 2")
```

- [ ] **步骤 2：修改 main 函数**

修改 `cli.py` 中的 `main` 函数，集成菜单和配置管理：

```python
def main():
    print("=" * 60)
    print("  12306 + 携程 电子发票 / 报销凭证提取工具")
    print("=" * 60)

    # 显示菜单，获取用户选择
    source_choice = show_menu()

    # 获取登录信息（如果需要）
    source_kwargs = {}
    if source_choice == 'imap':
        from qmail_ticket.config import get_imap_config, save_imap_config

        # 检查是否有保存的配置
        imap_config = get_imap_config()
        if imap_config:
            print(f"\n  使用已保存的配置: {imap_config['email']}")
            source_kwargs = {
                'email': imap_config['email'],
                'code': imap_config['code']
            }
        else:
            # 提示用户输入
            print("\n  首次使用 IMAP，请输入登录信息：")
            email_addr = input("  QQ邮箱: ").strip()
            auth_code = input("  授权码: ").strip()

            if not email_addr or not auth_code:
                print("  错误: imap 源需要邮箱地址和授权码", file=sys.stderr)
                sys.exit(1)

            # 保存配置
            save_imap_config(email_addr, auth_code)
            print("  登录信息已保存到 ~/.qmail-ticket/config.json")

            source_kwargs = {
                'email': email_addr,
                'code': auth_code
            }

    # 获取日期范围
    print()
    start_s = input("  起始日期 (YYYY-MM-DD, 回车跳过): ").strip() or None
    end_s = input("  截止日期 (YYYY-MM-DD, 回车跳过): ").strip() or None

    start_date = parse_date_arg(start_s) if start_s else None
    end_date = parse_date_arg(end_s) if end_s else None
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    if start_date or end_date:
        print(f"  筛选范围: {start_s or '不限'} ~ {end_s or '不限'}")

    # [1] 连接并搜索
    print(f"\n[1/4] 连接 {source_choice}...")

    source = get_source(source_choice, **source_kwargs)
    source.connect()
    raw_emails = source.search(start_date, end_date)
    source.disconnect()

    print(f"  找到 {len(raw_emails)} 封目标邮件")
    if not raw_emails:
        print("  未找到目标邮件，退出。")
        return

    # [2] 解析票面
    print(f"\n[2/4] 解析票面...")
    all_tickets = []
    pdf_data_list = []

    for raw in raw_emails:
        parser = get_parser(raw)
        if not parser:
            continue
        results = parser.parse(raw)
        if not results:
            continue
        for pdf_bytes, pdf_name, tickets in results:
            all_tickets.extend(tickets)
            pdf_data_list.append((pdf_bytes, pdf_name))
            tag = "机票" if "机票" in pdf_name else "火车"
            print(f"  [{tag}] {pdf_name}")

    print(f"  成功解析: {len(all_tickets)} 张票据")
    if not all_tickets:
        print("  没有可提取的附件，退出。")
        return

    # [3] 输出
    print(f"\n[3/4] 输出结果...")
    context = {
        'output_dir': OUTPUT_DIR,
        'pdf_data_list': pdf_data_list,
    }
    for writer in WRITERS:
        writer.write(all_tickets, context)

    # [4] 完成
    print(f"\n[4/4] 完成!")
    print("=" * 60)
```

- [ ] **步骤 3：验证 CLI 帮助**

```bash
python3 -m qmail_ticket --help
```

预期：显示帮助信息（注意：由于修改了 main 函数，--help 可能不再有效，这是预期的）

- [ ] **步骤 4：Commit**

```bash
git add qmail_ticket/cli.py
git commit -m "feat: 添加交互式菜单和配置管理"
```

---

### 任务 3：修改输出目录

**文件：**
- 修改：`qmail_ticket/cli.py`
- 修改：`qmail_ticket/outputs/jpg_out.py`
- 修改：`qmail_ticket/outputs/csv_out.py`
- 修改：`qmail_ticket/outputs/print_pdf.py`

- [ ] **步骤 1：修改 cli.py 中的 OUTPUT_DIR**

修改 `cli.py` 中的 `OUTPUT_DIR` 常量：

```python
# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
```

- [ ] **步骤 2：在 main 函数中创建输出目录**

在 `main` 函数的输出部分之前，添加目录创建逻辑：

```python
    # [3] 输出
    print(f"\n[3/4] 输出结果...")

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    context = {
        'output_dir': OUTPUT_DIR,
        'pdf_data_list': pdf_data_list,
    }
```

- [ ] **步骤 3：验证输出目录创建**

```bash
python3 -c "
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath('.'))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f'OUTPUT_DIR: {OUTPUT_DIR}')
print(f'EXISTS: {os.path.exists(OUTPUT_DIR)}')
"
```

预期：输出目录创建成功

- [ ] **步骤 4：Commit**

```bash
git add qmail_ticket/cli.py
git commit -m "feat: 修改输出目录到 output 文件夹"
```

---

### 任务 4：移除命令行参数（可选）

**文件：**
- 修改：`qmail_ticket/cli.py`

- [ ] **步骤 1：移除 argparse 相关代码**

由于我们现在使用交互式菜单，可以移除 argparse 相关代码：

```python
"""CLI 入口"""
import os
import sys
from datetime import datetime

from qmail_ticket.sources import get_source
from qmail_ticket.parsers import get_parser
from qmail_ticket.outputs import WRITERS

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 输出目录
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')


def parse_date_arg(s: str) -> datetime | None:
    return datetime.strptime(s.strip(), "%Y-%m-%d") if s else None


def show_menu() -> str:
    """显示菜单，返回用户选择 ('foxmail' 或 'imap')"""
    print()
    print("请选择邮件源：")
    print("  1. Foxmail 本地邮件")
    print("     - 自动扫描本地 Foxmail 邮件")
    print("     - 无需登录，直接提取")
    print()
    print("  2. QQ邮箱 IMAP (默认)")
    print("     - 通过 IMAP 协议连接 QQ邮箱")
    print("     - 需要邮箱地址和授权码")
    print()

    while True:
        choice = input("请输入选项 (1/2, 直接回车选择 2): ").strip()
        if choice == '' or choice == '2':
            return 'imap'
        elif choice == '1':
            return 'foxmail'
        else:
            print("  无效选项，请输入 1 或 2")


def main():
    print("=" * 60)
    print("  12306 + 携程 电子发票 / 报销凭证提取工具")
    print("=" * 60)

    # 显示菜单，获取用户选择
    source_choice = show_menu()

    # 获取登录信息（如果需要）
    source_kwargs = {}
    if source_choice == 'imap':
        from qmail_ticket.config import get_imap_config, save_imap_config

        # 检查是否有保存的配置
        imap_config = get_imap_config()
        if imap_config:
            print(f"\n  使用已保存的配置: {imap_config['email']}")
            source_kwargs = {
                'email': imap_config['email'],
                'code': imap_config['code']
            }
        else:
            # 提示用户输入
            print("\n  首次使用 IMAP，请输入登录信息：")
            email_addr = input("  QQ邮箱: ").strip()
            auth_code = input("  授权码: ").strip()

            if not email_addr or not auth_code:
                print("  错误: imap 源需要邮箱地址和授权码", file=sys.stderr)
                sys.exit(1)

            # 保存配置
            save_imap_config(email_addr, auth_code)
            print("  登录信息已保存到 ~/.qmail-ticket/config.json")

            source_kwargs = {
                'email': email_addr,
                'code': auth_code
            }

    # 获取日期范围
    print()
    start_s = input("  起始日期 (YYYY-MM-DD, 回车跳过): ").strip() or None
    end_s = input("  截止日期 (YYYY-MM-DD, 回车跳过): ").strip() or None

    start_date = parse_date_arg(start_s) if start_s else None
    end_date = parse_date_arg(end_s) if end_s else None
    if end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59)
    if start_date or end_date:
        print(f"  筛选范围: {start_s or '不限'} ~ {end_s or '不限'}")

    # [1] 连接并搜索
    print(f"\n[1/4] 连接 {source_choice}...")

    source = get_source(source_choice, **source_kwargs)
    source.connect()
    raw_emails = source.search(start_date, end_date)
    source.disconnect()

    print(f"  找到 {len(raw_emails)} 封目标邮件")
    if not raw_emails:
        print("  未找到目标邮件，退出。")
        return

    # [2] 解析票面
    print(f"\n[2/4] 解析票面...")
    all_tickets = []
    pdf_data_list = []

    for raw in raw_emails:
        parser = get_parser(raw)
        if not parser:
            continue
        results = parser.parse(raw)
        if not results:
            continue
        for pdf_bytes, pdf_name, tickets in results:
            all_tickets.extend(tickets)
            pdf_data_list.append((pdf_bytes, pdf_name))
            tag = "机票" if "机票" in pdf_name else "火车"
            print(f"  [{tag}] {pdf_name}")

    print(f"  成功解析: {len(all_tickets)} 张票据")
    if not all_tickets:
        print("  没有可提取的附件，退出。")
        return

    # [3] 输出
    print(f"\n[3/4] 输出结果...")

    # 确保输出目录存在
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    context = {
        'output_dir': OUTPUT_DIR,
        'pdf_data_list': pdf_data_list,
    }
    for writer in WRITERS:
        writer.write(all_tickets, context)

    # [4] 完成
    print(f"\n[4/4] 完成!")
    print("=" * 60)
```

- [ ] **步骤 2：验证 CLI 运行**

```bash
python3 -m qmail_ticket
```

预期：程序启动，显示菜单（注意：会等待用户输入，这是预期的）

- [ ] **步骤 3：Commit**

```bash
git add qmail_ticket/cli.py
git commit -m "refactor: 移除命令行参数，完全使用交互式菜单"
```

---

### 任务 5：测试验证

**文件：**
- 无新增文件

- [ ] **步骤 1：验证配置管理模块**

```bash
python3 -c "
from qmail_ticket.config import get_config_path, load_config, save_config, get_imap_config, save_imap_config

# 测试保存配置
save_imap_config('test@qq.com', 'test-code')

# 测试读取配置
config = get_imap_config()
assert config is not None
assert config['email'] == 'test@qq.com'
assert config['code'] == 'test-code'

# 测试配置文件路径
path = get_config_path()
assert '~/.qmail-ticket/config.json' in path

print('配置管理模块测试通过!')
"
```

预期：`配置管理模块测试通过!`

- [ ] **步骤 2：验证包完整性**

```bash
python3 -c "
from qmail_ticket.config import get_config_path, load_config, save_config, get_imap_config, save_imap_config
from qmail_ticket.models import Ticket, RawEmail
from qmail_ticket.sources import get_source
from qmail_ticket.parsers import get_parser, PARSERS
from qmail_ticket.outputs import WRITERS

print(f'Config: OK')
print(f'Models: OK')
print(f'Sources: foxmail, imap')
print(f'Parsers: {len(PARSERS)}')
print(f'Writers: {len(WRITERS)}')
print('All imports OK!')
"
```

预期：`All imports OK!`

- [ ] **步骤 3：Commit**

```bash
git add -A
git commit -m "test: 添加配置管理模块测试"
```

---

## 自检

**规格覆盖度：**
- [x] §2.1 配置管理模块 → 任务 1
- [x] §2.2 交互式菜单模块 → 任务 2
- [x] §2.3 输出目录调整 → 任务 3
- [x] §3.1 交互式菜单流程 → 任务 2
- [x] §3.2 配置文件流程 → 任务 1
- [x] §4.1 配置文件错误 → 任务 1（load_config 异常处理）
- [x] §4.2 用户输入错误 → 任务 2（show_menu 循环验证）
- [x] §4.3 输出目录错误 → 任务 3（os.makedirs）

**占位符扫描：** 无 TODO/待定/后续实现。

**类型一致性：** 配置管理模块的函数签名在 cli.py 中正确调用。

---

## 执行选项

计划已完成并保存到 `docs/superpowers/plans/2026-05-15-interactive-menu-plan.md`。两种执行方式：

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选哪种方式？
