#!/usr/bin/env python3
"""从日本服务器测试延迟，验证是否走了 SOCKS5"""
import subprocess
import json
import time

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("Step 1: 检查 AI 规则是否包含 google.com")
print("="*60)

_, stdout, _ = client.exec_command("grep -A 30 'ai-residential' /usr/local/s-ui/singbox/config.json")
config = stdout.read().decode()
print(config[:800])

print("\n" + "="*60)
print("Step 2: 测试正常延迟（ping www.google.com）")
print("="*60)

_, stdout, _ = client.exec_command("ping -c 5 www.google.com")
result = stdout.read().decode()
for line in result.split('\n'):
    if 'rtt' in line.lower() or 'time=' in line.lower() or 'loss' in line.lower():
        print(line)

print("\n" + "="*60)
print("Step 3: 模拟 v2rayN 延迟测试 (curl www.google.com/generate_204)")
print("="*60)

start = time.time()
_, stdout, _ = client.exec_command("curl -o /dev/null -s -w '%{time_total}' https://www.google.com/generate_204 --connect-timeout 5")
elapsed = stdout.read().decode().strip()
end = time.time()
print(f"curl 耗时: {elapsed} 秒")

print("\n" + "="*60)
print("Step 4: 测试 SOCKS5 延迟（如果有的话）")
print("="*60)

# 尝试读取 SOCKS5 配置
_, stdout, _ = client.exec_command("grep 'AI_SOCKS5' /root/singbox-eps-node/.env 2>/dev/null || echo '未配置'")
socks_info = stdout.read().decode().strip()
print(f"SOCKS5 配置: {socks_info}")

client.close()
print("\n✅ 测试完成")
