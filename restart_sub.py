#!/usr/bin/env python3
"""
强制重启订阅服务并测试
"""
import paramiko
import base64
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

print("=== 1. 停止订阅服务 ===")
run_cmd(client, "systemctl stop singbox-sub")
print("✅ 已停止")

print("\n=== 2. 查看订阅服务日志（最后20行）===")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 20")
print(out)

print("\n=== 3. 启动订阅服务 ===")
run_cmd(client, "systemctl start singbox-sub")
print("✅ 已启动")

print("\n=== 4. 等待服务启动 ===")
time.sleep(5)

print("\n=== 5. 检查服务状态 ===")
exit_code, out, err = run_cmd(client, "systemctl is-active singbox-sub")
print(f"服务状态: {out}")

print("\n=== 6. 获取订阅并解码 ===")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub", timeout=30)

try:
    decoded = base64.b64decode(out).decode('utf-8')
    print("\n解码后的订阅链接:")
    print(decoded)
except:
    print("\n无法解码，原始内容:")
    print(out[:1000])

client.close()
print("\n✅ 完成")
