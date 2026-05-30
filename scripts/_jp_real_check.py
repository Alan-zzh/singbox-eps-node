#!/usr/bin/env python3
import paramiko
import sys

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('52.195.179.240', username='root', password='je*pMaN8QNfCMK', timeout=15)

cmds = [
    ('1.singbox最近50行日志', 'tail -50 /var/log/singbox.log 2>&1'),
    ('2.singbox ERROR统计', 'grep -c ERROR /var/log/singbox.log 2>&1; echo "---ERROR分类---"; grep ERROR /var/log/singbox.log 2>&1 | tail -20'),
    ('3.singbox-sub最近日志', 'tail -30 /var/log/subscription_service.log 2>&1'),
    ('4.singbox-cdn最近日志', 'journalctl -u singbox-cdn --no-pager -n 50 2>&1'),
    ('5.内存和磁盘', 'free -h; echo "---"; df -h /; echo "---"; cat /proc/meminfo | grep -iE "MemAvailable|SwapFree"'),
    ('6.连接数和端口', 'ss -s; echo "---"; ss -tlnp | grep -E "443|8443|2053|2083|2087"; echo "---UDP---"; ss -ulnp | grep 443'),
    ('7.CDN数据库当前IP', 'cd /root/singbox-eps-node && python3 -c "import sqlite3,json; db=sqlite3.connect(\'data/singbox.db\'); c=db.cursor(); c.execute(\'SELECT key,value FROM cdn_settings\'); [print(f\'{k}={v[:200]}\') for k,v in c.fetchall()]; db.close()" 2>&1'),
    ('8.进程状态', 'ps aux | grep -E "sing-box|subscription|cdn_monitor" | grep -v grep'),
    ('9.OOM和dmesg', 'dmesg | grep -i "oom\\|killed" 2>&1 | tail -5 || echo "无OOM"'),
    ('10.系统负载和运行时间', 'uptime; echo "---"; cat /proc/loadavg'),
    ('11.singbox-sub错误日志', 'grep -i "error\\|traceback\\|exception\\|fail" /var/log/subscription_service.log 2>&1 | tail -20'),
    ('12.singbox重启记录', 'journalctl -u singbox --since "1 day ago" --no-pager | grep -iE "stop|start|restart|fail|exit|kill|signal" | tail -15'),
    ('13.订阅API测试', 'curl -sk https://localhost:2087/api/cdn-status 2>&1 | head -c 500; echo; echo "---"; curl -sk https://localhost:2087/api/traffic 2>&1 | head -c 200'),
    ('14.iptables流量统计', 'iptables -L INPUT -v -n -x 2>&1 | grep -E "dpt:(443|8443|2053|2083|2087|21000)" | head -10'),
    ('15.最近用户连接', 'grep -i "connected\\|inbound" /var/log/singbox.log 2>&1 | tail -20'),
]

for label, cmd in cmds:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=25)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    result = out if out else (err if err else '(无输出)')
    print(f'\n=== {label} ===')
    print(result[:3000])

client.close()
