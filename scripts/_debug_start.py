import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 排查启动失败原因...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        # 1. Check ExecStartPre output
        stdin, stdout, stderr = client.exec_command("journalctl -u singbox-sub --no-pager -n 30 2>/dev/null | grep -E 'ExecStartPre|error|fail|kill|pkill|address|port|bind' | tail -15", timeout=10)
        print(f"  日志关键词:\n{stdout.read().decode()[:1000]}")
        
        # 2. Check what process is on port 2087
        stdin, stdout, stderr = client.exec_command("ss -tlnp | grep 2087", timeout=10)
        port_out = stdout.read().decode().strip()
        print(f"  端口 2087: {port_out}")
        
        # 3. Check all python processes
        stdin, stdout, stderr = client.exec_command("ps aux | grep subscription_service | grep -v grep", timeout=10)
        procs = stdout.read().decode().strip()
        print(f"  进程: {procs[:500] if procs else '无'}")
        
        # 4. Try manual start
        stdin, stdout, stderr = client.exec_command("cd /root/singbox-eps-node && timeout 10 python3 scripts/subscription_service.py 2>&1 &", timeout=5)
        import time
        time.sleep(3)
        
        # 5. Check if it started
        stdin, stdout, stderr = client.exec_command("ss -tlnp | grep 2087 && echo '---' && ps aux | grep subscription_service | grep -v grep | head -3", timeout=10)
        print(f"  手动启动后: {stdout.read().decode()[:500]}")
        
        # 6. Kill manual and restart systemd
        stdin, stdout, stderr = client.exec_command("pkill -9 -f subscription_service; sleep 2; systemctl start singbox-sub; sleep 5; systemctl is-active singbox-sub", timeout=20)
        print(f"  systemd 重启: {stdout.read().decode().strip()}")
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")
