#!/usr/bin/env python3
"""同步 config_generator.py 到日本服务器"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

sftp = client.open_sftp()

print("="*60)
print("同步文件到日本服务器")
print("="*60)

files = [
    ('scripts/config_generator.py', 'scripts/config_generator.py'),
    ('scripts/config.py', 'scripts/config.py'),
    ('scripts/cdn_monitor.py', 'scripts/cdn_monitor.py'),
    ('scripts/subscription_service.py', 'scripts/subscription_service.py'),
    ('AI_DEBUG_HISTORY.md', 'AI_DEBUG_HISTORY.md'),
]

for local_name, remote_name in files:
    local_path = f'd:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\{local_name}'
    remote_path = f'/root/singbox-eps-node/{remote_name}'
    sftp.put(local_path, remote_path)
    print(f"  {local_name}")

sftp.close()

print("\n重新生成服务端配置...")
_, stdout, stderr = client.exec_command("cd /root/singbox-eps-node && python3 scripts/config_generator.py 2>&1")
out = stdout.read().decode() + stderr.read().decode()
print(out)

print("重启服务...")
_, stdout, _ = client.exec_command("systemctl restart singbox && sleep 2 && systemctl is-active singbox")
print(f"singbox: {stdout.read().decode().strip()}")

client.close()
print("\n✅ 同步完成")
