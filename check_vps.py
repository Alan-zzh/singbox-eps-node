#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

print('=== 检查 VPS 状态 ===')

# 1. 检查目录
stdin, stdout, stderr = ssh.exec_command('ls /root/singbox-eps-node/ 2>&1 | head -15')
print('\n[目录内容]')
print(stdout.read().decode()[:500])

# 2. 检查 Flask
stdin, stdout, stderr = ssh.exec_command('python3 -c "import flask; print(flask.__version__)" 2>&1')
print('\n[Flask]')
print(stdout.read().decode().strip())

# 3. 检查 sing-box
stdin, stdout, stderr = ssh.exec_command('sing-box version 2>&1')
print('\n[sing-box]')
print(stdout.read().decode().strip())

# 4. 检查 .env
stdin, stdout, stderr = ssh.exec_command('cat /root/singbox-eps-node/.env 2>&1 | head -10')
print('\n[.env]')
print(stdout.read().decode().strip())

# 5. 检查证书
stdin, stdout, stderr = ssh.exec_command('ls -la /root/singbox-eps-node/cert/ 2>&1')
print('\n[证书]')
print(stdout.read().decode().strip())

# 6. 检查 config.json
stdin, stdout, stderr = ssh.exec_command('ls -la /root/singbox-eps-node/config.json 2>&1')
print('\n[config.json]')
print(stdout.read().decode().strip())

# 7. 检查服务状态
stdin, stdout, stderr = ssh.exec_command('systemctl is-active singbox singbox-sub singbox-cdn singbox-tgbot 2>&1')
print('\n[服务状态]')
print(stdout.read().decode().strip())

# 8. 检查端口
stdin, stdout, stderr = ssh.exec_command('ss -tlnp | grep -E "443|6969|2053|2083|1080" 2>&1')
print('\n[端口]')
print(stdout.read().decode().strip())

# 9. 测试订阅
stdin, stdout, stderr = ssh.exec_command('curl -sk https://127.0.0.1:6969/sub/JP 2>&1 | head -c 200')
print('\n[订阅测试]')
print(stdout.read().decode().strip()[:200])

ssh.close()
