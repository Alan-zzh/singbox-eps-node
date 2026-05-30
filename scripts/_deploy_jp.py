import paramiko
import time

print("[JP] 重试部署...")
try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('52.195.179.240', username='root', password='je*pMaN8QNfCMK', timeout=30)
    sftp = client.open_sftp()
    
    with open('deploy/singbox-sub.service', 'rb') as f:
        sftp.putfo(f, '/etc/systemd/system/singbox-sub.service')
    sftp.close()
    
    cmd = """
systemctl daemon-reload
systemctl stop singbox-sub
sleep 2
systemctl start singbox-sub
sleep 5
echo "singbox-sub: $(systemctl is-active singbox-sub)"
echo "NRestarts: $(systemctl show singbox-sub --property=NRestarts)"
ss -tlnp | grep 2087
"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    print(stdout.read().decode().strip())
    client.close()
except Exception as e:
    print(f"[失败: {e}]")
