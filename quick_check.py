#!/usr/bin/env python3
"""
快速检查服务器状态
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

print("【检查.env文件】")
exit_code, out, err = run_cmd(client, "cat /root/singbox-eps-node/.env 2>/dev/null | head -10 || echo '不存在'")
print(out)

print("\n【检查目录结构】")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/")
print(out)

print("\n【检查脚本文件】")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/scripts/")
print(out)

print("\n【服务状态】")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc} 2>/dev/null || echo 'inactive'")
    print(f"  {svc}: {out}")

print("\n【systemd服务文件】")
exit_code, out, err = run_cmd(client, "cat /etc/systemd/system/singbox-sub.service 2>/dev/null || echo '不存在'")
print(out)

client.close()
