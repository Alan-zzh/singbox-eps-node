#!/usr/bin/env python3
"""
本地测试脚本：生成 Clash YAML 配置并用 mihomo -t 验证
"""
import os
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ['SERVER_IP'] = '1.2.3.4'
os.environ['CF_DOMAIN'] = 'test.example.com'
os.environ['COUNTRY_CODE'] = 'HK'
os.environ['SUB_PORT'] = '2087'
os.environ['VLESS_UUID'] = '12345678-1234-1234-1234-123456789abc'
os.environ['VLESS_WS_UUID'] = '87654321-4321-4321-4321-cba987654321'
os.environ['TROJAN_PASSWORD'] = 'test-trojan-pass'
os.environ['ANYTLS_PASSWORD'] = 'test-anytls-pass'
os.environ['REALITY_PUBLIC_KEY'] = 'T4EGGt0J2qX5vY9Z8aW3eR7tU1iO0pS2dF4gH6jK8lM'
os.environ['REALITY_SHORT_ID'] = '12345678abcd'
os.environ['VLESS_GRPC_PORT'] = '44259'
os.environ['TROJAN_TCP_PORT'] = '41831'
os.environ['VLESS_WS_PORT'] = '8443'
os.environ['TROJAN_WS_PORT'] = '2083'
os.environ['ANYTLS_PORT'] = '2096'

from subscription_service import generate_clash_config

config = generate_clash_config('full')

output_file = '_test_clash_output.yaml'
with open(output_file, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

print(f"测试配置已生成到: {output_file}")
print(f"proxies 数量: {len(config['proxies'])}")
for i, p in enumerate(config['proxies']):
    print(f"  [{i}] {p['name']:30s} type={p['type']:10s} port={p.get('port', 'MISSING!')}")
print(f"\n现在可以用 mihomo -t -f {output_file} 验证配置")
