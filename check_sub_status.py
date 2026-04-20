#!/usr/bin/env python3
"""
检查订阅服务状态和日志
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

print("=== 1. 检查服务状态 ===")
exit_code, out, err = run_cmd(client, "systemctl status singbox-sub --no-pager")
print(out)

print("\n=== 2. 检查服务日志（最后30行）===")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 30")
print(out)

print("\n=== 3. 检查端口是否监听 ===")
exit_code, out, err = run_cmd(client, "netstat -tlnp | grep 6969 || ss -tlnp | grep 6969")
print(out)

print("\n=== 4. 测试本地访问 ===")
exit_code, out, err = run_cmd(client, "curl -v http://127.0.0.1:6969/sub 2>&1 | head -30", timeout=30)
print(out)

print("\n=== 5. 检查 .env 文件 ===")
exit_code, out, err = run_cmd(client, "cat /root/singbox-manager/.env | head -20")
print(out)

client.close()
