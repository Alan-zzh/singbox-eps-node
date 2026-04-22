#!/usr/bin/env python3
"""检查CDN数据库写入"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("检查CDN数据库...")

# 查看所有表
_, stdout, _ = client.exec_command("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); c=conn.cursor(); c.execute(\\\"SELECT name FROM sqlite_master WHERE type='table'\\\"); print('表:', [r[0] for r in c.fetchall()]); conn.close()\"")
print(stdout.read().decode().strip())

# 查看 cdn_settings 表内容
_, stdout, _ = client.exec_command("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); rows=c.fetchall(); print(f'cdn_settings: {len(rows)} 行'); [print(f'  {r}') for r in rows]; conn.close()\" 2>/dev/null || echo 'cdn_settings表不存在'")
print(stdout.read().decode().strip())

# 查看 cdn_ips 表内容
_, stdout, _ = client.exec_command("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_ips'); rows=c.fetchall(); print(f'cdn_ips: {len(rows)} 行'); [print(f'  {r}') for r in rows]; conn.close()\" 2>/dev/null || echo 'cdn_ips表不存在'")
print(stdout.read().decode().strip())

client.close()
