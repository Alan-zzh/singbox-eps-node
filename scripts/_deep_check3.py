import paramiko

servers = [
    {'name': 'JP', 'ip': '52.195.179.240', 'user': 'root', 'pass': 'je*pMaN8QNfCMK'},
    {'name': 'SG', 'ip': '13.212.37.11', 'user': 'root', 'pass': 'jbfCMP75@jh.dxclouds.com'},
]

for srv in servers:
    print(f'\n{"="*70}')
    print(f'  {srv["name"]} - CDN TCP死亡确认')
    print(f'{"="*70}')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        cmds = [
            ('CDN存活检测逻辑确认', 'journalctl -u singbox-cdn --since "1 hour ago" --no-pager 2>&1 | grep -E "步骤1|存活检测|TCP.*检测|alive|dead|存活|死亡" | head -20'),
            ('CDN完整最近运行(前50行)', 'journalctl -u singbox-cdn --since "1 hour ago" --no-pager -n 100 2>&1 | head -60'),
            ('CDN当前IP手动TCP测试', 'cd /root/singbox-eps-node && python3 << \'PYEOF\'\nimport sqlite3, socket, json\ntry:\n    db = sqlite3.connect("data/singbox.db")\n    c = db.cursor()\n    c.execute("SELECT value FROM cdn_settings WHERE key=\'cdn_ips_list\'")\n    row = c.fetchone()\n    if row:\n        ips = json.loads(row[0])\n        print(f"IP池共{len(ips)}个IP")\n        for ip_info in ips[:5]:\n            ip = ip_info["ip"]\n            try:\n                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n                s.settimeout(3)\n                result = s.connect_ex((ip, 443))\n                s.close()\n                status = "存活" if result == 0 else f"死亡(code={result})"\n                print(f"  {ip}:443 -> {status}")\n            except Exception as e:\n                print(f"  {ip}:443 -> 异常: {e}")\n    db.close()\nexcept Exception as e:\n    print(f"Error: {e}")\nPYEOF'),
            ('CDN订阅IP实际使用', 'curl -sk https://localhost:2087/sub 2>&1 | python3 -c "import sys,base64; links=base64.b64decode(sys.stdin.read()).decode().split(chr(10)); [print(l[:120]) for l in links if l]" 2>&1'),
            ('UnicodeEncodeError触发路径', 'grep -B2 "UnicodeEncodeError" /var/log/subscription_service.log 2>&1 | grep "GET\\|POST\\|HEAD" | sort | uniq -c | sort -rn | head -10'),
            ('Clash配置请求测试', 'curl -sk "https://localhost:2087/clash/sg" 2>&1 | head -c 500'),
            ('Clash配置请求测试(JP)', 'curl -sk "https://localhost:2087/clash/jp" 2>&1 | head -c 500'),
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
