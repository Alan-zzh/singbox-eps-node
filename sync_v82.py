#!/usr/bin/env python3
"""同步所有文件到日本服务器"""
import paramiko

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
    ('scripts/config_generator.py', 'scripts/config_generator.py'),
    ('scripts/config.py', 'scripts/config.py'),
    ('scripts/cdn_monitor.py', 'scripts/cdn_monitor.py'),
    ('scripts/subscription_service.py', 'scripts/subscription_service.py'),
    ('AI_DEBUG_HISTORY.md', 'AI_DEBUG_HISTORY.md'),
    ('project_snapshot.md', 'project_snapshot.md'),
]

for local_name, remote_name in files:
    local_path = f'd:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\{local_name}'
    remote_path = f'/root/singbox-eps-node/{remote_name}'
    sftp.put(local_path, remote_path)
    print(f"  {local_name}")

sftp.close()

print("\n重新生成服务端配置...")
_, stdout, stderr = client.exec_command("cd /root/singbox-eps-node && python3 scripts/config_generator.py 2>&1")
out = stdout.read().decode() + stderr.read().decode()
print(out)

print("重启所有服务...")
_, stdout, _ = client.exec_command("systemctl restart singbox singbox-sub singbox-cdn && sleep 3 && systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
print(f"服务状态:\n{stdout.read().decode().strip()}")

print("\n验证配置...")
_, stdout, _ = client.exec_command("python3 -c \"\nimport json\nconfig = json.load(open('/root/singbox-eps-node/config.json'))\nrules = config.get('route', {}).get('rules', [])\nprint(f'路由规则: {len(rules)} 条')\ndns = config.get('dns', {})\nservers = dns.get('servers', [])\nprint(f'DNS服务器: {len(servers)} 个')\nfor r in rules:\n    if r.get('outbound') == 'ai-residential':\n        domains = r.get('domain_suffix', [])\n        has_google = any(d == 'google.com' for d in domains)\n        print(f'AI规则域名: {len(domains)} 个, 含google.com: {has_google}')\n\"")
print(stdout.read().decode().strip())

client.close()
print("\n✅ 同步完成 v1.0.82")
