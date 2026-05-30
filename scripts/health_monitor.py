#!/usr/bin/env python3
"""
singbox 服务健康监控与自动报警脚本 (方案 C - 双保险)

架构:
  第 1 层: systemd 原生 Restart=always + RestartSec=5（服务挂 5-10 秒自动恢复）
  第 2 层: 监控每 60 秒检查 + 连续失败 2 次自动 kill 残留 + 超过 3 次邮件报警
  第 3 层: 端口被占时自动 fuser 清理

恢复时间: 5-10 秒（systemd 自动）
报警触发: 连续 2 次检查失败（~120 秒）
邮件冷却: 10 分钟内不重复发同一报警
"""

import subprocess
import smtplib
import os
import json
import time
import sys
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ==================== 配置 ====================

def load_env():
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

SMTP_SERVER = os.getenv('MONITOR_SMTP_SERVER', 'smtp.qq.com')
SMTP_PORT = int(os.getenv('MONITOR_SMTP_PORT', '465'))
SMTP_USER = os.getenv('MONITOR_SMTP_USER', '')
SMTP_PASS = os.getenv('MONITOR_SMTP_PASS', '')
ALERT_EMAIL = os.getenv('MONITOR_ALERT_EMAIL', '')
SERVER_IP = os.getenv('SERVER_IP', '未知')
COUNTRY = os.getenv('COUNTRY_CODE', '未知')

# 阈值
CHECK_INTERVAL = int(os.getenv('MONITOR_CHECK_INTERVAL', '60'))  # 60 秒
RESTART_THRESHOLD = int(os.getenv('MONITOR_RESTART_THRESHOLD', '10'))
PORT = int(os.getenv('SUB_PORT', '2087'))
ALERT_AFTER_FAILS = 2    # 连续失败 2 次后报警（~120 秒）
AUTO_KILL_AFTER = 2      # 连续失败 2 次后自动清理并强制重启
ALERT_COOLDOWN = 600     # 邮件冷却 10 分钟

SERVICES = ['singbox-sub', 'singbox']
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
STATE_FILE = os.path.join(DATA_DIR, 'singbox_monitor_state.json')


def send_email(subject: str, body: str) -> bool:
    if not SMTP_USER or not SMTP_PASS or not ALERT_EMAIL:
        return False
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = ALERT_EMAIL
        msg['Subject'] = f"[{COUNTRY}-singbox 报警] {subject}"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, ALERT_EMAIL, msg.as_string())
        server.quit()
        print(f"[{datetime.now()}] ✅ 邮件已发送 → {ALERT_EMAIL}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] ❌ 邮件发送失败: {e}")
        return False


def run_cmd(cmd: str, timeout: int = 10) -> str:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


def check_service(name: str) -> dict:
    active = run_cmd(f"systemctl is-active {name} 2>/dev/null") == 'active'
    nrestarts = 0
    if name == 'singbox-sub':
        out = run_cmd(f"systemctl show {name} --property=NRestarts 2>/dev/null")
        try:
            nrestarts = int(out.split('=')[1])
        except:
            pass
    port_ok = 'python' in run_cmd(f"ss -tlnp | grep :{PORT} 2>/dev/null") if name == 'singbox-sub' else True
    return {
        'name': name,
        'active': active,
        'status': 'active' if active else 'inactive',
        'restarts': nrestarts,
        'port_ok': port_ok,
        'time': datetime.now().strftime('%H:%M:%S')
    }


def clean_port():
    pids = run_cmd(f"fuser {PORT}/tcp 2>/dev/null")
    if pids:
        print(f"  清理端口 {PORT} 占用 PID={pids}")
        run_cmd(f"fuser -k {PORT}/tcp 2>/dev/null")
        time.sleep(2)
        return True
    return False


def force_restart(name: str):
    print(f"  强制重启 {name}...")
    run_cmd(f"systemctl stop {name} 2>/dev/null")
    time.sleep(2)
    clean_port()
    run_cmd(f"systemctl start {name}")


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            pass
    return {'fail_counts': {}, 'last_alerts': {}, 'last_ok': {}}


def save_state(state: dict):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except:
        pass


def main():
    print(f"[{datetime.now()}] 监控启动 | {COUNTRY} {SERVER_IP}")
    print(f"  检查间隔: {CHECK_INTERVAL}s | 报警阈值: 连续{ALERT_AFTER_FAILS}次失败")
    print(f"  报警邮箱: {ALERT_EMAIL or '未配置'}")
    print("-" * 60)

    state = load_state()
    now_ts = time.time()

    while True:
        now_ts = time.time()
        any_issue = False

        for svc in SERVICES:
            info = check_service(svc)
            fail_key = svc

            if info['active']:
                state['fail_counts'][fail_key] = 0
                state['last_ok'][fail_key] = now_ts
                print(f"[{info['time']}] {svc}: ✅ active | 重启次数: {info['restarts']}")
                continue

            # 服务不 active
            state['fail_counts'][fail_key] = state.get('fail_counts', {}).get(fail_key, 0) + 1
            fails = state['fail_counts'][fail_key]
            any_issue = True
            print(f"[{info['time']}] {svc}: ❌ {info['status']} | 连续失败: {fails}")

            # 达到自动清理阈值
            if fails >= AUTO_KILL_AFTER:
                print(f"  🔄 连续失败 {fails} 次，执行清理+重启...")
                force_restart(svc)
                time.sleep(3)
                recheck = check_service(svc)
                if recheck['active']:
                    print(f"  ✅ 重启成功")
                    state['fail_counts'][fail_key] = 0
                else:
                    print(f"  ❌ 重启仍失败")

            # 达到报警阈值
            if fails >= ALERT_AFTER_FAILS:
                last_alert = state.get('last_alerts', {}).get(fail_key, 0)
                if now_ts - last_alert > ALERT_COOLDOWN:
                    body = f"""
服务器: {COUNTRY} ({SERVER_IP})
服务: {svc}
状态: 连续 {fails} 次检查失败
端口: {PORT}

已自动执行:
1. 清理端口占用
2. 强制重启服务

请 SSH 检查:
  journalctl -u {svc} -n 50 --no-pager
  ss -tlnp | grep {PORT}
                    """.strip()
                    send_email(f"{svc} 异常 ({fails}次失败)", body)
                    state['last_alerts'][fail_key] = now_ts

        # 所有服务正常：重置连续失败计数
        if not any_issue:
            for svc in SERVICES:
                state['fail_counts'][svc] = 0
            print("✅ 所有服务正常")

        save_state(state)
        print("-" * 60)
        time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n监控已停止")
        sys.exit(0)
