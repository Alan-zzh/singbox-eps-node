#!/usr/bin/env python3
"""
修复订阅服务文件
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

# 修复订阅服务文件
print("【修复订阅服务文件】...")
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

# 重新加载并重启服务
print("\n【重新加载systemd】...")
run_cmd(client, "systemctl daemon-reload")
print("  ✅ systemd配置已重新加载")

print("\n【重启CDN服务】...")
run_cmd(client, "systemctl restart singbox-cdn")
print("  ✅ CDN服务已重启")

import time
time.sleep(5)

print("\n【重启订阅服务】...")
run_cmd(client, "systemctl restart singbox-sub")
print("  ✅ 订阅服务已重启")

time.sleep(5)

# 检查服务状态
print("\n【检查服务状态】...")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    status = "✅ 运行中" if out == 'active' else "❌ 未运行"
    print(f"  {svc}: {status}")

client.close()

print("\n✅ 服务文件修复完成！")
