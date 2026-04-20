#!/usr/bin/env python3
"""
检查服务器上的数据库路径和内容
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

print("=== 查找所有 singbox.db 文件 ===")
exit_code, out, err = run_cmd(client, "find /root -name 'singbox.db' 2>/dev/null")
print(out)

print("\n=== 检查各个可能路径的数据库内容 ===")
paths = [
    '/root/singbox-manager/singbox.db',
    '/root/singbox-manager/data/singbox.db',
    '/root/singbox-eps-node/singbox.db',
]

for path in paths:
    print(f"\n--- 检查: {path} ---")
    exit_code, out, err = run_cmd(client, f"ls -la {path} 2>/dev/null || echo 'NOT_FOUND'")
    print(f"文件状态: {out}")
    
    if 'NOT_FOUND' not in out:
        exit_code, out, err = run_cmd(client, f"""
python3 -c "
import sqlite3
conn = sqlite3.connect('{path}')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{{key}}: {{value}}')
conn.close()
"
""")
        print(f"数据库内容:\n{out}")

print("\n=== 检查 subscription_service.py 使用的 DB_PATH ===")
exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from subscription_service import DB_PATH
print('DB_PATH:', DB_PATH)
"
""")
print(out)
if err:
    print(f"错误: {err}")

print("\n=== 检查 cdn_monitor.py 使用的 DATA_DIR ===")
exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from config import DATA_DIR
print('DATA_DIR:', DATA_DIR)
"
""")
print(out)
if err:
    print(f"错误: {err}")

client.close()
print("\n✅ 检查完成")
