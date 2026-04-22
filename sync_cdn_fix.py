#!/usr/bin/env python3
"""同步CDN修复到日本服务器并验证"""
import paramiko
import time

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

sftp = client.open_sftp()

print("="*60)
print("同步CDN修复到日本服务器")
print("="*60)

files = [
    ('scripts/cdn_monitor.py', 'scripts/cdn_monitor.py'),
    ('scripts/config_generator.py', 'scripts/config_generator.py'),
    ('scripts/subscription_service.py', 'scripts/subscription_service.py'),
    ('scripts/config.py', 'scripts/config.py'),
    ('AI_DEBUG_HISTORY.md', 'AI_DEBUG_HISTORY.md'),
]

for local_name, remote_name in files:
    local_path = f'd:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\{local_name}'
    remote_path = f'/root/singbox-eps-node/{remote_name}'
    sftp.put(local_path, remote_path)
    print(f"  ✅ {local_name}")

sftp.close()

# 重启CDN服务
print("\n重启CDN服务...")
_, stdout, _ = client.exec_command("systemctl restart singbox-cdn && sleep 3 && systemctl is-active singbox-cdn")
print(f"  状态: {stdout.read().decode().strip()}")

# 手动触发一次CDN更新
print("\n手动触发CDN更新...")
_, stdout, stderr = client.exec_command("cd /root/singbox-eps-node && python3 -c \"from scripts.cdn_monitor import fetch_cdn_ips, assign_and_save_ips; ips=fetch_cdn_ips(); assign_and_save_ips(ips); print(f'获取到 {len(ips)} 个IP: {ips[:5]}')\" 2>&1")
out = stdout.read().decode()
print(out[:2000])

# 检查CDN数据
print("\n检查CDN数据...")
_, stdout, _ = client.exec_command("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); c=conn.cursor(); c.execute('SELECT protocol,ip,updated_at FROM cdn_settings ORDER BY updated_at DESC LIMIT 5'); rows=c.fetchall(); [print(f'  {r[0]}: {r[1]} ({r[2]})') for r in rows]; conn.close()\" 2>/dev/null || echo '  无CDN数据'")
print(stdout.read().decode().strip())

client.close()
print("\n✅ 完成")
