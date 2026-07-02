#!/usr/bin/env python3
"""远程服务器诊断脚本 - 凭据从 .env 动态读取。"""

import paramiko
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
try:
    from config import get_ssh_credentials
    _all_creds = get_ssh_credentials()
    SERVERS = [
        {"name": c['prefix'], "host": c['host'], "user": c['user'], "password": c['password']}
        for c in _all_creds if c['host']
    ]
except Exception as e:
    print(f"⚠️  config.get_ssh_credentials() 失败: {e}")
    SERVERS = []

if not SERVERS:
    print("❌ .env 中未找到 SSH 凭据")
    sys.exit(1)

# 使用列表构建复杂命令，避免引号嵌套问题
CMD_CDN_IPS = (
    "python3 -c \"import sqlite3,json; "
    "conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); "
    "c=conn.cursor(); "
    "c.execute(\\\"SELECT value FROM cdn_settings WHERE key='cdn_ips_list'\\\"); "
    "row=c.fetchone(); "
    "print(row[0][:500] if row and row[0] else 'EMPTY'); "
    "conn.close()\""
)

CMD_TUIC = (
    "python3 -c \"import json; "
    "cfg=json.load(open('/root/singbox-eps-node/config.json')); "
    "tuic=[i for i in cfg['inbounds'] if i.get('type')=='tuic']; "
    "print(json.dumps(tuic,indent=2))\""
)

COMMANDS = [
    ("服务状态 (singbox/singbox-sub/singbox-cdn)", "systemctl is-active singbox singbox-sub singbox-cdn"),
    ("版本号", "cat /root/singbox-eps-node/VERSION.md"),
    ("关键环境变量", "grep -E '^(SERVER_IP|CF_DOMAIN|COUNTRY_CODE|REALITY_SHORT_ID)=' /root/singbox-eps-node/.env"),
    ("CDN IP列表 (前500字符)", CMD_CDN_IPS),
    ("TUIC v5入站配置", CMD_TUIC),
    ("订阅服务HTTP状态码", "curl -sk -o /dev/null -w '%{http_code}' https://localhost:2087/sub/"),
    ("singbox-sub 近1小时日志 (最近30行)", "journalctl -u singbox-sub --since '1 hour ago' --no-pager -n 30"),
    ("singbox-cdn 近1小时日志 (最近30行)", "journalctl -u singbox-cdn --since '1 hour ago' --no-pager -n 30"),
]


def run_on_server(server):
    """连接服务器并依次执行诊断命令"""
    name = server["name"]
    host = server["host"]
    user = server["user"]
    password = server["password"]

    print("=" * 70)
    print(f"  服务器: {name} ({host})")
    print("=" * 70)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(host, port=22, username=user, password=password, timeout=15)
    except Exception as e:
        print(f"  [错误] 连接失败: {e}\n")
        return

    for label, cmd in COMMANDS:
        print(f"\n--- {label} ---")
        print(f"$ {cmd}")
        try:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            if out:
                print(out)
            if err:
                print(f"[stderr] {err}")
            if not out and not err:
                print("(无输出)")
        except Exception as e:
            print(f"  [命令执行错误] {e}")

    client.close()
    print()


def main():
    print("[Trae CN] 远程服务器诊断开始\n")
    for server in SERVERS:
        run_on_server(server)
    print("[Trae CN] 诊断完成")


if __name__ == "__main__":
    main()
