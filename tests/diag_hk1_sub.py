#!/usr/bin/env python3
"""HK1 订阅端点诊断：检查 /sub/HK Base64 订阅节点数，定位手机端只刷出 2 节点的根因。
"""
import os
import sys
import paramiko
import base64

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_DIR = '/root/singbox-eps-node'


def load_env():
    env = {}
    env_path = os.path.join(BASE_DIR, '.env')
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def run_remote(c, cmd, label='', timeout=60):
    if label:
        print(f"\n--- {label} ---")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out:
        print(out.rstrip())
    if err:
        print("STDERR:", err.rstrip())
    return out, err


def main():
    prefix = 'HK1'
    env = load_env()
    host = env.get(f'{prefix}_SSH_IP')
    user = env.get(f'{prefix}_SSH_USER')
    pwd = env.get(f'{prefix}_SSH_PASS')
    if not all([host, user, pwd]):
        print(f"[ERROR] .env 中缺少 {prefix}_SSH_IP/_SSH_USER/_SSH_PASS 凭据")
        sys.exit(1)

    print(f"=== 连接 HK1 服务器 {host} ===")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=user, password=pwd, timeout=15)

    # 1. /clash/HK 节点数（对比基准）
    run_remote(c, 'curl -sk https://127.0.0.1:2087/clash/HK | grep -c "^  - name:"', '1. /clash/HK 节点数（应为 4）')

    # 2. /sub/HK 默认（无 UA）节点数
    run_remote(c, 'curl -sk https://127.0.0.1:2087/sub/HK | base64 -d 2>/dev/null | grep -c "://"', '2. /sub/HK 默认节点数（无 UA）')

    # 3. /sub/HK 各 UA 节点数
    print("\n--- 3. /sub/HK 各 UA 节点数 ---")
    for ua in ['Shadowrocket', 'ClashMetaForAndroid/2.x', 'clash-meta', 'v2rayN', 'Quantumult%20X', 'Surge', 'sing-box']:
        out = run_remote(c, f'curl -sk -H "User-Agent: {ua}" https://127.0.0.1:2087/sub/HK | base64 -d 2>/dev/null | grep -c "://"', f'  UA={ua}')[0].strip()
        print(f"    -> {ua}: {out} 节点")

    # 4. /sub/HK 无 UA 的实际内容
    run_remote(c, 'curl -sk https://127.0.0.1:2087/sub/HK | base64 -d 2>/dev/null', '4. /sub/HK 无 UA 实际内容')

    # 5. /sub/HK Shadowrocket UA 的实际内容
    run_remote(c, 'curl -sk -H "User-Agent: Shadowrocket" https://127.0.0.1:2087/sub/HK | base64 -d 2>/dev/null', '5. /sub/HK Shadowrocket UA 实际内容')

    # 6. /singbox/HK 节点数
    run_remote(c, 'curl -sk https://127.0.0.1:2087/singbox/HK | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get(\'outbounds\',[])))" 2>/dev/null', '6. /singbox/HK 节点数')

    # 7. 检查 subscription_service.py 中 /sub 端点的 Base64 生成逻辑
    run_remote(c, f'grep -n "def generate_base64\\|def generate_sub\\|def sub\\|/sub" {REMOTE_DIR}/scripts/subscription_service.py | head -20', '7. /sub 端点相关函数定义')

    # 8. 检查 HK1 直连模式下 Base64 生成函数中 anyTLS/TUIC 的条件
    run_remote(c, f'grep -n "anytls\\|anyTLS\\|tuic\\|TUIC" {REMOTE_DIR}/scripts/subscription_service.py | head -30', '8. anyTLS/TUIC 在 subscription_service.py 中的引用')

    # 9. 检查 CLIENT_CAPABILITIES 配置
    run_remote(c, f'grep -A 20 "CLIENT_CAPABILITIES" {REMOTE_DIR}/scripts/subscription_service.py | head -30', '9. CLIENT_CAPABILITIES 配置')

    # 10. 直连模式判断逻辑
    run_remote(c, f'grep -n "DIRECT_MODE_ENABLED\\|direct_mode\\|HK_DIRECT_MODE" {REMOTE_DIR}/scripts/subscription_service.py | head -20', '10. 直连模式判断逻辑')

    c.close()
    print(f"\n=== HK1 订阅诊断完成 ===")


if __name__ == '__main__':
    main()
