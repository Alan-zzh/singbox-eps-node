#!/usr/bin/env python3
"""
更新 systemd 服务配置并重启
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

print("=== 1. 更新 singbox-sub.service ===")
sub_service = """[Unit]
Description=Singbox Subscription Service
After=network.target

[Service]
EnvironmentFile=/root/singbox-manager/.env
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/subscription_service.py
Restart=always
RestartSec=5
WorkingDirectory=/root/singbox-manager

[Install]
WantedBy=multi-user.target
"""

# 写入服务文件
stdin, stdout, stderr = client.exec_command(f"cat > /etc/systemd/system/singbox-sub.service << 'EOF'\n{sub_service}\nEOF")
stdout.channel.recv_exit_status()
print("✅ singbox-sub.service 已更新")

print("\n=== 2. 更新 singbox-cdn.service ===")
cdn_service = """[Unit]
Description=Singbox CDN Monitor
After=network.target

[Service]
EnvironmentFile=/root/singbox-manager/.env
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/cdn_monitor.py --daemon
Restart=always
RestartSec=10
WorkingDirectory=/root/singbox-manager

[Install]
WantedBy=multi-user.target
"""

stdin, stdout, stderr = client.exec_command(f"cat > /etc/systemd/system/singbox-cdn.service << 'EOF'\n{cdn_service}\nEOF")
stdout.channel.recv_exit_status()
print("✅ singbox-cdn.service 已更新")

print("\n=== 3. 重新加载 systemd 并重启服务 ===")
run_cmd(client, "systemctl daemon-reload")
print("✅ systemd 已重新加载")

run_cmd(client, "systemctl restart singbox-sub")
print("✅ 订阅服务已重启")

run_cmd(client, "systemctl restart singbox-cdn")
print("✅ CDN 监控服务已重启")

import time
time.sleep(5)

print("\n=== 4. 检查服务状态 ===")
exit_code, out, err = run_cmd(client, "systemctl is-active singbox-sub singbox-cdn")
print(out)

print("\n=== 5. 测试订阅链接 ===")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub", timeout=30)

# 解码Base64
import base64
try:
    decoded = base64.b64decode(out).decode('utf-8')
    print("\n解码后的订阅链接:")
    print(decoded)
except:
    print("\n无法解码，原始内容:")
    print(out[:1000])

client.close()
print("\n✅ 完成")
