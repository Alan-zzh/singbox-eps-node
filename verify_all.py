#!/usr/bin/env python3
"""
重启服务并验证所有功能
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

print("=" * 60)
print("重启服务并验证所有功能")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
print("✅ 服务器连接成功")

# 1. 重启CDN服务
print("\n【重启CDN服务】...")
run_cmd(client, "systemctl restart singbox-cdn")
print("  ✅ CDN服务已重启")

# 等待CDN服务获取IP
print("\n【等待CDN服务获取IP】（30秒）...")
time.sleep(30)

# 2. 检查CDN IP
print("\n【检查CDN IP】...")
exit_code, out, err = run_cmd(client, """python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}: {row[1]}')
    print(f'\\n  共获取到{len(rows)}个CDN IP')
else:
    print('  无CDN IP数据')
conn.close()
" 2>/dev/null || echo '  数据库查询失败'""")
print(out)

# 3. 重启订阅服务
print("\n【重启订阅服务】...")
run_cmd(client, "systemctl restart singbox-sub")
print("  ✅ 订阅服务已重启")

time.sleep(5)

# 4. 检查服务状态
print("\n【检查服务状态】...")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    status = "✅ 运行中" if out == 'active' else "❌ 未运行"
    print(f"  {svc}: {status}")

# 5. 测试HTTPS订阅
print("\n【测试HTTPS订阅】...")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTPS不可用'")
print(f"  {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTP不可用'")
print(f"  {out}")

# 6. 获取订阅内容
print("\n【订阅内容（前500字符）】...")
exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub 2>/dev/null | head -c 500 || curl -s http://127.0.0.1:6969/sub 2>/dev/null | head -c 500")
if out:
    print(out)
else:
    print("  无法获取")

# 7. 检查CDN服务日志
print("\n【CDN服务日志】...")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 10 2>&1 | tail -10")
print(f"  {out}")

# 8. 检查订阅服务日志
print("\n【订阅服务日志】...")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 5 2>&1 | tail -5")
print(f"  {out}")

client.close()

print("\n" + "=" * 60)
print("✅ 验证完成！")
print("=" * 60)
