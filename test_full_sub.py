#!/usr/bin/env python3
"""
完整测试 subscription_service 的链接生成
"""
import paramiko

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

print("=== 完整测试链接生成 ===")
exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sys
sys.path.insert(0, 'scripts')

# 导入所有需要的变量
from subscription_service import (
    SERVER_IP, CF_DOMAIN, DB_PATH,
    VLESS_WS_UUID, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, TROJAN_PASSWORD,
    REALITY_SNI, REALITY_PUBLIC_KEY, REALITY_SHORT_ID, REALITY_DEST,
    HYSTERIA2_PASSWORD, HYSTERIA2_UDP_PORTS,
    get_cdn_ip_for_protocol, generate_all_links
)
import sqlite3
import random

print('SERVER_IP:', SERVER_IP)
print('CF_DOMAIN:', CF_DOMAIN)
print('DB_PATH:', DB_PATH)

# 检查数据库
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
print('\\n数据库内容:')
for key, value in rows:
    print(f'  {key}: {value}')
conn.close()

# 测试 get_cdn_ip_for_protocol
print('\\nget_cdn_ip_for_protocol 测试结果:')
vless_ws = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
print(f'  vless_ws_cdn_ip: {vless_ws}')
vless_upgrade = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
print(f'  vless_upgrade_cdn_ip: {vless_upgrade}')
trojan_ws = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
print(f'  trojan_ws_cdn_ip: {trojan_ws}')

# 生成链接
print('\\n生成的链接:')
links = generate_all_links()
for link in links:
    print(link)
"
""", timeout=30)
print(out)
if err:
    print(f"错误: {err}")

client.close()
