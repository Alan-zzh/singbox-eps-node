#!/usr/bin/env python3
"""
检查CDN服务详细日志
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

print("【CDN服务详细日志】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 20 2>&1")
print(out)

print("\n【CDN服务文件】")
exit_code, out, err = run_cmd(client, "cat /etc/systemd/system/singbox-cdn.service")
print(out)

print("\n【CDN脚本路径】")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/scripts/cdn_monitor.py")
print(out)

print("\n【手动运行CDN脚本测试】")
exit_code, out, err = run_cmd(client, "cd /root/singbox-eps-node && python3 scripts/cdn_monitor.py 2>&1 | head -20", timeout=15)
print(out if out else '无输出')

client.close()
