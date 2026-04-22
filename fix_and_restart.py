#!/usr/bin/env python3
"""修复日本服务器配置并重启"""
import paramiko
import time

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("修复日本服务器配置")
print("="*60)

# 1. 重新生成服务端配置
print("\nStep 1: 重新生成 config.json")
_, stdout, stderr = client.exec_command("cd /root/singbox-eps-node && python3 scripts/config_generator.py")
gen_out = stdout.read().decode()
gen_err = stderr.read().decode()
print(f"输出: {gen_out}")
if gen_err:
    print(f"错误: {gen_err}")

# 2. 重启订阅服务（会自动重新加载）
print("\nStep 2: 重启所有服务")
_, stdout, _ = client.exec_command("systemctl restart singbox-sub singbox-cdn && sleep 2 && systemctl restart singbox")
time.sleep(3)

# 3. 检查服务状态
_, stdout, _ = client.exec_command("systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
status = stdout.read().decode().strip()
print(f"服务状态:\n{status}")

# 4. 验证新配置
_, stdout, _ = client.exec_command("python3 -c \"import json; config=json.load(open('/root/singbox-eps-node/config.json')); rules=config.get('route',{}).get('rules',[]); print(f'路由规则数量: {len(rules)}')\"")
print(f"\n配置验证: {stdout.read().decode().strip()}")

# 5. 检查 DNS 配置
_, stdout, _ = client.exec_command("python3 -c \"import json; config=json.load(open('/root/singbox-eps-node/config.json')); dns=config.get('dns',{}); servers=dns.get('servers',[]); print(f'DNS服务器数量: {len(servers)}')\"")
print(f"DNS 配置: {stdout.read().decode().strip()}")

client.close()
print("\n✅ 修复完成")
