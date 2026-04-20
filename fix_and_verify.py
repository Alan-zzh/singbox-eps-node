#!/usr/bin/env python3
"""
修复所有服务并验证
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

print("=" * 60)
print("修复所有服务并验证")
print("=" * 60)

# 1. 修复CDN服务文件（添加--daemon参数）
print("\n【修复CDN服务文件】...")
cdn_service = """[Unit]
Description=Singbox CDN Monitor Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/singbox-eps-node
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/cdn_monitor.py --daemon
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

sftp = client.open_sftp()
with sftp.open('/etc/systemd/system/singbox-cdn.service', 'w') as f:
    f.write(cdn_service)
sftp.close()
print("  ✅ CDN服务文件已修复（添加--daemon参数）")

# 2. 修复订阅服务文件
print("\n【修复订阅服务文件】...")
sub_service = """[Unit]
Description=Singbox Subscription Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/singbox-eps-node
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/subscription_service.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

sftp = client.open_sftp()
with sftp.open('/etc/systemd/system/singbox-sub.service', 'w') as f:
    f.write(sub_service)
sftp.close()
print("  ✅ 订阅服务文件已修复")

# 3. 重新加载并重启服务
print("\n【重新加载systemd】...")
run_cmd(client, "systemctl daemon-reload")

print("\n【重启CDN服务】...")
run_cmd(client, "systemctl restart singbox-cdn")
print("  ✅ CDN服务已重启")

time.sleep(10)

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

# 5. 检查CDN IP
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
    print(f'  ✅ 共{len(rows)}个CDN IP')
else:
    print('  ❌ 无CDN IP数据')
conn.close()
" 2>/dev/null || echo '  ❌ 数据库查询失败'""")
print(out)

# 6. 测试HTTPS订阅
print("\n【测试HTTPS订阅】...")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTPS不可用'")
print(f"  {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTP不可用'")
print(f"  {out}")

# 7. 获取订阅内容
print("\n【订阅内容验证】...")
exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub 2>/dev/null | head -c 200 || curl -s http://127.0.0.1:6969/sub 2>/dev/null | head -c 200")
if out:
    print(f"  {out[:200]}...")
else:
    print("  ❌ 无法获取")

client.close()

print("\n" + "=" * 60)
print("✅ 所有服务已修复！")
print("=" * 60)
