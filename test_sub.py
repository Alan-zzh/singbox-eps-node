#!/usr/bin/env python3
"""
测试订阅服务
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

print("=" * 60)
print("测试订阅服务")
print("=" * 60)

# 测试HTTP订阅
print("\n【测试HTTP订阅】")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub")
print(f"  /sub: {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub/JP")
print(f"  /sub/JP: {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/iKzF2SK3yhX3UfLw")
print(f"  /token: {out}")

# 获取订阅内容
print("\n【获取订阅内容（前500字符）】")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub 2>/dev/null | head -c 500")
if out:
    print(out)
else:
    print("  无法获取内容")

# 检查CDN IP
print("\n【检查CDN IP】")
exit_code, out, err = run_cmd(client, "python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); cursor=conn.cursor(); cursor.execute('SELECT key,value FROM cdn_settings WHERE key LIKE \\\"%cdn%\\\"'); [print(f'  {r[0]}: {r[1]}') for r in cursor.fetchall()]; conn.close()\" 2>/dev/null || echo '  数据库不存在或无CDN IP'")
print(out)

# 检查服务日志
print("\n【订阅服务最新日志】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 5 2>&1 | tail -5")
print(f"  {out}")

client.close()

print("\n" + "=" * 60)
print("✅ 测试完成！")
print("=" * 60)
