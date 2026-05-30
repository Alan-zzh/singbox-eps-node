import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 完成部署...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        sftp = client.open_sftp()
        
        # Upload files (both servers)
        with open('scripts/health_monitor.py', 'r', encoding='utf-8') as f:
            sftp.putfo(f, '/root/singbox-eps-node/scripts/health_monitor.py')
        
        with open('deploy/singbox-sub.service', 'r', encoding='utf-8') as f:
            sftp.putfo(f, '/etc/systemd/system/singbox-sub.service')
        
        with open('deploy/singbox-monitor.service', 'r', encoding='utf-8') as f:
            sftp.putfo(f, '/etc/systemd/system/singbox-monitor.service')
        
        sftp.close()
        
        # Restart and enable
        cmds = """
systemctl daemon-reload

# 重启订阅服务
systemctl restart singbox-sub
echo "singbox-sub: $(systemctl is-active singbox-sub)"

# 启用并启动监控
systemctl daemon-reload
systemctl enable singbox-monitor
systemctl restart singbox-monitor
sleep 2
echo "singbox-monitor: $(systemctl is-active singbox-monitor)"

# 验证
echo ""
grep ExecStartPre /etc/systemd/system/singbox-sub.service
echo ""
journalctl -u singbox-monitor --no-pager -n 5 2>/dev/null | tail -3
"""
        stdin, stdout, stderr = client.exec_command(cmds, timeout=60)
        output = stdout.read().decode('utf-8', errors='replace')
        print(output[:1500])
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n部署完成")
