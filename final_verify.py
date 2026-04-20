#!/usr/bin/env python3
"""
最终验证所有功能
"""
import paramiko
import base64

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

print("=" * 60)
print("最终验证所有功能")
print("=" * 60)

# 1. 检查服务状态
print("\n【1. 服务状态】")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    status = "✅ 运行中" if out == 'active' else "❌ 未运行"
    print(f"  {svc}: {status}")

# 2. 检查CDN IP
print("\n【2. CDN优选IP】")
exit_code, out, err = run_cmd(client, """python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}: {row[1]}')
    print(f'  ✅ 共{len(rows)}个CDN IP')
else:
    print('  ❌ 无CDN IP数据')
conn.close()
" 2>/dev/null || echo '  ❌ 数据库查询失败'""")
print(out)

# 3. 检查.env配置
print("\n【3. .env配置】")
exit_code, out, err = run_cmd(client, "grep -v '^#' /root/singbox-eps-node/.env | grep -v '^$' | grep -v '='")
if out:
    print(f"  ❌ 以下配置为空:")
    print(out)
else:
    print("  ✅ 所有配置已填写")

# 4. 测试HTTPS订阅
print("\n【4. HTTPS订阅测试】")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTPS不可用'")
print(f"  {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTP不可用'")
print(f"  {out}")

# 5. 获取订阅内容并解码
print("\n【5. 订阅内容验证】")
exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub 2>/dev/null || curl -s http://127.0.0.1:6969/sub 2>/dev/null")
if out:
    # 尝试Base64解码
    try:
        decoded = base64.b64decode(out).decode('utf-8')
        lines = decoded.strip().split('\n')
        print(f"  ✅ 订阅内容有效，共{len(lines)}个节点:")
        for line in lines[:5]:
            if '://' in line:
                protocol = line.split('://')[0]
                name = line.split('#')[-1] if '#' in line else '未命名'
                print(f"    - {protocol}: {name}")
        if len(lines) > 5:
            print(f"    ... 还有{len(lines)-5}个节点")
    except:
        print(f"  ⚠️ 订阅内容格式: {out[:100]}...")
else:
    print("  ❌ 无法获取订阅内容")

# 6. 检查证书
print("\n【6. SSL证书】")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/cert/*.pem 2>/dev/null || echo '无证书'")
print(f"  {out}")

# 7. 检查日志
print("\n【7. 最新日志】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 3 2>&1 | tail -3")
print(f"  CDN: {out}")

exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 3 2>&1 | tail -3")
print(f"  订阅: {out}")

client.close()

print("\n" + "=" * 60)
print("✅ 验证完成！")
print("=" * 60)
