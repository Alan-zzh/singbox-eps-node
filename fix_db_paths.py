#!/usr/bin/env python3
"""
修复数据库路径问题并清理旧数据
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

print("=== 1. 备份旧数据库 ===")
exit_code, out, err = run_cmd(client, "cp /root/singbox-manager/singbox.db /root/singbox-manager/singbox.db.old 2>/dev/null && echo 'BACKED_UP' || echo 'NO_OLD_DB'")
print(out)

print("\n=== 2. 删除旧数据库 ===")
exit_code, out, err = run_cmd(client, "rm -f /root/singbox-manager/singbox.db && echo 'DELETED' || echo 'NOT_FOUND'")
print(out)

print("\n=== 3. 确保新数据库存在且有正确数据 ===")
exit_code, out, err = run_cmd(client, """
python3 -c "
import sqlite3
import os

db_path = '/root/singbox-manager/data/singbox.db'
os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 创建表
cursor.execute('''
    CREATE TABLE IF NOT EXISTS cdn_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
''')

# 检查现有数据
cursor.execute('SELECT COUNT(*) FROM cdn_settings')
count = cursor.fetchone()[0]
print(f'数据库中有 {count} 条记录')

# 显示所有数据
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{key}: {value[:50]}...' if len(str(value)) > 50 else f'{key}: {value}')

conn.commit()
conn.close()
"
""")
print(out)

print("\n=== 4. 手动运行一次CDN监控更新数据 ===")
exit_code, out, err = run_cmd(client, "cd /root/singbox-manager && python3 scripts/cdn_monitor.py 2>&1 | tail -15", timeout=60)
print(out)

print("\n=== 5. 检查更新后的数据库 ===")
exit_code, out, err = run_cmd(client, """
python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-manager/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{key}: {value}')
conn.close()
"
""")
print(out)

print("\n=== 6. 重启服务 ===")
exit_code, out, err = run_cmd(client, "systemctl restart singbox-cdn singbox-sub && echo 'RESTARTED'")
print(out)

print("\n=== 7. 等待服务启动并测试订阅 ===")
import time
time.sleep(3)

exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub | base64 -d 2>/dev/null || curl -s http://127.0.0.1:6969/sub", timeout=30)
print("\n订阅内容:")
print(out[:2000])

client.close()
print("\n✅ 修复完成")
