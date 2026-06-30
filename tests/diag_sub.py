#!/usr/bin/env python3
"""诊断 singbox-sub 服务的 HTTP 500 问题。从 .env 读凭据。
用法: python tests/diag_sub.py HK
"""
import os
import sys
import paramiko

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_env():
    env = {}
    with open(os.path.join(BASE_DIR, '.env'), encoding='utf-8') as f:
        for l in f:
            l = l.strip()
            if '=' in l and not l.startswith('#'):
                k, v = l.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else 'HK'
    env = load_env()
    host = env[f'{prefix}_SSH_IP']
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=env[f'{prefix}_SSH_USER'], password=env[f'{prefix}_SSH_PASS'], timeout=15)

    cmds = [
        ('订阅端点 /clash', 'curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:2087/clash/' + prefix),
        ('订阅端点 /sub', 'curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:2087/sub/' + prefix),
        ('首页 /', 'curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:2087/'),
        ('singbox-sub 日志(近40行)', 'journalctl -u singbox-sub --no-pager -n 40 2>&1 | tail -40'),
        ('.env DEPLOY_MODE', 'grep -E "^DEPLOY_MODE=|^CF_DOMAIN=|^COUNTRY_CODE=" /root/singbox-eps-node/.env || echo "(无DEPLOY_MODE)"'),
    ]
    for label, cmd in cmds:
        print(f"\n--- {label} ---")
        _, o, e = c.exec_command(cmd, timeout=30)
        out = o.read().decode('utf-8', errors='replace')
        err = e.read().decode('utf-8', errors='replace')
        if out:
            print(out.rstrip())
        if err:
            print("ERR:", err.rstrip())
    c.close()

if __name__ == '__main__':
    main()
