import paramiko
import re

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 配置 SMTP...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        # Read current .env
        stdin, stdout, stderr = client.exec_command("cat /root/singbox-eps-node/.env", timeout=10)
        content = stdout.read().decode('utf-8', errors='replace')
        
        # Replace monitor section
        lines = content.split('\n')
        new_lines = []
        skip_monitor = False
        for line in lines:
            if line.strip().startswith('# 健康监控'):
                skip_monitor = True
                new_lines.append(line)
                continue
            if skip_monitor:
                stripped = line.strip()
                if stripped and not stripped.startswith('MONITOR_') and not stripped.startswith('#'):
                    skip_monitor = False
                if stripped.startswith('MONITOR_'):
                    continue
            new_lines.append(line)
        
        # Rebuild with correct monitor config
        final_lines = []
        for line in new_lines:
            if line.strip().startswith('# 健康监控'):
                final_lines.append(line)
                final_lines.append('MONITOR_SMTP_SERVER=smtp.qq.com')
                final_lines.append('MONITOR_SMTP_PORT=465')
                final_lines.append('MONITOR_SMTP_USER=puzangroup@qq.com')
                final_lines.append('MONITOR_SMTP_PASS=ffnrcyjqwcfybhji')
                final_lines.append('MONITOR_ALERT_EMAIL=puzangroup@qq.com')
                final_lines.append('MONITOR_RESTART_THRESHOLD=10')
                final_lines.append('MONITOR_CHECK_INTERVAL=60')
            else:
                final_lines.append(line)
        
        # Write back
        new_content = '\n'.join(final_lines)
        sftp = client.open_sftp()
        with sftp.file('/root/singbox-eps-node/.env', 'w') as f:
            f.write(new_content)
        sftp.close()
        
        # Verify and restart
        cmd = """
rm -f /tmp/singbox_monitor_state.json
echo '=== 配置结果 ==='
grep MONITOR /root/singbox-eps-node/.env
echo ""
systemctl restart singbox-monitor
echo "monitor: $(systemctl is-active singbox-monitor)"
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
        print(stdout.read().decode().strip())
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")
