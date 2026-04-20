#!/usr/bin/env python3
"""
检查服务器上的 .env 文件
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

print("=== 检查 .env 文件 ===")
exit_code, out, err = run_cmd(client, "cat /root/singbox-manager/.env | grep -E 'SERVER_IP|CF_DOMAIN'")
print(out)

print("\n=== 检查 systemd 服务配置 ===")
exit_code, out, err = run_cmd(client, "cat /etc/systemd/system/singbox-sub.service")
print(out)

print("\n=== 直接测试 subscription_service 的 SERVER_IP 和 CF_DOMAIN ===")
exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from subscription_service import SERVER_IP, CF_DOMAIN, DB_PATH
print('SERVER_IP:', repr(SERVER_IP))
print('CF_DOMAIN:', repr(CF_DOMAIN))
print('DB_PATH:', DB_PATH)
"
""")
print(out)
if err:
    print(f"错误: {err}")

client.close()
