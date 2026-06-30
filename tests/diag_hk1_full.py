#!/usr/bin/env python3
"""HK1 全面诊断：拉取订阅内容、检查端口、证书、协议凭据、防火墙。
用法: python tests/diag_hk1_full.py
"""
import os
import sys
import paramiko
import base64
import urllib.request
import ssl

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HK1_IP = '47.243.72.97'


def load_env():
    env = {}
    with open(os.path.join(BASE_DIR, '.env'), encoding='utf-8') as f:
        for l in f:
            l = l.strip()
            if '=' in l and not l.startswith('#'):
                k, v = l.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def main():
    env = load_env()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HK1_IP, username=env['HK1_SSH_USER'], password=env['HK1_SSH_PASS'],
              timeout=12, allow_agent=False, look_for_keys=False)
    print(f"=== 连接 HK1 {HK1_IP} ===")

    def run(label, cmd):
        print(f"\n--- {label} ---")
        _, o, e = c.exec_command(cmd, timeout=30)
        out = o.read().decode('utf-8', errors='replace')
        err = e.read().decode('utf-8', errors='replace')
        if out:
            print(out.rstrip())
        if err:
            print("ERR:", err.rstrip())
        return out

    # 1. 服务状态
    run('1. 服务状态', 'systemctl is-active singbox singbox-sub')

    # 2. .env 关键字段
    run('2. .env 关键字段', 'grep -E "^CF_DOMAIN=|^COUNTRY_CODE=|^DEPLOY_MODE=|^ENABLE_TUIC=|^ENABLE_ANYTLS=|^TUIC_UUID=|^TUIC_PASSWORD=|^ANYTLS_PASSWORD=|^VLESS_UUID=|^TROJAN_PASSWORD=|^REALITY_PUBLIC_KEY=|^REALITY_SHORT_ID=" /root/singbox-eps-node/.env')

    # 3. config.py 模式判断
    run('3. config.py 模式判断', 'cd /root/singbox-eps-node/scripts && python3 -c "import config; print(\'DEPLOY_MODE=\'+str(config.DEPLOY_MODE)+\' CDN=\'+str(config.CDN_MODE_ENABLED)+\' DIRECT=\'+str(config.DIRECT_MODE_ENABLED)+\' HK_DIRECT=\'+str(config.HK_DIRECT_MODE)+\' ENABLE_TUIC=\'+str(config.ENABLE_TUIC)+\' ENABLE_ANYTLS=\'+str(getattr(config,\'ENABLE_ANYTLS\',\'N/A\')))" 2>&1')

    # 4. config.json 入站协议
    run('4. config.json 入站协议', 'python3 -c "import json; d=json.load(open(\'/root/singbox-eps-node/config.json\')); [print(i.get(\'tag\',\'?\')+\' | type=\'+i.get(\'type\',\'?\')+\' | listen=\'+i.get(\'listen\',\'?\')+\':\'+str(i.get(\'listen_port\',\'?\'))) for i in d.get(\'inbounds\',[])]"')

    # 5. 端口监听
    run('5. 端口监听', 'ss -tlnp | grep -E "sing-box|python" | head -20')

    # 6. 防火墙规则
    run('6. 防火墙规则', 'iptables -L INPUT -n --line-numbers 2>&1 | head -30')

    # 7. 证书有效期
    run('7. 证书有效期', 'openssl x509 -in /root/singbox-eps-node/cert/fullchain.pem -noout -dates -subject 2>&1')

    # 8. 拉取订阅内容（本地回环）
    run('8. /clash/HK 订阅内容', 'curl -sk https://127.0.0.1:2087/clash/HK 2>&1 | head -80')
    run('9. /sub/HK Base64解码', 'curl -sk https://127.0.0.1:2087/sub/HK | base64 -d 2>&1')

    # 10. singbox-sub 日志
    run('10. singbox-sub 日志(近15行)', 'journalctl -u singbox-sub --no-pager -n 15 2>&1 | tail -15')

    # 11. singbox 日志
    run('11. singbox 日志(近15行)', 'journalctl -u singbox --no-pager -n 15 2>&1 | tail -15')

    c.close()
    print("\n=== 诊断完成 ===")


if __name__ == '__main__':
    main()
