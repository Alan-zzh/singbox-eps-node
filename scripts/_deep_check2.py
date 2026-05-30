import paramiko

servers = [
    {'name': 'JP', 'ip': '52.195.179.240', 'user': 'root', 'pass': 'je*pMaN8QNfCMK'},
    {'name': 'SG', 'ip': '13.212.37.11', 'user': 'root', 'pass': 'jbfCMP75@jh.dxclouds.com'},
]

for srv in servers:
    print(f'\n{"="*70}')
    print(f'  {srv["name"]} - 暗病深挖')
    print(f'{"="*70}')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        cmds = [
            ('A.UnicodeEncodeError完整堆栈', 'grep -A5 "UnicodeEncodeError" /var/log/subscription_service.log 2>&1 | head -40'),
            ('B.UnicodeEncodeError频率', 'grep -c "UnicodeEncodeError" /var/log/subscription_service.log 2>&1'),
            ('C.UnicodeEncodeError最近时间', 'grep "UnicodeEncodeError" /var/log/subscription_service.log 2>&1 | tail -5'),
            ('D.REALITY invalid connection频率', 'grep -c "REALITY.*invalid connection" /var/log/singbox.log 2>&1'),
            ('E.REALITY invalid来源IP统计', 'grep "REALITY.*invalid connection" /var/log/singbox.log 2>&1 | grep -oP "from \\K[0-9.]+" | sort | uniq -c | sort -rn | head -15'),
            ('F.CDN所有IP全部TCP死亡?', 'journalctl -u singbox-cdn --since "1 hour ago" --no-pager 2>&1 | grep -c "TCP死亡"'),
            ('G.CDN存活IP数量', 'journalctl -u singbox-cdn --since "1 hour ago" --no-pager 2>&1 | grep -c "TCP存活"'),
            ('H.CDN最近完整运行摘要', 'journalctl -u singbox-cdn --since "1 hour ago" --no-pager 2>&1 | grep -E "步骤|存活|死亡|替换|分配|写入|完成|更新" | tail -30'),
            ('I.CDN数据库表结构', 'cd /root/singbox-eps-node && python3 << \'PYEOF\'\nimport sqlite3\ntry:\n    db = sqlite3.connect("data/singbox.db")\n    c = db.cursor()\n    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type=\'table\'").fetchall()]\n    print("Tables:", tables)\n    for t in tables:\n        count = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]\n        print(f"  {t}: {count} rows")\n        if count > 0 and count < 20:\n            rows = c.execute(f"SELECT * FROM {t}").fetchall()\n            for r in rows:\n                print(f"    {str(r)[:200]}")\n    db.close()\nexcept Exception as e:\n    print(f"Error: {e}")\nPYEOF'),
            ('J.health_check日志最近错误', 'tail -100 /root/singbox-eps-node/logs/health_check.log 2>&1 | grep -iE "error|fail|warn|异常" | tail -15'),
            ('K.singbox-sub /api/cdn-status测试', 'curl -sk https://localhost:2087/api/cdn-status 2>&1'),
            ('L.subscription_service日志最近20行', 'tail -20 /var/log/subscription_service.log 2>&1'),
            ('M.JP singbox ERROR分类详细', 'grep "ERROR" /var/log/singbox.log 2>&1 | grep -v "REALITY.*invalid" | tail -20'),
            ('N.SG singbox ERROR分类详细', 'grep "ERROR" /var/log/singbox.log 2>&1 | grep -v "REALITY.*invalid" | tail -20'),
        ]
        for label, cmd in cmds:
            stdin, stdout, stderr = client.exec_command(cmd, timeout=25)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            result = out if out else err
            if not result:
                result = '(无输出)'
            print(f'\n[{label}]')
            print(result[:2000])
    except Exception as e:
        print(f'连接失败: {e}')
    finally:
        client.close()
