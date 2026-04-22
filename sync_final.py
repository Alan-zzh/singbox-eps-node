#!/usr/bin/env python3
"""同步所有文件到日本服务器并最终验证"""
import paramiko
import json
import time

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

sftp = client.open_sftp()

print("="*60)
print("同步所有文件到日本服务器 v1.0.82")
print("="*60)

files = [
    'scripts/config_generator.py',
    'scripts/config.py',
    'scripts/cdn_monitor.py',
    'scripts/subscription_service.py',
    'scripts/cert_manager.py',
    'scripts/logger.py',
    'AI_DEBUG_HISTORY.md',
    'project_snapshot.md',
    'install.sh',
]

for f in files:
    local_path = f'd:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\{f}'
    remote_path = f'/root/singbox-eps-node/{f}'
    try:
        sftp.put(local_path, remote_path)
        print(f"  ✅ {f}")
    except Exception as e:
        print(f"  ❌ {f}: {e}")

sftp.close()

# 重新生成服务端配置
print("\n重新生成服务端配置...")
_, stdout, _ = client.exec_command("cd /root/singbox-eps-node && python3 scripts/config_generator.py 2>&1")
print(stdout.read().decode().strip())

# 重启所有服务
print("\n重启所有服务...")
_, stdout, _ = client.exec_command("systemctl restart singbox singbox-sub singbox-cdn && sleep 3 && systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
status = stdout.read().decode().strip()
print(f"服务状态:\n{status}")

# 最终验证
print("\n" + "="*60)
print("最终验证")
print("="*60)

# 1. 服务端配置
_, stdout, _ = client.exec_command("python3 -c \"import json; c=json.load(open('/root/singbox-eps-node/config.json')); rules=c.get('route',{}).get('rules',[]); ai=[r for r in rules if r.get('outbound')=='ai-residential']; print(f'服务端: {len(rules)}条规则, AI规则含google.com: {\\\"google.com\\\" in ai[0].get(\\\"domain_suffix\\\",[]) if ai else False}')\"")
print(f"\n{stdout.read().decode().strip()}")

# 2. 客户端配置
_, stdout, _ = client.exec_command("curl -k -s https://localhost:2087/singbox/JP | python3 -c \"import sys,json; c=json.load(sys.stdin); rules=c.get('route',{}).get('rules',[]); dns=c.get('dns',{}).get('servers',[]); ai=[r for r in rules if r.get('outbound')=='ai-residential']; x_rule=[r for r in rules if 'x.com' in r.get('domain_suffix',[])]; final=c.get('route',{}).get('final',''); print(f'客户端: {len(rules)}条规则, {len(dns)}个DNS, AI含google.com: {\\\"google.com\\\" in ai[0].get(\\\"domain_suffix\\\",[]) if ai else False}, X/推特outbound: {x_rule[0].get(\\\"outbound\\\") if x_rule else \\\"无\\\"}, final: {final}')\"")
client_result = stdout.read().decode().strip()
print(f"{client_result}")

# 3. 端口监听
print("\n端口监听:")
_, stdout, _ = client.exec_command("ss -tlnp | grep -E '443|2053|2083|2087|8443' | awk '{print $4}' | sort")
print(stdout.read().decode().strip())

# 4. CDN数据
print("\nCDN数据:")
_, stdout, _ = client.exec_command("python3 -c \"import sqlite3,json; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); c=conn.cursor(); c.execute('SELECT protocol,ip,updated_at FROM cdn_ips ORDER BY updated_at DESC LIMIT 5'); rows=c.fetchall(); [print(f'  {r[0]}: {r[1]} ({r[2]})') for r in rows]; conn.close()\" 2>/dev/null || echo '  无CDN数据'")
print(stdout.read().decode().strip())

client.close()
print("\n✅ 全部完成 v1.0.82")
