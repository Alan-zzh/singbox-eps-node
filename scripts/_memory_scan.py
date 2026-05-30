import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n{'='*70}\n[{srv['name']}] 深度内存扫描\n{'='*70}")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        cmds = [
            ("=== 所有进程内存占用（按内存排序）===", 
             "ps aux --sort=-%mem | awk 'NR>1{printf \"PID=%-7s MEM=%-6s%% RSS=%-5sMB COMMAND=%s %s %s\\n\", $2, $4, $6/1024, $11, $12, $13}' | head -15"),
            ("=== 系统服务状态 ===", 
             "systemctl list-units --type=service --state=running --no-pager 2>/dev/null | grep -v UNIT | head -20"),
            ("=== 开机自启服务 ===", 
             "systemctl list-unit-files --state=enabled --no-pager 2>/dev/null | grep -v UNIT | head -20"),
            ("=== cdn_monitor 进程详情 ===", 
             "ps aux | grep cdn_monitor | grep -v grep"),
            ("=== systemd-journald 占用 ===", 
             "journalctl --disk-usage 2>/dev/null && ls -lh /var/log/journal/ 2>/dev/null"),
            ("=== snap 服务 ===", 
             "snap list 2>/dev/null && echo '---' && systemctl status snap* --no-pager 2>/dev/null | head -20"),
            ("=== 内核缓存/缓冲区 ===", 
             "free -m && echo '---' && cat /proc/meminfo | grep -E 'Active:|Inactive:|Buffers:|Cached:|SReclaimable:|SwapTotal:|SwapFree:'"),
            ("=== 可优化的 systemd 服务 ===", 
             "systemctl list-units --type=service --state=running --no-pager 2>/dev/null | grep -vE 'sshd|singbox|network|systemd-journald|dbus|cron|rsyslog|udhcpc|cloud-init' | grep -v UNIT"),
        ]
        
        for title, cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
            output = stdout.read().decode('utf-8', errors='replace').strip()
            print(f"\n{title}")
            print(output[:2000])
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")
