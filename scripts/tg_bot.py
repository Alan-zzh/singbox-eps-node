#!/usr/bin/env python3
"""
TG机器人总控脚本
Author: Alan
Version: v1.0.0
Date: 2026-04-20
功能：
  - /status 查看服务器状态
  - /renew 强制续签证书
  - /sub 获取订阅链接
  - /restart 重启Singbox
  - /cdn 更新CDN IP
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
from datetime import datetime

BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '')
ADMIN_CHAT_ID = os.getenv('TG_ADMIN_CHAT_ID', '')
BASE_DIR = '/root/singbox-manager'
ENV_FILE = os.path.join(BASE_DIR, '.env')

def load_env():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    os.environ[k] = v

load_env()

if not BOT_TOKEN:
    print("[ERROR] 未配置 TG_BOT_TOKEN，请在 .env 中添加")
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
        print(f"[ERROR] 发送消息失败: {e}")
        return None

def get_server_status():
    status = []
    status.append("📊 <b>服务器状态</b>")
    status.append(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        result = subprocess.run(['systemctl', 'is-active', 'singbox'], capture_output=True, text=True)
        status.append(f"🟢 Singbox: {'运行中' if result.stdout.strip() == 'active' else '❌ 已停止'}")
    except:
        status.append("🔴 Singbox: 未知")

    try:
        result = subprocess.run(['systemctl', 'is-active', 'singbox-sub'], capture_output=True, text=True)
        status.append(f"🟢 订阅服务: {'运行中' if result.stdout.strip() == 'active' else '❌ 已停止'}")
    except:
        status.append("🔴 订阅服务: 未知")

    try:
        result = subprocess.run(['systemctl', 'is-active', 'singbox-cdn'], capture_output=True, text=True)
        status.append(f"🟢 CDN监控: {'运行中' if result.stdout.strip() == 'active' else '❌ 已停止'}")
    except:
        status.append("🔴 CDN监控: 未知")

    try:
        with open('/proc/loadavg', 'r') as f:
            load = f.read().split()
        status.append(f"📈 负载: {load[0]} {load[1]} {load[2]}")
    except:
        pass

    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        total = int(lines[0].split()[1])
        avail = int(lines[2].split()[1])
        used_pct = int((total - avail) / total * 100)
        status.append(f"💾 内存: {used_pct}%")
    except:
        pass

    return '\n'.join(status)

def renew_cert():
    try:
        os.chdir(BASE_DIR)
        result = subprocess.run(['python3', 'scripts/cert_manager.py', '--renew'], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return "✅ 证书续签完成"
        else:
            return f"❌ 证书续签失败:\n{result.stderr[:500]}"
    except Exception as e:
        return f"❌ 异常: {e}"

def restart_singbox():
    try:
        subprocess.run(['systemctl', 'restart', 'singbox'], timeout=30)
        return "✅ Singbox 已重启"
    except Exception as e:
        return f"❌ 重启失败: {e}"

def update_cdn():
    try:
        os.chdir(BASE_DIR)
        result = subprocess.run(['python3', 'scripts/cdn_monitor.py'], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return "✅ CDN IP 已更新"
        else:
            return f"❌ CDN 更新失败:\n{result.stderr[:500]}"
    except Exception as e:
        return f"❌ 异常: {e}"

def get_sub_link():
    domain = os.getenv('CF_DOMAIN', '')
    ip = os.getenv('SERVER_IP', '')
    addr = domain if domain else ip
    sub_port = os.getenv('SUB_PORT', '6969')
    sub_token = os.getenv('SUB_TOKEN', '')
    return f"🔗 订阅链接:\nhttps://{addr}:{sub_port}/{sub_token}"

def set_bot_commands():
    """设置 Telegram 内置命令菜单"""
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
                print("✅ Telegram 命令菜单已设置")
    except Exception as e:
        print(f"[WARN] 设置命令菜单失败: {e}")

def update_env_and_restart(key, value):
    """更新.env并重启Singbox"""
    env_path = os.path.join(BASE_DIR, '.env')
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith(key + '='):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{key}={value}\n")
    with open(env_path, 'w') as f:
        f.writelines(lines)
    os.environ[key] = value
    subprocess.run(['python3', os.path.join(BASE_DIR, 'scripts/config_generator.py')], capture_output=True)
    subprocess.run(['systemctl', 'restart', 'singbox'], capture_output=True)

def handle_ai_socks5(action, params=None):
    """处理AI SOCKS5设置"""
    if action == 'set':
        server, port, user, pwd = params
        update_env_and_restart('AI_SOCKS5_SERVER', server)
        update_env_and_restart('AI_SOCKS5_PORT', port)
        update_env_and_restart('AI_SOCKS5_USER', user)
        update_env_and_restart('AI_SOCKS5_PASS', pwd)
        return f"✅ AI住宅IP已设置\n🌐 服务器: {server}:{port}\n👤 用户: {user}\n🔄 Singbox已重启，AI流量将走住宅IP"
    elif action == 'del':
        update_env_and_restart('AI_SOCKS5_SERVER', '')
        update_env_and_restart('AI_SOCKS5_PORT', '')
        update_env_and_restart('AI_SOCKS5_USER', '')
        update_env_and_restart('AI_SOCKS5_PASS', '')
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
        send_message(chat_id, "⏳ 正在重启 Singbox...")
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
    print(f"🤖 TG机器人启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📡 使用 Token: {BOT_TOKEN[:10]}...")

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
            print(f"[ERROR] 轮询失败: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main()
