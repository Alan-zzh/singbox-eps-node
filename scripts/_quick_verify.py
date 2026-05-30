import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 验证...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        # Simple curl test
        stdin, stdout, stderr = client.exec_command("curl -sk https://127.0.0.1:2087/singbox/SG 2>/dev/null | head -c 200", timeout=10)
        print(f"  响应: {stdout.read().decode()[:200]}...")
        
        # Service status
        stdin, stdout, stderr = client.exec_command("sleep 5 && systemctl is-active singbox-sub && systemctl is-active singbox-monitor", timeout=20)
        status = stdout.read().decode().strip()
        print(f"  服务: {status}")
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")
