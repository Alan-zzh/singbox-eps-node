#!/usr/bin/env python3
"""
快速检查服务器状态
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

print("【服务状态】")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    print(f"  {svc}: {out}")

print("\n【CDN IP数据库】")
exit_code, out, err = run_cmd(client, """python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}: {row[1]}')
else:
    print('  无CDN IP数据')
conn.close()
" 2>/dev/null || echo '  数据库查询失败'""")
print(out)

print("\n【CDN服务日志（最新5条）】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 5 2>&1 | tail -5")
print(f"  {out}")

print("\n【订阅服务测试】")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null")
print(f"  {out}")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null")
print(f"  {out}")

client.close()
