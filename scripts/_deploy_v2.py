import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 部署方案 C...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        sftp = client.open_sftp()
        
        with open('scripts/health_monitor.py', 'rb') as f:
            sftp.putfo(f, '/root/singbox-eps-node/scripts/health_monitor.py')
        sftp.close()
        
        cmd = """
# 清理旧状态
rm -f /tmp/singbox_monitor_state.json

# 重启监控服务
systemctl daemon-reload
systemctl restart singbox-monitor
sleep 2

# 验证
echo "singbox-sub: $(systemctl is-active singbox-sub)"
echo "monitor: $(systemctl is-active singbox-monitor)"
echo ""
echo "=== 监控日志 ==="
journalctl -u singbox-monitor --no-pager -n 8 2>/dev/null | tail -5
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        output = stdout.read().decode('utf-8', errors='replace')
        print(output.strip())
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")
