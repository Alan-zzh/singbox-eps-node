import paramiko

servers = [
    {'name': 'JP', 'ip': '52.195.179.240', 'user': 'root', 'pass': 'je*pMaN8QNfCMK'},
    {'name': 'SG', 'ip': '13.212.37.11', 'user': 'root', 'pass': 'jbfCMP75@jh.dxclouds.com'},
]

for srv in servers:
    print(f'\n{"="*70}')
    print(f'  {srv["name"]} Server: {srv["ip"]} - 深度暗病排查')
    print(f'{"="*70}')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        cmds = [
            ('1.singbox ERROR日志', 'grep -i "ERROR\\|FATAL\\|panic\\|WARN" /var/log/singbox.log 2>&1 | grep -v "5151" | tail -30'),
            ('2.singbox-sub错误日志', 'grep -i "error\\|traceback\\|exception\\|fail" /var/log/subscription_service.log 2>&1 | tail -20'),
            ('3.singbox-cdn错误日志', 'journalctl -u singbox-cdn --since "1 day ago" -p warning --no-pager 2>&1 | tail -30'),
            ('4.singbox-sub重启记录', 'journalctl -u singbox-sub --since "1 day ago" --no-pager | grep -iE "stop|start|restart|fail|exit|kill|signal" | tail -15'),
            ('5.singbox重启记录', 'journalctl -u singbox --since "1 day ago" --no-pager | grep -iE "stop|start|restart|fail|exit|kill|signal" | tail -15'),
            ('6.内存状态', 'free -h && echo "---" && cat /proc/meminfo | grep -iE "MemAvailable|SwapFree|Committed_AS"'),
            ('7.磁盘inode', 'df -i / && echo "---" && df -h /'),
            ('8.OOM记录', 'dmesg | grep -i "oom\\|out of memory\\|killed process" 2>&1 | tail -10 || echo "无OOM"'),
            ('9.singbox进程状态', 'ps aux | grep sing-box | grep -v grep'),
            ('10.singbox-sub进程状态', 'ps aux | grep subscription_service | grep -v grep'),
            ('11.singbox连接数', 'ss -s 2>&1'),
            ('12.端口监听完整性', 'ss -tlnp | grep -E "443|8443|2053|2083|2087" && echo "---UDP---" && ss -ulnp | grep -E "443"'),
            ('13.CDN数据库状态', 'cd /root/singbox-eps-node && python3 -c "import sqlite3,json; db=sqlite3.connect(\'data/singbox.db\'); c=db.cursor(); tables=[r[0] for r in c.execute(\'SELECT name FROM sqlite_master WHERE type=\\\\\"table\\\\\"\').fetchall()]; print(\'Tables:\',tables); [print(f\'  {t}: {c.execute(f\"SELECT COUNT(*) FROM {t}\").fetchone()[0]} rows\') for t in tables]; db.close()" 2>&1'),
            ('14.CDN当前IP评分', 'cd /root/singbox-eps-node && python3 -c "import sqlite3,json; db=sqlite3.connect(\'data/singbox.db\'); c=db.cursor(); c.execute(\'SELECT key,value FROM cdn_settings WHERE key IN (\"vless_ws_cdn_ip\",\"vless_upgrade_cdn_ip\",\"trojan_ws_cdn_ip\",\"cdn_ips_list\")\'); [print(f\'{k}={v[:120]}\') for k,v in c.fetchall()]; db.close()" 2>&1'),
            ('15.health_check最近执行', 'journalctl -u cron --since "1 day ago" --no-pager 2>&1 | grep health | tail -5 || echo "无cron日志"; ls -la /root/singbox-eps-node/data/health_* 2>/dev/null || echo "无health文件"'),
            ('16.系统异常服务', 'systemctl --failed 2>&1'),
            ('17.singbox日志错误分类统计', 'grep -c "ERROR" /var/log/singbox.log 2>&1; echo "---ERROR分类---"; grep "ERROR" /var/log/singbox.log 2>&1 | sed "s/.*ERROR //" | sed "s/\\[.*//" | sort | uniq -c | sort -rn | head -10'),
            ('18.证书状态', 'openssl x509 -enddate -noout -in /root/singbox-eps-node/cert/cert.pem 2>&1 || echo "无cert.pem"; ls -la /root/singbox-eps-node/cert/ 2>&1'),
            ('19.iptables规则完整性', 'iptables -L INPUT -v -n -x 2>&1 | grep -E "dpt:(443|8443|2053|2083|2087|21000)" | head -10'),
            ('20.HY2端口跳跃规则', 'iptables -t nat -L DNAT -n 2>&1 | head -5; iptables -t nat -L -n 2>&1 | grep -c "21000" || echo "0"'),
            ('21.Swap使用', 'cat /proc/swaps 2>&1; swapon --show 2>&1'),
            ('22.singbox配置验证', 'sing-box check -c /root/singbox-eps-node/config.json 2>&1 && echo "config OK" || echo "config ERROR"'),
            ('23.订阅服务API全量测试', 'echo "--- /api/cdn-status ---"; curl -sk https://localhost:2087/api/cdn-status 2>&1 | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f\"code={d[\'code\']}, msg={d[\'msg\']}\")" 2>&1; echo "--- /api/traffic ---"; curl -sk https://localhost:2087/api/traffic 2>&1 | head -c 200; echo; echo "--- /sub ---"; curl -sk https://localhost:2087/sub 2>&1 | head -c 100'),
            ('24.singbox日志最近10行', 'tail -10 /var/log/singbox.log 2>&1'),
            ('25.cdn_monitor最近完整运行', 'journalctl -u singbox-cdn --since "1 day ago" --no-pager -n 50 2>&1 | grep -iE "error|warn|fail|异常|超时|timeout|refused|存活|死亡|替换" | tail -20'),
        ]
        for label, cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=25)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            result = out if out else err
            if not result:
                result = '(无输出)'
            print(f'\n[{label}]')
            print(result[:1500])
    except Exception as e:
        print(f'连接失败: {e}')
    finally:
        client.close()
