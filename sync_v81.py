import paramiko
import os

SERVER_IP = '54.250.149.157'
SERVER_PORT = 22
SERVER_USER = 'root'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'
REMOTE_DIR = '/root/singbox-eps-node'
LOCAL_BASE = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node'

FILES = [
    'scripts/config.py',
    'scripts/subscription_service.py',
    'scripts/config_generator.py',
    'scripts/cdn_monitor.py',
    'AI_DEBUG_HISTORY.md',
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, SERVER_PORT, SERVER_USER, SERVER_PASS, timeout=30, allow_agent=False, look_for_keys=False)

sftp = client.open_sftp()
for f in FILES:
    remote = REMOTE_DIR + '/' + f.replace('\\', '/')
    local = os.path.join(LOCAL_BASE, f)
    sftp.put(local, remote)
    print(f"✅ {f}")
sftp.close()

# Restart services
_, out, _ = client.exec_command("systemctl restart singbox-sub singbox-cdn && sleep 2 && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
print(f"\n✅ 服务重启: {out.read().decode().strip()}")

client.close()
print("✅ 日本服务器 v1.0.81 更新完成")
