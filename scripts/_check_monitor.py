import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 查看监控输出...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        # Wait for first check cycle
        import time
        time.sleep(65)
        
        stdin, stdout, stderr = client.exec_command("journalctl -u singbox-monitor --no-pager -n 20 2>/dev/null | grep -v 'Started\\|Stopping\\|Deactivated\\|Stopped'")
        print(stdout.read().decode()[:2000])
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")
