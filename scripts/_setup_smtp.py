import paramiko

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
        
        # Update .env on server
        cmd = """
sed -i 's/^MONITOR_SMTP_SERVER=.*/MONITOR_SMTP_SERVER=smtp.qq.com/' /root/singbox-eps-node/.env
sed -i 's/^MONITOR_SMTP_USER=.*/MONITOR_SMTP_USER=puzangroup@qq.com/' /root/singbox-eps-node/.env
sed -i 's/^MONITOR_SMTP_PASS=.*/MONITOR_SMTP_PASS=ffnrcyjqwcfybhji/' /root/singbox-eps-node/.env
sed -i 's/^MONITOR_ALERT_EMAIL=.*/MONITOR_ALERT_EMAIL=puzangroup@qq.com/' /root/singbox-eps-node/.env
sed -i 's/^MONITOR_CHECK_INTERVAL=.*/MONITOR_CHECK_INTERVAL=60/' /root/singbox-eps-node/.env
echo '=== .env 监控配置 ==='
grep MONITOR /root/singbox-eps-node/.env

# Clear state and restart monitor
rm -f /tmp/singbox_monitor_state.json
systemctl restart singbox-monitor
echo ""
echo "monitor: $(systemctl is-active singbox-monitor)"
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=20)
        output = stdout.read().decode('utf-8', errors='replace')
        print(output.strip())
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")
