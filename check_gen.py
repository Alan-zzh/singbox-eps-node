#!/usr/bin/env python3
"""检查 config.json 是如何生成的"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("检查配置生成方式")
print("="*60)

# 1. 检查 config_generator.py
_, stdout, _ = client.exec_command("head -50 /root/singbox-eps-node/scripts/config_generator.py")
gen_head = stdout.read().decode()
print(f"config_generator.py 头部:\n{gen_head[:400]}")

# 2. 检查 systemd 服务
_, stdout, _ = client.exec_command("systemctl list-units --type=service | grep -i sing")
services = stdout.read().decode()
print(f"\nSingbox 相关服务:\n{services}")

# 3. 检查 config_generator 的生成逻辑
_, stdout, _ = client.exec_command("grep -n 'config.json' /root/singbox-eps-node/scripts/config_generator.py | head -5")
gen_config = stdout.read().decode()
print(f"\nconfig_generator.py 中 config.json 相关:\n{gen_config}")

# 4. 检查 singbox-sub 服务
_, stdout, _ = client.exec_command("systemctl cat singbox-sub 2>/dev/null | head -20")
sub_service = stdout.read().decode()
print(f"\nsingbox-sub 服务配置:\n{sub_service}")

# 5. 检查 singbox 服务
_, stdout, _ = client.exec_command("systemctl cat singbox 2>/dev/null | head -20")
singbox_service = stdout.read().decode()
print(f"\nsingbox 服务配置:\n{singbox_service}")

# 6. 检查 subscription_service.py 的 API
_, stdout, _ = client.exec_command("grep -n 'def.*singbox' /root/singbox-eps-node/scripts/subscription_service.py | head -10")
api_endpoints = stdout.read().decode()
print(f"\n订阅服务 API 端点:\n{api_endpoints}")

# 7. 检查端口
_, stdout, _ = client.exec_command("netstat -tlnp | grep -E '2087|2083|5000|8080' 2>/dev/null || ss -tlnp | grep -E '2087|2083|5000|8080'")
ports = stdout.read().decode()
print(f"\n监听端口:\n{ports}")

client.close()
