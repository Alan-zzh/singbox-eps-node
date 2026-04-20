#!/usr/bin/env python3
"""
调试订阅服务的 CDN IP 读取
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

print("=== 测试 subscription_service 的 DB_PATH 和读取 ===")
exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sys
sys.path.insert(0, 'scripts')

# 先加载配置
from config import DB_FILE, DATA_DIR, SERVER_IP, CF_DOMAIN
print('DB_FILE:', DB_FILE)
print('DATA_DIR:', DATA_DIR)
print('SERVER_IP:', SERVER_IP)
print('CF_DOMAIN:', CF_DOMAIN)

# 导入 subscription_service
from subscription_service import DB_PATH, get_cdn_ip_for_protocol
print('DB_PATH:', DB_PATH)

# 测试读取
import sqlite3
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
print('\\n数据库内容:')
for key, value in rows:
    print(f'  {key}: {value}')
conn.close()

print('\\n测试 get_cdn_ip_for_protocol:')
print('  vless_ws_cdn_ip:', get_cdn_ip_for_protocol('vless_ws_cdn_ip'))
print('  vless_upgrade_cdn_ip:', get_cdn_ip_for_protocol('vless_upgrade_cdn_ip'))
print('  trojan_ws_cdn_ip:', get_cdn_ip_for_protocol('trojan_ws_cdn_ip'))
"
""")
print(out)
if err:
    print(f"错误: {err}")

client.close()
