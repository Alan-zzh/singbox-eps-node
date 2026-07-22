#!/usr/bin/env python3
"""
完整订阅验证 + CDN 架构审计
测试每台服务器的所有订阅格式，验证 CDN 路径分离是否正确
"""
import subprocess, json, base64, sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

servers = [
    ('JP', 'sub-jp.290372913.xyz', 'JP', 'jp.290372913.xyz', True),
    ('HK1', 'hk1.290372913.xyz', 'HK1', 'hk1.290372913.xyz', False),
    ('HK2', 'hk2.290372913.xyz', 'HK2', 'hk2.290372913.xyz', False),
]

all_ok = True

for sname, sub_domain, cc, main_domain, is_cdn in servers:
    print(f'\n{"="*60}')
    print(f'  {sname} ({sub_domain}:2087)')
    print(f'{"="*60}')
    
    # 1. /clash/{cc}
    try:
        r = subprocess.run(['curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '10',
                           '-o', 'NUL', '-w', '%{http_code}',
                           f'https://{sub_domain}:2087/clash/{cc}'],
                          capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
        code = r.stdout.strip()
        ok = code == '200'
        print(f'  /clash/{cc}: HTTP {code} {"OK" if ok else "FAIL"}')
        if ok:
            r2 = subprocess.run(['curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '10',
                                f'https://{sub_domain}:2087/clash/{cc}'],
                               capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
            # CDN 节点按协议名识别，避免 proxy-groups 或历史命名差异影响架构检查。
            GROUP_KEYWORDS = ('自动选择', '节点选择', '手动选择', '故障切换', 'auto', 'select', 'fallback')
            name_lines = [l for l in r2.stdout.split('\n') if '- name:' in l]
            # 真实节点 = 含 - name: 且不是 proxy-group
            node_lines = [l for l in name_lines if not any(kw in l for kw in GROUP_KEYWORDS)]
            cdn_nodes = [l for l in node_lines if '-VLESS-WS' in l or '-Trojan-WS' in l]
            print(f'    节点数: {len(node_lines)} (含 {len(name_lines) - len(node_lines)} 个 proxy-group)')
            print(f'    CDN 节点: {len(cdn_nodes)}')
            # Check server fields in CDN nodes
            if cdn_nodes:
                # Find server lines after CDN nodes
                lines = r2.stdout.split('\n')
                for i, line in enumerate(lines):
                    if ('-VLESS-WS' in line or '-Trojan-WS' in line) and '- name:' in line and not any(kw in line for kw in GROUP_KEYWORDS):
                        # Show next few lines for context
                        ctx = lines[i:i+5]
                        for cl in ctx:
                            if 'server:' in cl or 'port:' in cl or 'sni:' in cl:
                                print(f'      {cl.strip()}')
        else:
            all_ok = False
    except Exception as e:
        print(f'  /clash/{cc}: ERROR {e}')
        all_ok = False
    
    # 2. /sub/{cc} (Base64 - V2RAYN format)
    try:
        r = subprocess.run(['curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '10',
                           f'https://{sub_domain}:2087/sub/{cc}'],
                          capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
        raw = r.stdout.strip()
        # Try base64 decode
        try:
            decoded = base64.b64decode(raw + '==').decode('utf-8', errors='replace')
            links = [l for l in decoded.split('\n') if l.strip() and '://' in l]
            print(f'  /sub/{cc}: OK ({len(links)} 协议链接)')
            for link in links[:3]:
                # Extract protocol and basic info
                proto = link.split('://')[0] if '://' in link else '?'
                print(f'    {proto}://...')
            # v4.15.14: 默认/未知 UA 按 full 输出，避免 sing-box 拉取器被误降级成 Xray 兼容节点。
            if len(links) < 4:
                print(f'    WARN: 默认 UA 仅 {len(links)} 个协议 (<4，预期 full)')
                all_ok = False
        except:
            print(f'  /sub/{cc}: RAW ({len(raw)} bytes, not valid base64?)')
            print(f'    First 100: {raw[:100]}')
    except Exception as e:
        print(f'  /sub/{cc}: ERROR {e}')
        all_ok = False
    
    # 3. /singbox/{cc}
    try:
        r = subprocess.run(['curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '10',
                           '-o', 'NUL', '-w', '%{http_code}',
                           f'https://{sub_domain}:2087/singbox/{cc}'],
                          capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
        code = r.stdout.strip()
        ok = code == '200'
        print(f'  /singbox/{cc}: HTTP {code} {"OK" if ok else "FAIL"}')
        if not ok:
            all_ok = False
    except Exception as e:
        print(f'  /singbox/{cc}: ERROR {e}')
        all_ok = False
    
    # 4. CDN WS 路径测试（主域名，CDN 模式专用）
    if is_cdn:
        for label, domain, port, path in [
            ('CDN', main_domain, 443, '/api/v1/stream'),
            ('CDN', main_domain, 443, '/api/v1/data'),
        ]:
            try:
                r = subprocess.run([
                    'curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '8',
                    '-o', 'NUL', '-w', '%{http_code}',
                    '-H', 'Connection: Upgrade',
                    '-H', 'Upgrade: websocket',
                    '-H', 'Sec-WebSocket-Version: 13',
                    '-H', 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==',
                    f'https://{domain}:{port}{path}'
                ], capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
                code = r.stdout.strip()
                ok = code == '101'
                print(f'  {label} {domain}:{port}{path}: HTTP {code} {"✅" if ok else "❌"}')
                if not ok:
                    all_ok = False
            except Exception as e:
                print(f'  {label} {domain}:{port}{path}: ERROR {e}')
                all_ok = False

    # 5. 验证 CDN 节点 server 字段使用主域名
    if is_cdn:
        try:
            r = subprocess.run(['curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '10',
                               f'https://{sub_domain}:2087/clash/{cc}'],
                              capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
            yaml_text = r.stdout
            lines = yaml_text.split('\n')
            in_cdn = False
            cdn_issues = []
            # CDN 节点按协议名识别。
            for i, line in enumerate(lines):
                if '- name:' in line and ('-VLESS-WS' in line or '-Trojan-WS' in line):
                    in_cdn = True
                    cdn_start = i
                if in_cdn and '  server:' in line:
                    val = line.split(':', 1)[1].strip() if ':' in line else ''
                    if main_domain in val:
                        cdn_issues.append(f'server={val} ✅ (main domain)')
                    elif sub_domain in val:
                        cdn_issues.append(f'server={val} ❌ (sub-* direct, should use main domain for CDN)')
                        all_ok = False
                    else:
                        # IP address - check if it reaches
                        cdn_issues.append(f'server={val} (direct IP)')
                if in_cdn and line.strip().startswith('- name:') and i > cdn_start + 1:
                    break
            
            for issue in cdn_issues:
                print(f'  CDN架构: {issue}')
                
        except Exception as e:
            print(f'  CDN架构检查: ERROR {e}')

    # 6. V2RAYN UA 测试
    try:
        r = subprocess.run(['curl.exe', '-s', '-4', '--noproxy', '*', '--max-time', '10',
                           '-A', 'v2rayN/6.0',
                           f'https://{sub_domain}:2087/sub/{cc}'],
                          capture_output=True, text=True, timeout=15, encoding='utf-8', errors='replace')
        raw = r.stdout.strip()
        try:
            decoded = base64.b64decode(raw + '==').decode('utf-8', errors='replace')
            links = [l for l in decoded.split('\n') if l.strip() and '://' in l]
            print(f'  v2rayN UA /sub/{cc}: {len(links)} 协议')
            if len(links) < 4:
                print(f'    WARN: v2rayN 仅 {len(links)} 个协议')
                all_ok = False
        except:
            print(f'  v2rayN UA /sub/{cc}: 解码失败 ({len(raw)} bytes)')
            all_ok = False
    except Exception as e:
        print(f'  v2rayN UA /sub/{cc}: ERROR {e}')
        all_ok = False

print(f'\n{"="*60}')
print(f'  {"ALL OK" if all_ok else "SOME ISSUES FOUND"}')
print(f'{"="*60}')
sys.exit(0 if all_ok else 1)
