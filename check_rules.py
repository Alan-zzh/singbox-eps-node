#!/usr/bin/env python3
"""检查服务端 config_generator.py 的规则生成逻辑"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("检查 config_generator.py 路由规则生成")
print("="*60)

# 读取完整文件
_, stdout, _ = client.exec_command("cat /root/singbox-eps-node/scripts/config_generator.py")
content = stdout.read().decode()

# 检查规则相关
import re

# 查找 rules 变量定义
rules_section = re.findall(r'rules.*?=.*?\[.*?\]', content, re.DOTALL)
print(f"\n找到 rules 定义: {len(rules_section)} 处")

# 查找 DNS 配置
dns_section = re.findall(r'dns.*?=.*?\{.*?\}', content, re.DOTALL)
print(f"找到 DNS 定义: {len(dns_section)} 处")

# 输出文件最后50行（应该是路由规则部分）
lines = content.split('\n')
print(f"\n文件总行数: {len(lines)}")

# 检查 route 和 rules
route_start = None
for i, line in enumerate(lines):
    if '"route"' in line and i > 100:  # 跳过前面的配置
        route_start = i
        print(f"\nroute 开始于行: {i+1}")
        break

if route_start:
    print(f"\nroute 部分 (行 {route_start+1} 到结尾):")
    for i in range(route_start, min(route_start+100, len(lines))):
        print(f"{i+1}: {lines[i]}")

client.close()
