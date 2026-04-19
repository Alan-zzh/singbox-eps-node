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
    return f"🔗 订阅链接:\nhttps://{addr}:2096/sub"

def handle_message(update):
    chat_id = str(update['message']['chat']['id'])
    text = update['message'].get('text', '').strip()

    if ADMIN_CHAT_ID and chat_id != ADMIN_CHAT_ID:
        send_message(chat_id, "❌ 无权限访问")
        return

    if text == '/status':
        send_message(chat_id, get_server_status())
    elif text == '/renew':
        send_message(chat_id, "⏳ 正在续签证书...")
        send_message(chat_id, renew_cert())
    elif text == '/sub':
        send_message(chat_id, get_sub_link())
    elif text == '/restart':
        send_message(chat_id, "⏳ 正在重启 Singbox...")
        send_message(chat_id, restart_singbox())
    elif text == '/cdn':
        send_message(chat_id, "⏳ 正在更新 CDN IP...")
        send_message(chat_id, update_cdn())
    elif text == '/help':
        send_message(chat_id, """📖 <b>可用命令</b>
/status - 查看服务器状态
/renew - 强制续签证书
/sub - 获取订阅链接
/restart - 重启Singbox
/cdn - 更新CDN IP
/help - 显示帮助""")
    else:
        send_message(chat_id, "❓ 未知命令，发送 /help 查看帮助")

def main():
    print(f"🤖 TG机器人启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📡 使用 Token: {BOT_TOKEN[:10]}...")

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
