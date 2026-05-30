#!/usr/bin/env python3
import paramiko
import time

time.sleep(8)

servers = [
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
]

for srv in servers:
    print(f"\n=== {srv['name']} 服务器日志检查 ===")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        stdin, stdout, stderr = client.exec_command('journalctl -u singbox-cdn --no-pager -n 40 --since "2 minutes ago"')
        output = stdout.read().decode('utf-8', errors='replace')
        print(output)
        client.close()
    except Exception as e:
        print(f"失败: {e}")
