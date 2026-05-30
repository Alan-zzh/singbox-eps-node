import paramiko
import time

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

time.sleep(5)

for srv in servers:
    print(f"\n[{srv['name']}] 最终验证...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        cmds = [
            "echo '=== 服务状态 ===' && systemctl is-active singbox-sub && systemctl is-active singbox-monitor",
            "echo '=== ExecStartPre ===' && grep ExecStartPre /etc/systemd/system/singbox-sub.service",
            "echo '=== 监控状态 ===' && systemctl status singbox-monitor --no-pager | head -5",
            "echo '=== 订阅验证 ===' && curl -sk https://127.0.0.1:2087/singbox/$(grep COUNTRY_CODE /root/singbox-eps-node/.env | head -1 | cut -d= -f2) 2>/dev/null | python3 -c 'import sys,json; c=json.load(sys.stdin); print(f\"OK: {len(c.get(\\\"outbounds\\\",[]))} outbounds\")' 2>&1 || echo FAIL",
        ]
        
        for cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
            output = stdout.read().decode('utf-8', errors='replace').strip()
            print(f"  {output[:300]}")
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n最终验证完成")
