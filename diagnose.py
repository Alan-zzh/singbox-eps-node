#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

print('=== 诊断 singbox 问题 ===')

# 1. 检查 config.json 内容
stdin, stdout, stderr = ssh.exec_command('cat /root/singbox-eps-node/config.json')
config = stdout.read().decode()
print('\n[config.json]')
print(config[:1000])

# 2. 检查 singbox 日志
stdin, stdout, stderr = ssh.exec_command('journalctl -u singbox --no-pager -n 20')
print('\n[singbox 日志]')
print(stdout.read().decode()[-1000:])

# 3. 尝试手动运行 singbox
stdin, stdout, stderr = ssh.exec_command('/usr/local/bin/sing-box check -c /root/singbox-eps-node/config.json 2>&1')
print('\n[配置检查]')
print(stdout.read().decode()[-500:])
err = stderr.read().decode()
if err:
    print(f'[错误] {err[-500:]}')

# 4. 检查 .env 中的 Reality 密钥
stdin, stdout, stderr = ssh.exec_command('grep REALITY /root/singbox-eps-node/.env')
print('\n[Reality 密钥]')
print(stdout.read().decode())

ssh.close()
