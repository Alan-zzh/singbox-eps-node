import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n{'='*60}\n[{srv['name']}] 服务器资源评估\n{'='*60}")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        cmds = [
            ("=== 硬件配置 ===", "lscpu | grep -E 'Model name|CPU\\(s\\)|Core\\(s\\)|Socket' && free -h | grep -E 'Mem|Swap' && df -h / | tail -1"),
            ("=== 当前负载 ===", "uptime && cat /proc/loadavg"),
            ("=== 各进程资源 ===", "ps aux --sort=-%mem | head -10"),
            ("=== 监控服务占用 ===", "ps aux | grep -E 'singbox-monitor|health_monitor' | grep -v grep"),
            ("=== 订阅服务占用 ===", "ps aux | grep subscription_service | grep -v grep"),
            ("=== sing-box 占用 ===", "ps aux | grep 'sing-box' | grep -v grep"),
            ("=== 网络连接数 ===", "echo 'TCP: $(ss -tn | wc -l)' && echo 'UDP: $(ss -un | wc -l)' && echo 'ESTABLISHED: $(ss -tn state established | wc -l)'"),
        ]
        
        for title, cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            output = stdout.read().decode('utf-8', errors='replace').strip()
            print(f"\n{title}")
            print(output[:1000])
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")
