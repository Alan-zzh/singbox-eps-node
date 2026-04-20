#!/usr/bin/env python3
"""
快速检查服务器最终状态
"""
import paramiko
import base64

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

print("\n【CDN IP】")
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

print("\n【订阅测试】")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTPS: 不可用'")
print(f"  {out}")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTP: 不可用'")
print(f"  {out}")

print("\n【订阅内容】")
exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub 2>/dev/null || curl -s http://127.0.0.1:6969/sub 2>/dev/null")
if out:
    try:
        decoded = base64.b64decode(out).decode('utf-8')
        lines = decoded.strip().split('\n')
        print(f"  ✅ {len(lines)}个节点:")
        for line in lines:
            if '#' in line:
                name = line.split('#')[-1]
                print(f"    - {name}")
    except:
        print(f"  ⚠️ 格式: {out[:100]}...")
else:
    print("  ❌ 无法获取")

client.close()
print("\n✅ 检查完成！")
