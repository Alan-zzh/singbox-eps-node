import paramiko
import time

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 部署状态检查...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        cmds = [
            ("服务状态", "systemctl is-active singbox-sub && systemctl is-active singbox-monitor"),
            ("ExecStartPre", "grep ExecStartPre /etc/systemd/system/singbox-sub.service 2>/dev/null || echo 'NOT FOUND'"),
            ("health_monitor.py", "ls -la /root/singbox-eps-node/scripts/health_monitor.py 2>/dev/null || echo 'NOT FOUND'"),
            ("singbox-monitor", "systemctl status singbox-monitor --no-pager 2>/dev/null | head -8"),
            ("端口占用", "ss -tlnp | grep 2087"),
            ("订阅测试", "curl -sk https://127.0.0.1:2087/singbox/$(grep COUNTRY_CODE /root/singbox-eps-node/.env | head -1 | cut -d= -f2) 2>/dev/null | python3 -c 'import sys,json; c=json.load(sys.stdin); print(f\"OK: {len(c.get(\"outbounds\",[]))} outbounds\")' 2>&1 || echo 'FAIL'"),
        ]
        
        for title, cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
            output = stdout.read().decode('utf-8', errors='replace').strip()
            print(f"  {title}: {output[:200]}")
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")
