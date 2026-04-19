#!/usr/bin/env python3
"""
Singbox 配置生成器
Author: Alan
Version: v1.0.3
Date: 2026-04-19
功能：生成完整的 Singbox 配置
"""

import sys
import os
import uuid
import json
import random
import string

# 读取环境变量
env_vars = {}
with open('/root/singbox-manager/.env', 'r') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            env_vars[key] = value

vless_uuid = env_vars.get('VLESS_UUID', str(uuid.uuid4()))
vless_ws_uuid = env_vars.get('VLESS_WS_UUID', str(uuid.uuid4()))
trojan_pass = env_vars.get('TROJAN_PASSWORD', ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16)))
hysteria2_pass = env_vars.get('HYSTERIA2_PASSWORD', ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16)))
reality_private_key = env_vars.get('REALITY_PRIVATE_KEY', '')
server_ip = env_vars.get('SERVER_IP', '')
cf_domain = env_vars.get('CF_DOMAIN', server_ip) or server_ip
socks5_user = env_vars.get('SOCKS5_USER', 'socks5')
socks5_pass = env_vars.get('SOCKS5_PASS', 'socks5pass')

config = {
    "log": {
        "disabled": False,
        "level": "info",
        "output": "/var/log/singbox.log",
        "timestamp": True
    },
    "inbounds": [
        {
            "type": "socks",
            "tag": "socks-in",
            "listen": "0.0.0.0",
            "listen_port": 1080,
            "users": [
                {
                    "username": socks5_user,
                    "password": socks5_pass
                }
            ]
        },
        {
            "type": "vless",
            "tag": "vless-reality",
            "listen": "0.0.0.0",
            "listen_port": 443,
            "users": [{"id": vless_uuid, "flow": "xtls-rprx-vision"}],
            "tls": {
                "enabled": True,
                "server_name": "www.apple.com",
                "reality": {
                    "enabled": True,
                    "handshake": {"server": "www.apple.com", "server_port": 443},
                    "private_key": reality_private_key,
                    "short_id": ["abcd1234"]
                }
            }
        },
        {
            "type": "vless",
            "tag": "vless-ws",
            "listen": "0.0.0.0",
            "listen_port": 8443,
            "users": [{"id": vless_ws_uuid}],
            "transport": {
                "type": "ws",
                "path": "/vless-ws",
                "headers": {"Host": cf_domain or server_ip}
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": "/root/singbox-manager/cert/cert.crt",
                "key_path": "/root/singbox-manager/cert/cert.key",
                "alpn": ["http/1.1"]
            }
        },
        {
            "type": "trojan",
            "tag": "trojan-ws",
            "listen": "0.0.0.0",
            "listen_port": 8444,
            "users": [{"password": trojan_pass}],
            "transport": {
                "type": "ws",
                "path": "/trojan-ws",
                "headers": {"Host": cf_domain or server_ip}
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": "/root/singbox-manager/cert/cert.crt",
                "key_path": "/root/singbox-manager/cert/cert.key",
                "alpn": ["http/1.1"]
            }
        },
        {
            "type": "hysteria2",
            "tag": "hysteria2",
            "listen": "0.0.0.0",
            "listen_port": 4433,
            "users": [{"password": hysteria2_pass}],
            "tls": {
                "enabled": True,
                "server_name": "www.apple.com",
                "certificate_path": "/root/singbox-manager/cert/cert.crt",
                "key_path": "/root/singbox-manager/cert/cert.key",
                "alpn": ["h3"]
            },
            "obfs": {
                "type": "salamander",
                "password": hysteria2_pass[:8]
            }
        }
    ],
    "outbounds": [
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"}
    ],
    "route": {
        "rules": [
            {"geoip": "cn", "outbound": "direct"},
            {"geosite": "cn", "outbound": "direct"},
            {"outbound": "direct"}
        ]
    }
}

with open("/root/singbox-manager/config.json", 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("[OK] Singbox配置已保存")
print(f"  - SOCKS5 用户: {socks5_user}")
print(f"  - SOCKS5 密码: {socks5_pass}")
print(f"  - VLESS UUID: {vless_uuid}")
print(f"  - VLESS WS UUID: {vless_ws_uuid}")
print(f"  - Trojan Password: {trojan_pass}")
print(f"  - Hysteria2 Password: {hysteria2_pass}")
