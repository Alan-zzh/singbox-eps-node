#!/usr/bin/env python3
"""重启订阅服务并验证"""
import paramiko
import json
import time

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("重启订阅服务并验证配置")
print("="*60)

# 1. 重启服务
print("\nStep 1: 重启所有服务")
_, stdout, _ = client.exec_command("systemctl restart singbox-sub singbox-cdn singbox && sleep 3")
time.sleep(5)

# 2. 检查服务状态
_, stdout, _ = client.exec_command("systemctl is-active singbox-sub && systemctl is-active singbox-cdn && systemctl is-active singbox")
status = stdout.read().decode().strip()
print(f"服务状态:\n{status}")

# 3. 获取客户端配置
print("\nStep 2: 获取客户端配置 (/singbox/JP)")
_, stdout, stderr = client.exec_command("curl -k -s https://localhost:2087/singbox/JP")
out = stdout.read().decode()
err = stderr.read().decode()

if not out:
    print(f"获取失败，尝试 curl...")
    _, stdout, _ = client.exec_command("curl -k -v https://localhost:2087/singbox/JP 2>&1 | head -30")
    print(stdout.read().decode()[:1000])
else:
    try:
        config = json.loads(out)
        
        # DNS 配置
        dns = config.get('dns', {})
        dns_servers = dns.get('servers', [])
        print(f"\n【DNS 配置】{len(dns_servers)} 个服务器")
        for s in dns_servers:
            tag = s.get('tag', '')
            detour = s.get('detour', '')
            print(f"  {tag}: detour={detour}")
        
        # 路由规则
        rules = config.get('route', {}).get('rules', [])
        print(f"\n【路由规则】共 {len(rules)} 条")
        for i, r in enumerate(rules):
            outbound = r.get('outbound', 'N/A')
            domains = r.get('domain_suffix', [])
            keywords = r.get('domain_keyword', [])
            
            if 'x.com' in domains:
                print(f"  规则{i+1}: X/推特排除 → {outbound}")
            elif 'openai.com' in domains:
                print(f"  规则{i+1}: AI规则({len(domains)}个域名) → {outbound}")
                has_google = 'google.com' in domains
                print(f"    含google.com: {has_google} {'❌ 错误!' if has_google else '✅ 正确'}")
            elif domains and len(domains) > 0:
                print(f"  规则{i+1}: {outbound} ({len(domains)}个域名)")
        
        # final 规则
        final = config.get('route', {}).get('final', '')
        print(f"\n【final规则】: {final}")
        
        # 模拟延迟测试
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
        print(f"  匹配: {matched}")
        if 'ai-residential' not in str(matched):
            print(f"  ✅ 正确: 不走 SOCKS5")
        else:
            print(f"  ❌ 错误: 走了 SOCKS5!")
        
        # X/推特路径
        print(f"\n【X/推特路径】")
        for r in rules:
            domains = r.get('domain_suffix', [])
            if 'x.com' in domains:
                outbound = r.get('outbound')
                print(f"  outbound: {outbound}")
                if outbound == 'ePS-Auto':
                    print(f"  ✅ 正确: 走正常代理")
                else:
                    print(f"  ❌ 错误: 应该走 ePS-Auto")
                    
    except Exception as e:
        print(f"解析失败: {e}")
        print(f"输出: {out[:500]}")

client.close()
print("\n✅ 完成")
