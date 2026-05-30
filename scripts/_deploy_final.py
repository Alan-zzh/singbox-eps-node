import paramiko
import os

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

files = {
    'scripts/health_monitor.py': '/root/singbox-eps-node/scripts/health_monitor.py',
    'deploy/singbox-sub.service': '/etc/systemd/system/singbox-sub.service',
    'deploy/singbox-monitor.service': '/etc/systemd/system/singbox-monitor.service',
}

for srv in servers:
    print(f"\n[{srv['name']}] 上传文件...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        sftp = client.open_sftp()
        
        for local, remote in files.items():
            full_local = os.path.join('d:\\Documents\\Syncdisk\\Work\\job\\singbox-eps-node', local.replace('/', '\\'))
            print(f"  上传 {local} -> {remote}")
            sftp.put(full_local, remote)
            print(f"    ✅ OK")
        
        sftp.close()
        
        # Deploy
        cmd = """
systemctl daemon-reload
systemctl restart singbox-sub
echo "singbox-sub: $(systemctl is-active singbox-sub)"
systemctl enable singbox-monitor 2>/dev/null
systemctl restart singbox-monitor
sleep 2
echo "singbox-monitor: $(systemctl is-active singbox-monitor)"
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        output = stdout.read().decode()
        print(output.strip())
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")
