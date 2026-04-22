#!/usr/bin/env python3
"""通过 SSH 验证客户端配置"""
import paramiko
import json

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("通过 SSH 获取订阅服务配置")
print("="*60)

# 1. 直接调用 Python 函数获取配置
print("\nStep 1: 直接调用 subscription_service.py 的生成函数")
_, stdout, stderr = client.exec_command("""
cd /root/singbox-eps-node
python3 -c "
import sys, json
sys.path.insert(0, 'scripts')
from subscription_service import SubscriptionService
ss = SubscriptionService()
config = ss.generate_singbox_config()
print(json.dumps(config, ensure_ascii=False, indent=2)[:5000])
"
""")
out = stdout.read().decode()
err = stderr.read().decode()
if err:
    print(f"错误: {err[:500]}")
else:
    try:
        # 提取 JSON
        start = out.find('{')
        end = out.rfind('}') + 1
        config = json.loads(out[start:end])
        
        # DNS
        dns = config.get('dns', {})
        dns_servers = dns.get('servers', [])
        print(f"\n【DNS 配置】{len(dns_servers)} 个服务器")
        for s in dns_servers:
            print(f"  {s.get('tag')}: {s.get('address')} (detour: {s.get('detour')})")
        
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
                print(f"    含google.com: {has_google}")
            elif domains and len(domains) < 10:
                print(f"  规则{i+1}: {outbound} ({', '.join(domains[:3])})")
        
        # final
        final = config.get('route', {}).get('final', '')
        print(f"\n【final规则】: {final}")
        
    except Exception as e:
        print(f"解析失败: {e}")
        print(out[:1000])

# 2. 检查订阅服务日志
print("\nStep 2: 检查订阅服务日志")
_, stdout, _ = client.exec_command("journalctl -u singbox-sub -n 30 --no-pager 2>/dev/null | tail -20")
logs = stdout.read().decode().strip()
print(logs or "无日志输出")

client.close()
print("\n✅ 完成")
