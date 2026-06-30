#!/usr/bin/env python3
import paramiko
import sys
import os

SERVERS = [
    {'host': '43.207.152.47', 'name': 'JP', 'password': 'sarEBA97@jh.dxclouds.com', 'cc': 'JP'},
    {'host': '13.212.37.11', 'name': 'SG', 'password': 'jbfCMP75@jh.dxclouds.com', 'cc': 'SG'},
    {'host': '43.249.174.222', 'name': 'HK', 'password': '2aKf9Xt!4U.gOywfci', 'cc': 'HK'},
]

import yaml  # we'll print raw and try parse

for srv in SERVERS:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(srv['host'], username='root', password=srv['password'], timeout=15)
        cmd = f"curl -sk -A 'clash-verge/2.0' https://127.0.0.1:2087/clash/{srv['cc']}"
        _, so, se = ssh.exec_command(cmd, timeout=15)
        data = so.read().decode('utf-8', errors='replace')
        err = se.read().decode('utf-8', errors='replace')

        print(f"\n{'='*70}")
        print(f"=== {srv['name']} ({srv['host']}) /clash/{srv['cc']}  length={len(data)}")
        print(f"{'='*70}")

        # 保存到本地文件以便分析
        local_path = os.path.join(os.path.dirname(__file__), f'_clash_{srv["name"]}.yaml')
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(data)
        print(f"[saved to {local_path}]")

        # 显示 proxies: 段落（找 proxy 5）
        lines = data.split('\n')
        in_proxies = False
        proxy_idx = 0
        for i, line in enumerate(lines):
            if line.strip() == 'proxies:':
                in_proxies = True
                print(f"--- proxies section starting at line {i+1} ---")
                continue
            if in_proxies:
                # 检查是否到下一个顶层 section（顶格 + 冒号）
                if line and not line.startswith(' ') and not line.startswith('\t') and ':' in line and not line.startswith('-'):
                    print(f"--- end of proxies at line {i+1} ---")
                    break
                if line.startswith('  - '):
                    # 新 proxy 开始
                    name_part = line[4:].strip()
                    print(f"\n  proxy[{proxy_idx}]: {name_part[:100]}")
                    proxy_idx += 1
                elif proxy_idx <= 7 and line.startswith('    '):
                    print(f"    {line.strip()[:100]}")
    except Exception as e:
        print(f"ERROR {srv['name']}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        ssh.close()
