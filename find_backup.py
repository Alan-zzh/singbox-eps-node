#!/usr/bin/env python3
"""
检查服务器上的配置备份
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

print("【查找.env备份】")
exit_code, out, err = run_cmd(client, "find /root -name '*.env*' -o -name '.env.bak*' 2>/dev/null")
print(out if out else '无备份')

print("\n【查找singbox相关目录】")
exit_code, out, err = run_cmd(client, "ls -la /root/ | grep -i sing")
print(out)

print("\n【查找证书文件】")
exit_code, out, err = run_cmd(client, "find /root -name '*.pem' -o -name '*.crt' -o -name '*.key' 2>/dev/null")
print(out if out else '无证书')

print("\n【查找数据库文件】")
exit_code, out, err = run_cmd(client, "find /root -name '*.db' 2>/dev/null")
print(out if out else '无数据库')

print("\n【检查Cloudflare证书】")
exit_code, out, err = run_cmd(client, "ls -la /root/.acme.sh/ 2>/dev/null || echo '无acme.sh'")
print(out)

client.close()
