#!/usr/bin/env python3
"""验证日本服务器 sing-box 配置是否正确"""
import paramiko
import json

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("验证日本服务器 sing-box 配置")
print("="*60)

# 读取完整配置
_, stdout, _ = client.exec_command("cat /root/singbox-eps-node/config.json")
config_json = stdout.read().decode()

try:
    config = json.loads(config_json)
    print("✅ 配置是有效的 JSON")
except:
    print("❌ 配置不是有效 JSON")
    print(config_json[:500])
    client.close()
    exit(1)

# 1. 检查 DNS 配置
dns = config.get('dns', {})
dns_servers = dns.get('servers', [])
print(f"\n【DNS 配置】")
for s in dns_servers:
    tag = s.get('tag', '')
    detour = s.get('detour', '')
    print(f"  {tag}: detour={detour}")
    if 'proxy' in tag and detour != 'direct':
        print("  ⚠️ dns_proxy detour 不是 direct!")

# 2. 检查路由规则
rules = config.get('route', {}).get('rules', [])
print(f"\n【路由规则顺序】（共 {len(rules)} 条）")
for i, rule in enumerate(rules):
    outbound = rule.get('outbound', 'N/A')
    domains = rule.get('domain_suffix', [])
    keywords = rule.get('domain_keyword', [])
    
    if domains or keywords:
        print(f"  规则{i+1}: outbound={outbound}")
        if domains:
            print(f"    domain_suffix: {len(domains)} 个域名")
            # 检查 google.com
            google_domains = [d for d in domains if 'google' in d]
            if google_domains:
                print(f"    ⚠️ 包含 google 域名: {google_domains}")
        if keywords:
            print(f"    domain_keyword: {keywords}")
    
    # 特别检查 ai-residential
    if outbound == 'ai-residential':
        print(f"  ✅ AI 规则在位置 {i+1}")

# 3. 检查 X/推特排除规则
print(f"\n【X/推特/groK 排除规则】")
for i, rule in enumerate(rules):
    domains = rule.get('domain_suffix', [])
    if 'x.com' in domains or 'twitter.com' in domains:
        print(f"  规则{i+1}: {domains}")
        print(f"  outbound: {rule.get('outbound')}")

# 4. 检查 ai-residential 故障转移
outbounds = config.get('outbounds', [])
print(f"\n【ai-residential 故障转移】")
for ob in outbounds:
    if ob.get('tag') == 'ai-residential':
        out_list = ob.get('outbounds', [])
        print(f"  outbounds: {out_list}")
        if 'direct' in out_list:
            print("  ✅ 有 direct 故障转移")
        else:
            print("  ❌ 缺少 direct 故障转移")

# 5. 检查 SOCKS5 配置
print(f"\n【SOCKS5 配置】")
for ob in outbounds:
    if ob.get('tag') == 'AI-SOCKS5':
        transport = ob.get('transport', {})
        print(f"  server: {ob.get('server')}:{ob.get('server_port')}")
        print(f"  transport: {transport.get('type', 'N/A')}")

print("\n" + "="*60)
print("服务状态")
print("="*60)
_, stdout, _ = client.exec_command("systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
services = stdout.read().decode().strip()
print(services)

client.close()
print("\n✅ 验证完成")
