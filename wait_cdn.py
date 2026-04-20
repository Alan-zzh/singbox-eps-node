#!/usr/bin/env python3
"""
等待CDN服务获取IP并验证
"""
import paramiko
import time

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

print("等待CDN服务获取IP（60秒）...")
time.sleep(60)

print("\n【检查CDN IP】")
exit_code, out, err = run_cmd(client, """python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}: {row[1]}')
    print(f'  ✅ 共{len(rows)}个CDN IP')
else:
    print('  ❌ 无CDN IP')
conn.close()
" 2>/dev/null || echo '  ❌ 查询失败'""")
print(out)

print("\n【CDN服务日志】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 10 2>&1 | tail -10")
print(f"  {out}")

client.close()
