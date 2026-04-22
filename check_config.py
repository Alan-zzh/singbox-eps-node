#!/usr/bin/env python3
"""检查日本服务器 singbox 配置"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("检查日本服务器 sing-box 配置")
print("="*60)

# 1. 检查服务端配置
_, stdout, _ = client.exec_command("cat /usr/local/s-ui/singbox/config.json | head -5")
print(f"配置文件头部: {stdout.read().decode()[:200]}")

# 2. 检查路由规则
_, stdout, _ = client.exec_command("grep -c 'outbound' /usr/local/s-ui/singbox/config.json")
count = stdout.read().decode().strip()
print(f"\n路由规则数量: {count}")

# 3. 检查 google 相关域名
_, stdout, _ = client.exec_command("grep 'google' /usr/local/s-ui/singbox/config.json")
google_lines = stdout.read().decode().strip()
print(f"\ngoogle 相关域名: {google_lines or '无'}")

# 4. 检查 ai-residential
_, stdout, _ = client.exec_command("grep 'ai-residential' /usr/local/s-ui/singbox/config.json")
ai_lines = stdout.read().decode().strip()
print(f"\nai-residential 出现次数: {len(ai_lines.split(chr(10))) if ai_lines else 0}")

# 5. 检查服务状态
_, stdout, _ = client.exec_command("systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
services = stdout.read().decode().strip()
print(f"\n服务状态:\n{services}")

# 6. 检查文件时间戳
_, stdout, _ = client.exec_command("ls -la /usr/local/s-ui/singbox/config.json")
print(f"\n配置文件时间: {stdout.read().decode().strip()}")

# 7. 读取完整配置（前100行）
_, stdout, _ = client.exec_command("head -100 /usr/local/s-ui/singbox/config.json")
print(f"\n配置前100行:\n{stdout.read().decode()[:500]}")

client.close()
