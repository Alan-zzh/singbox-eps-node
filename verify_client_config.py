#!/usr/bin/env python3
"""验证订阅服务生成的客户端配置"""
import paramiko
import requests
import json

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

# 通过 HTTP 获取订阅配置
url = f"https://{SERVER_IP}:2087/singbox/us"

print("="*60)
print("获取订阅服务生成的客户端配置")
print("="*60)

try:
    resp = requests.get(url, verify=False, timeout=10)
    config = resp.json()
    
    # 1. 检查 DNS
    dns = config.get('dns', {})
    dns_servers = dns.get('servers', [])
    print(f"\n【DNS 配置】")
    print(f"  服务器数量: {len(dns_servers)}")
    for s in dns_servers:
        tag = s.get('tag', '')
        detour = s.get('detour', '')
        print(f"  {tag}: detour={detour}")
    
    # 2. 检查路由规则
    rules = config.get('route', {}).get('rules', [])
    print(f"\n【路由规则】共 {len(rules)} 条")
    for i, r in enumerate(rules):
        outbound = r.get('outbound', 'N/A')
        domains = r.get('domain_suffix', [])
        keywords = r.get('domain_keyword', [])
        
        # 只显示关键规则
        if domains and len(domains) > 0:
            print(f"  规则{i+1}: outbound={outbound}")
            if 'x.com' in domains:
                print(f"    X/推特排除: {len(domains)} 个域名")
            elif 'openai.com' in domains:
                print(f"    AI规则: {len(domains)} 个域名")
                # 检查 google.com
                has_google = 'google.com' in domains
                print(f"    含 google.com: {has_google}")
            else:
                print(f"    domains({len(domains)}): {', '.join(domains[:3])}{'...' if len(domains)>3 else ''}")
        if keywords and not domains:
            print(f"  规则{i+1}: outbound={outbound}, keywords={keywords}")
    
    # 3. 检查 final
    final = config.get('route', {}).get('final', '')
    print(f"\n【final规则】: {final}")
    
    # 4. 模拟 v2rayN 延迟测试
    print(f"\n【模拟 v2rayN 延迟测试 www.google.com/generate_204】")
    matched = None
    for r in rules:
        domains = r.get('domain_suffix', [])
        keywords = r.get('domain_keyword', [])
        if 'google.com' in domains or 'google' in keywords:
            matched = r.get('outbound')
            break
    if not matched:
        matched = final
    print(f"  匹配规则: {matched}")
    print(f"  ✅ 正确: 不走 ai-residential (SOCKS5)" if 'ai-residential' not in str(matched) else f"  ❌ 错误: 走了 SOCKS5")
    
    # 5. 检查 X/推特
    print(f"\n【X/推特路径】")
    for r in rules:
        domains = r.get('domain_suffix', [])
        if 'x.com' in domains:
            outbound = r.get('outbound')
            print(f"  outbound: {outbound}")
            print(f"  ✅ 正确: 走 ePS-Auto (正常代理)" if outbound == 'ePS-Auto' else f"  ❌ 错误: 应该走 ePS-Auto")
    
except Exception as e:
    print(f"\n❌ 获取失败: {e}")
    # 尝试 SSH 验证
    print("\n尝试通过 SSH 验证...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)
    
    _, stdout, _ = client.exec_command("curl -k -s https://localhost:2087/singbox/us | python3 -c \"import sys,json; config=json.load(sys.stdin); print(json.dumps(config, indent=2, ensure_ascii=False)[:2000])\"")
    print(stdout.read().decode()[:1500])
    client.close()
