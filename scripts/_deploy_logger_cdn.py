#!/usr/bin/env python3
import paramiko

servers = [
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
]

for srv in servers:
    print(f"\n=== {srv['name']} 服务器 ===")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        sftp = client.open_sftp()

        local_logger = 'scripts/logger.py'
        remote_logger = '/root/singbox-eps-node/scripts/logger.py'
        local_cdn = 'scripts/cdn_monitor.py'
        remote_cdn = '/root/singbox-eps-node/scripts/cdn_monitor.py'

        print(f"[{srv['name']}] 上传 logger.py...")
        sftp.put(local_logger, remote_logger)

        print(f"[{srv['name']}] 上传 cdn_monitor.py...")
        sftp.put(local_cdn, remote_cdn)

        sftp.close()

        print(f"[{srv['name']}] 重启 singbox-cdn 服务...")
        cmds = """
systemctl restart singbox-cdn
sleep 2
echo "服务状态: $(systemctl is-active singbox-cdn)"
echo ""
echo "=== 最近1分钟日志 ==="
journalctl -u singbox-cdn --no-pager -n 20 --since "1 minute ago"
"""
        stdin, stdout, stderr = client.exec_command(cmds, timeout=60)
        output = stdout.read().decode('utf-8', errors='replace')
        print(output)

        client.close()
        print(f"[{srv['name']}] 完成！")
    except Exception as e:
        print(f"[{srv['name']}] 失败: {e}")

print("\n=== 所有服务器部署完成 ===")
