#!/usr/bin/env python3
"""HK1 最终验证：直接测试 ?client=full 和手机端实际访问。"""
import os, sys, paramiko

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_DIR = '/root/singbox-eps-node'

def load_env():
    env = {}
    with open(os.path.join(BASE_DIR, '.env'), 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env

def run(c, cmd, label=''):
    if label: print(f"\n--- {label} ---")
    _, stdout, stderr = c.exec_command(cmd, timeout=30)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    if out: print(out)
    if err: print("STDERR:", err)
    return out

def main():
    env = load_env()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(env['HK1_SSH_IP'], username=env['HK1_SSH_USER'], password=env['HK1_SSH_PASS'], timeout=15)

    # 1. ?client=full 参数测试（修正 URL）
    out = run(c, 'curl -sk "https://127.0.0.1:2087/sub/HK?client=full" | base64 -d 2>/dev/null | grep -c "://"', '1. ?client=full 节点数')
    print(f"  => {out} 节点 (期望 4)")

    # 2. ?client=shadowrocket 参数测试
    out = run(c, 'curl -sk "https://127.0.0.1:2087/sub/HK?client=shadowrocket" | base64 -d 2>/dev/null | grep -c "://"', '2. ?client=shadowrocket 节点数')
    print(f"  => {out} 节点 (期望 4)")

    # 3. ?client=xray 参数测试（安全降级）
    out = run(c, 'curl -sk "https://127.0.0.1:2087/sub/HK?client=xray" | base64 -d 2>/dev/null | grep -c "://"', '3. ?client=xray 节点数')
    print(f"  => {out} 节点 (期望 2)")

    # 4. Shadowrocket UA + ?client=full 内容
    run(c, 'curl -sk -H "User-Agent: Shadowrocket" "https://127.0.0.1:2087/sub/HK" | base64 -d 2>/dev/null | grep -o "#[^?]*" | head -10', '4. Shadowrocket UA 节点名列表')

    # 5. /clash/HK 实际代理节点数
    run(c, 'curl -sk https://127.0.0.1:2087/clash/HK | grep "^  - name:"', '5. /clash/HK 代理节点列表')

    # 6. /singbox/HK 代理出站数（不含 selector/dns/block 等）
    run(c, '''curl -sk https://127.0.0.1:2087/singbox/HK | python3 -c "
import json,sys
d=json.load(sys.stdin)
proxies = [o['tag'] for o in d['outbounds'] if o['type'] in ('vless','trojan','anytls','tuic')]
print(f'代理节点: {len(proxies)} 个')
for p in proxies: print(f'  - {p}')
"''', '6. /singbox/HK 代理节点列表')

    # 7. singbox 启动时间（确认之前 health_check 修复仍然有效）
    run(c, 'systemctl show singbox -p ActiveEnterTimestamp | tr -d " "', '7. singbox 启动时间')

    # 8. 确认 singbox 没有被重启（对比启动时间）
    before = run(c, 'systemctl show singbox -p ActiveEnterTimestamp | tr -d " "', '')
    run(c, f'cd {REMOTE_DIR} && bash scripts/health_check.sh 2>&1 | tail -3', '8. 执行 health_check.sh 不触发 singbox 重启')
    after = run(c, 'systemctl show singbox -p ActiveEnterTimestamp | tr -d " "', '')
    ok = "✅" if before == after else "❌"
    print(f"\n  {ok} health_check.sh 执行前后 singbox 启动时间{'未变' if before == after else '变化了！'}")

    c.close()
    print("\n=== HK1 最终验证完成 ===")

if __name__ == '__main__':
    main()
