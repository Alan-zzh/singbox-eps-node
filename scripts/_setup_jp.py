import paramiko

print("[JP] 配置 SMTP...")
try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('52.195.179.240', username='root', password='je*pMaN8QNfCMK', timeout=30)
    
    stdin, stdout, stderr = client.exec_command("cat /root/singbox-eps-node/.env", timeout=10)
    content = stdout.read().decode('utf-8', errors='replace')
    
    lines = content.split('\n')
    clean_lines = [l for l in lines if not l.strip().startswith('MONITOR_')]
    clean_content = '\n'.join(clean_lines)
    
    monitor_config = """
# 健康监控与报警（[Trae CN] [凭据已获取] SMTP 2026-05-26）
MONITOR_SMTP_SERVER=smtp.qq.com
MONITOR_SMTP_PORT=465
MONITOR_SMTP_USER=puzangroup@qq.com
MONITOR_SMTP_PASS=ffnrcyjqwcfybhji
MONITOR_ALERT_EMAIL=puzangroup@qq.com
MONITOR_RESTART_THRESHOLD=10
MONITOR_CHECK_INTERVAL=60"""
    
    new_content = clean_content + monitor_config
    
    sftp = client.open_sftp()
    with sftp.file('/root/singbox-eps-node/.env', 'w') as f:
        f.write(new_content)
    sftp.close()
    
    cmd = """
rm -f /tmp/singbox_monitor_state.json
grep 'MONITOR_' /root/singbox-eps-node/.env
echo ""
systemctl restart singbox-monitor
echo "monitor: $(systemctl is-active singbox-monitor)"
"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=20)
    print(stdout.read().decode().strip())
    client.close()
except Exception as e:
    print(f"[失败: {e}]")
