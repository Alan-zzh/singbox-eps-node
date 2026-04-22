#!/usr/bin/env python3
"""检查CDN更新问题"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("检查CDN数据不更新原因")
print("="*60)

# 1. 检查CDN服务日志
print("\n【CDN服务日志】最近30行")
_, stdout, _ = client.exec_command("journalctl -u singbox-cdn -n 30 --no-pager")
print(stdout.read().decode()[:2000])

# 2. 检查CDN数据文件
print("\n【CDN数据文件】")
_, stdout, _ = client.exec_command("ls -la /root/singbox-eps-node/data/ 2>/dev/null")
print(stdout.read().decode().strip())

# 3. 检查数据库
print("\n【数据库CDN表】")
_, stdout, _ = client.exec_command("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_ips'); rows=c.fetchall(); print(f'记录数: {len(rows)}'); [print(f'  {r}') for r in rows]; conn.close()\" 2>/dev/null || echo '数据库不存在或表不存在'")
print(stdout.read().decode().strip())

# 4. 手动运行一次CDN更新
print("\n【手动运行CDN更新】")
_, stdout, stderr = client.exec_command("cd /root/singbox-eps-node && python3 -c \"from scripts.cdn_monitor import fetch_cdn_ips, assign_and_save_ips; ips=fetch_cdn_ips(); assign_and_save_ips(ips); print(f'获取到 {len(ips)} 个IP')\" 2>&1")
out = stdout.read().decode()
err = stderr.read().decode()
print(out[:1500])
if err:
    print(f"错误: {err[:500]}")

client.close()
print("\n✅ 检查完成")
