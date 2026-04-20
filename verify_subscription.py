#!/usr/bin/env python3
"""
验证订阅链接是否正确使用了CDN优选IP
"""
import paramiko
import base64
import re

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

print("=== 获取订阅链接 ===")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub", timeout=30)

# 尝试Base64解码
try:
    decoded = base64.b64decode(out).decode('utf-8')
    print("\n=== 解码后的订阅链接 ===")
    links = decoded.strip().split('\n')
    for link in links:
        if link.strip():
            print(f"\n{link.strip()}")
except:
    print("\n无法解码Base64，原始内容:")
    print(out[:2000])

# 提取所有IP
print("\n\n=== 提取的IP地址 ===")
ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', out if not decoded else decoded)
unique_ips = list(set(ips))
print(f"共找到 {len(unique_ips)} 个不同IP:")
for ip in unique_ips:
    print(f"  - {ip}")

# 检查数据库中的CDN IP
print("\n=== 数据库中的CDN IP ===")
exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sqlite3
conn = sqlite3.connect('data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings WHERE key LIKE \"%cdn_ip%\"')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{key}: {value}')
conn.close()
"
""")
print(out)

client.close()
print("\n✅ 验证完成")
