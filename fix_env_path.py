#!/usr/bin/env python3
"""
修复 .env 文件路径问题
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

print("=== 1. 查找 .env 文件 ===")
exit_code, out, err = run_cmd(client, "find /root -name '.env' 2>/dev/null")
print(out)

print("\n=== 2. 检查 /root/singbox-eps-node/.env ===")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/.env 2>/dev/null && echo 'EXISTS' || echo 'NOT_FOUND'")
print(out)

print("\n=== 3. 检查 /root/singbox-manager/.env ===")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-manager/.env 2>/dev/null && echo 'EXISTS' || echo 'NOT_FOUND'")
print(out)

# 创建符号链接或复制文件
print("\n=== 4. 创建 .env 符号链接 ===")
exit_code, out, err = run_cmd(client, """
if [ -f /root/singbox-eps-node/.env ]; then
    ln -sf /root/singbox-eps-node/.env /root/singbox-manager/.env
    echo "SYMLINK_CREATED"
elif [ -f /root/singbox-manager/.env ]; then
    echo "ALREADY_EXISTS"
else
    echo "NO_ENV_FOUND"
fi
""")
print(out)

print("\n=== 5. 更新 systemd 服务配置 ===")
# 使用正确的路径
sub_service = """[Unit]
Description=Singbox Subscription Service
After=network.target

[Service]
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/subscription_service.py
Restart=always
RestartSec=5
WorkingDirectory=/root/singbox-manager

[Install]
WantedBy=multi-user.target
"""

stdin, stdout, stderr = client.exec_command(f"cat > /etc/systemd/system/singbox-sub.service << 'EOF'\n{sub_service}\nEOF")
stdout.channel.recv_exit_status()
print("✅ singbox-sub.service 已更新")

cdn_service = """[Unit]
Description=Singbox CDN Monitor
After=network.target

[Service]
EnvironmentFile=/root/singbox-eps-node/.env
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

print("\n=== 6. 重新加载并重启服务 ===")
run_cmd(client, "systemctl daemon-reload")
run_cmd(client, "systemctl reset-failed singbox-sub singbox-cdn")
run_cmd(client, "systemctl restart singbox-sub")
run_cmd(client, "systemctl restart singbox-cdn")
print("✅ 服务已重启")

import time
time.sleep(5)

print("\n=== 7. 检查服务状态 ===")
exit_code, out, err = run_cmd(client, "systemctl is-active singbox-sub singbox-cdn")
print(f"服务状态: {out}")

print("\n=== 8. 测试订阅链接 ===")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub", timeout=30)

import base64
try:
    decoded = base64.b64decode(out).decode('utf-8')
    print("\n✅ 订阅链接:")
    print(decoded)
except:
    print("\n❌ 解码失败")
    print(out[:500])

client.close()
print("\n✅ 完成")
