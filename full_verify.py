#!/usr/bin/env python3
"""彻底验证日本服务器配置"""
import paramiko
import json

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("彻底验证日本服务器配置 v1.0.82")
print("="*60)

# 1. 读取完整配置
_, stdout, _ = client.exec_command("cat /root/singbox-eps-node/config.json")
config = json.loads(stdout.read().decode())

# 2. 检查 DNS
dns = config.get('dns', {})
dns_servers = dns.get('servers', [])
print(f"\n【DNS 配置】")
print(f"  服务器数量: {len(dns_servers)}")
for s in dns_servers:
    print(f"  {s.get('tag')}: {s.get('address')} (detour: {s.get('detour')})")

# 3. 检查路由规则
rules = config.get('route', {}).get('rules', [])
print(f"\n【路由规则】共 {len(rules)} 条")
for i, r in enumerate(rules):
    outbound = r.get('outbound', 'N/A')
    domains = r.get('domain_suffix', [])
    keywords = r.get('domain_keyword', [])
    print(f"  规则{i+1}: outbound={outbound}")
    if domains:
        print(f"    domain_suffix({len(domains)}): {', '.join(domains[:5])}{'...' if len(domains)>5 else ''}")
    if keywords:
        print(f"    domain_keyword: {', '.join(keywords)}")

# 4. 检查 outbounds
outbounds = config.get('outbounds', [])
print(f"\n【outbounds】")
for ob in outbounds:
    tag = ob.get('tag', 'N/A')
    ob_type = ob.get('type', 'N/A')
    if tag in ['ai-residential', 'AI-SOCKS5', 'ePS-Auto', 'direct']:
        print(f"  {tag}: type={ob_type}")
        if ob.get('outbounds'):
            print(f"    outbounds: {ob['outbounds']}")

# 5. 模拟 v2rayN 延迟测试路径
print(f"\n【模拟 v2rayN 延迟测试 www.google.com/generate_204】")
matched = None
for r in rules:
    domains = r.get('domain_suffix', [])
    keywords = r.get('domain_keyword', [])
    # 检查是否匹配 google.com
    if 'google.com' in domains or 'google' in keywords:
        matched = r.get('outbound')
        break
print(f"  匹配规则: {matched or 'final(默认)'}")
print(f"  预期: 不走 ai-residential (SOCKS5)")

# 6. 检查 X/推特路径
print(f"\n【X/推特路径】")
for r in rules:
    domains = r.get('domain_suffix', [])
    if 'x.com' in domains:
        print(f"  outbound: {r.get('outbound')}")
        print(f"  预期: ePS-Auto (正常代理)")

# 7. 检查 SOCKS5 故障转移
print(f"\n【SOCKS5 故障转移】")
for ob in outbounds:
    if ob.get('tag') == 'ai-residential':
        outs = ob.get('outbounds', [])
        print(f"  outbounds: {outs}")
        print(f"  有 direct: {'direct' in outs}")

# 8. 服务状态
print(f"\n【服务状态】")
_, stdout, _ = client.exec_command("systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
print(stdout.read().decode().strip())

client.close()
print("\n✅ 验证完成")
