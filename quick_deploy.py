#!/usr/bin/env python3
"""
快速部署：只上传 cdn_monitor.py 并测试
"""
import paramiko
import os

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

print("=== 上传 cdn_monitor.py ===")
sftp = client.open_sftp()
sftp.put('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\scripts\\cdn_monitor.py', '/root/singbox-manager/scripts/cdn_monitor.py')
sftp.close()
print("✅ 已上传")

print("\n=== 重启 CDN 监控服务 ===")
run_cmd(client, "systemctl restart singbox-cdn")
print("✅ 已重启")

print("\n=== 手动运行一次测试 ===")
import time
time.sleep(2)
exit_code, out, err = run_cmd(client, "cd /root/singbox-manager && python3 scripts/cdn_monitor.py 2>&1 | tail -20", timeout=60)
print(out)

print("\n=== 检查数据库 ===")
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

print("\n=== 测试订阅链接 ===")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub | base64 -d 2>/dev/null", timeout=30)
print(out)

client.close()
print("\n✅ 部署完成")
