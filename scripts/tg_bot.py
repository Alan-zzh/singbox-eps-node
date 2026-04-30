#!/usr/bin/env python3
"""
TG机器人总控脚本
Author: Alan
Version: v3.1.2
Date: 2026-05-01
功能：
  - /状态 查看服务器状态
  - /续签 强制续签证书
  - /订阅 获取订阅链接
  - /重启 重启Singbox（含singbox-sub和singbox-cdn）
  - /优选 更新CDN IP
  - /设置住宅 设置AI住宅IP SOCKS5
  - /删除住宅 删除AI住宅IP
"""

import os
import sys
import json
import time
import logging
import subprocess
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger('tg_bot')

BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.getenv('TG_ADMIN_CHAT_ID', '')

def load_env():
    env_path = os.path.join(os.getenv('BASE_DIR', '/root/singbox-eps-node'), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    v = v.strip().strip('"').strip("'")
                    os.environ[k] = v

load_env()

sys.path.insert(0, os.path.join(os.getenv('BASE_DIR', '/root/singbox-eps-node'), 'scripts'))
try:
    from config import BASE_DIR, SUB_PORT as CONFIG_SUB_PORT, CF_DOMAIN as CONFIG_CF_DOMAIN, SERVER_IP as CONFIG_SERVER_IP
except ImportError:
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
    CONFIG_SUB_PORT = 2087
    CONFIG_CF_DOMAIN = ''
    CONFIG_SERVER_IP = ''

ENV_FILE = os.path.join(BASE_DIR, '.env')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger('tg_bot')
logger.setLevel(logging.INFO)
fh = logging.FileHandler(os.path.join(LOG_DIR, 'tg_bot.log'), encoding='utf-8')
fh.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s %(message)s'))
logger.addHandler(fh)

if not BOT_TOKEN:
    logger.error("未配置 TG_BOT_TOKEN，请在 .env 中添加")
    sys.exit(1)

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text):
    url = f"{API_URL}/sendMessage"
    data = json.dumps({'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        logger.error("发送消息失败: %s", e)
        return None

def get_server_status():
    status = []
    status.append("📊 <b>服务器状态</b>")
    status.append(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for svc, label in [('singbox', 'Singbox'), ('singbox-sub', '订阅服务'), ('singbox-cdn', 'CDN监控')]:
        try:
            result = subprocess.run(['systemctl', 'is-active', svc], capture_output=True, text=True)
            if result.stdout.strip() == 'active':
                status.append(f"� {label}: 运行中")
            else:
                status.append(f"❌ {label}: 已停止")
        except Exception:
            status.append(f"🔴 {label}: 未知")

    try:
        with open('/proc/loadavg', 'r') as f:
            load = f.read().split()
        status.append(f"📈 负载: {load[0]} {load[1]} {load[2]}")
    except Exception:
        pass

    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        total = int(lines[0].split()[1])
        avail = int(lines[2].split()[1])
        used_pct = int((total - avail) / total * 100)
        status.append(f"💾 内存: {used_pct}%")
    except Exception:
        pass

    return '\n'.join(status)

def renew_cert():
    try:
        result = subprocess.run(
            ['python3', os.path.join(BASE_DIR, 'scripts/cert_manager.py'), '--renew'],
            capture_output=True, text=True, timeout=60, cwd=BASE_DIR
        )
        if result.returncode == 0:
            return "✅ 证书续签完成"
        else:
            logger.error("证书续签失败: %s", result.stderr[:500])
            return "❌ 证书续签失败，请查看日志"
    except Exception as e:
        logger.error("证书续签异常: %s", e)
        return "❌ 证书续签异常，请查看日志"

def restart_singbox():
    try:
        subprocess.run(['systemctl', 'restart', 'singbox', 'singbox-sub', 'singbox-cdn'], timeout=30)
        return "✅ Singbox 及相关服务已重启（singbox + singbox-sub + singbox-cdn）"
    except Exception as e:
        logger.error("重启失败: %s", e)
        return "❌ 重启失败，请查看日志"

def update_cdn():
    try:
        sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))
        from cdn_monitor import fetch_cdn_ips, assign_and_save_ips, init_db
        init_db()
        ips = fetch_cdn_ips()
        if ips:
            assign_and_save_ips(ips)
            return f"✅ CDN IP 已更新 ({len(ips)}个IP)"
        else:
            return "❌ CDN IP 更新失败：未获取到任何IP"
    except Exception as e:
        logger.error("CDN更新异常: %s", e)
        return "❌ CDN更新异常，请查看日志"

def get_sub_link():
    addr = CONFIG_CF_DOMAIN if CONFIG_CF_DOMAIN else CONFIG_SERVER_IP or os.getenv('SERVER_IP', '')
    sub_port = CONFIG_SUB_PORT
    country = os.getenv('COUNTRY_CODE', 'US')
    return f"🔗 订阅链接:\nhttps://{addr}:{sub_port}/sub/{country}"

def set_bot_commands():
    url = f"{API_URL}/setMyCommands"
    commands = [
        {"command": "状态", "description": "查看服务器运行状态（CPU/内存/服务）"},
        {"command": "续签", "description": "强制续签 SSL 证书（15年长期）"},
        {"command": "订阅", "description": "获取最新订阅链接（Base64/Clash）"},
        {"command": "重启", "description": "重启 Singbox 核心服务"},
        {"command": "优选", "description": "更新 CDN 优选 IP 地址"},
        {"command": "设置住宅", "description": "设置 AI 住宅IP SOCKS5（链式代理）"},
        {"command": "删除住宅", "description": "删除 AI 住宅IP，恢复普通代理"},
        {"command": "帮助", "description": "显示所有命令详细说明"}
    ]
    data = json.dumps({'commands': commands}).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get('ok'):
                logger.info("Telegram 命令菜单已设置")
    except Exception as e:
        logger.warning("设置命令菜单失败: %s", e)

def batch_update_env(updates):
    """批量更新.env中的多个键值对，只重启一次服务
    updates: dict of {key: value}
    """
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r') as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if '=' in stripped and not stripped.startswith('#'):
            k = stripped.split('=', 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                updated_keys.add(k)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_FILE, 'w') as f:
        f.writelines(new_lines)

    for k, v in updates.items():
        os.environ[k] = v

    subprocess.run(['python3', os.path.join(BASE_DIR, 'scripts/config_generator.py')], capture_output=True, cwd=BASE_DIR)
    subprocess.run(['systemctl', 'restart', 'singbox', 'singbox-sub', 'singbox-cdn'], capture_output=True)

def handle_ai_socks5(action, params=None):
    if action == 'set':
        server, port, user, pwd = params
        if not server or not port or not user or not pwd:
            return "❌ 参数不完整，请提供服务器、端口、用户名、密码"
        try:
            int(port)
        except ValueError:
            return "❌ 端口必须是数字"
        batch_update_env({
            'AI_SOCKS5_SERVER': server,
            'AI_SOCKS5_PORT': port,
            'AI_SOCKS5_USER': user,
            'AI_SOCKS5_PASS': pwd,
        })
        return f"✅ AI住宅IP已设置\n🌐 服务器: {server}:{port}\n👤 用户: {user}\n🔄 Singbox已重启，AI流量将走住宅IP"
    elif action == 'del':
        batch_update_env({
            'AI_SOCKS5_SERVER': '',
            'AI_SOCKS5_PORT': '',
            'AI_SOCKS5_USER': '',
            'AI_SOCKS5_PASS': '',
        })
        return "✅ AI住宅IP已删除\n🔄 Singbox已重启，AI流量将走普通代理"

def handle_message(update):
    chat_id = str(update['message']['chat']['id'])
    text = update['message'].get('text', '').strip()

    if ADMIN_CHAT_ID and chat_id != ADMIN_CHAT_ID:
        send_message(chat_id, "❌ 无权限访问")
        return

    if text == '/start' or text == '/帮助':
        current_ai = os.getenv('AI_SOCKS5_SERVER', '')
        ai_status = f"✅ 已配置: {current_ai}" if current_ai else "❌ 未配置"
        send_message(chat_id, f"""👋 <b>欢迎使用 Singbox 服务器管理机器人</b>

📖 <b>可用命令</b>（点击即可发送）：

/状态 - 📊 查看服务器运行状态（CPU/内存/服务运行情况）
/续签 - 🔄 强制续签 SSL 证书（Cloudflare 15年长期证书）
/订阅 - 🔗 获取最新订阅链接（自动识别 Clash/Base64 格式）
/重启 - 🔁 重启 Singbox 核心服务（配置更新后使用）
/优选 - 🌐 更新 CDN 优选 IP 地址（自动从多源获取最快IP）
/设置住宅 - 🏠 设置 AI 住宅IP SOCKS5（链式代理，AI流量走住宅IP）
/删除住宅 - 🗑️ 删除 AI 住宅IP（恢复普通代理模式）
/帮助 - ❓ 显示此帮助菜单

🏠 <b>AI住宅IP状态</b>: {ai_status}

💡 <b>提示</b>：点击命令即可执行，无需手动输入""")
    elif text == '/状态':
        send_message(chat_id, get_server_status())
    elif text == '/续签':
        send_message(chat_id, "⏳ 正在续签证书...")
        send_message(chat_id, renew_cert())
    elif text == '/订阅':
        send_message(chat_id, get_sub_link())
    elif text == '/重启':
        send_message(chat_id, "⏳ 正在重启 Singbox 及相关服务...")
        send_message(chat_id, restart_singbox())
    elif text == '/优选':
        send_message(chat_id, "⏳ 正在更新 CDN IP...")
        send_message(chat_id, update_cdn())
    elif text == '/设置住宅':
        send_message(chat_id, """🏠 <b>设置 AI 住宅IP SOCKS5</b>

请按以下格式发送（一行一条）：
<code>服务器IP:端口</code>
<code>用户名</code>
<code>密码</code>

例如：
<code>1.2.3.4:1080</code>
<code>myuser</code>
<code>mypass123</code>

💡 设置后，所有 AI 网站流量将自动走住宅IP，Singbox 会自动重启""")
    elif text == '/删除住宅':
        send_message(chat_id, handle_ai_socks5('del'))
    elif text.startswith('/设置住宅 '):
        parts = text[7:].strip().split('\n')
        if len(parts) >= 3:
            server_port = parts[0].strip().split(':')
            if len(server_port) == 2:
                result = handle_ai_socks5('set', (server_port[0], server_port[1], parts[1].strip(), parts[2].strip()))
                send_message(chat_id, result)
            else:
                send_message(chat_id, "❌ 格式错误，请按 IP:端口 格式发送")
        else:
            send_message(chat_id, "❌ 格式错误，请发送3行信息")
    else:
        send_message(chat_id, "❓ 未知命令，请发送 /帮助 查看说明")

def main():
    logger.info(f"TG机器人启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"使用 Token: {BOT_TOKEN[:5]}...{BOT_TOKEN[-5:] if len(BOT_TOKEN) > 10 else '***'}")

    set_bot_commands()

    offset = None
    while True:
        try:
            url = f"{API_URL}/getUpdates?offset={offset}&timeout=30"
            with urllib.request.urlopen(url, timeout=35) as resp:
                data = json.loads(resp.read().decode())
                if data.get('ok') and data.get('result'):
                    for update in data['result']:
                        offset = update['update_id'] + 1
                        if 'message' in update:
                            handle_message(update)
        except Exception as e:
            logger.error("轮询失败: %s", e)
            time.sleep(5)

if __name__ == '__main__':
    main()
