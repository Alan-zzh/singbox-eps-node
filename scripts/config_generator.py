#!/usr/bin/env python3
"""
Singbox 配置生成器
Author: Alan
Version: v1.0.19
Date: 2026-04-21
功能：生成完整的 Singbox 配置
⚠️ 所有路径从config.py的BASE_DIR读取，禁止硬编码
"""

import sys
import os
import uuid
import json
import random
import string

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import BASE_DIR, CERT_DIR
except ImportError:
    BASE_DIR = '/root/singbox-eps-node'
    CERT_DIR = os.path.join(BASE_DIR, 'cert')

# 读取环境变量
env_vars = {}
env_file = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_file):
    with open(env_file, 'r') as f:
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
reality_short_id = env_vars.get('REALITY_SHORT_ID', 'abcd1234')
server_ip = env_vars.get('SERVER_IP', '')
cf_domain = env_vars.get('CF_DOMAIN', server_ip) or server_ip
socks5_user = env_vars.get('SOCKS5_USER', 'socks5')
socks5_pass = env_vars.get('SOCKS5_PASS', 'socks5pass')

ai_socks5_server = env_vars.get('AI_SOCKS5_SERVER', '')
ai_socks5_port = env_vars.get('AI_SOCKS5_PORT', '')
ai_socks5_user = env_vars.get('AI_SOCKS5_USER', '')
ai_socks5_pass = env_vars.get('AI_SOCKS5_PASS', '')

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
            "users": [{"uuid": vless_uuid, "flow": "xtls-rprx-vision"}],
            "tls": {
                "enabled": True,
                "server_name": "www.apple.com",
                "reality": {
                    "enabled": True,
                    "handshake": {"server": "www.apple.com", "server_port": 443},
                    "private_key": reality_private_key,
                    "short_id": [reality_short_id]
                }
            }
        },
        {
            "type": "vless",
            "tag": "vless-ws",
            "listen": "0.0.0.0",
            "listen_port": 8443,
            "users": [{"uuid": vless_ws_uuid}],
            "transport": {
                "type": "ws",
                "path": "/vless-ws",
                "headers": {"Host": cf_domain or server_ip}
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": os.path.join(CERT_DIR, "cert.pem"),
                "key_path": os.path.join(CERT_DIR, "key.pem"),
                "alpn": ["http/1.1"]
            }
        },
        {
            "type": "vless",
            "tag": "vless-upgrade",
            "listen": "0.0.0.0",
            "listen_port": 2053,
            "users": [{"uuid": vless_ws_uuid}],
            "transport": {
                "type": "httpupgrade",
                "path": "/vless-upgrade",
                "host": cf_domain or server_ip
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": os.path.join(CERT_DIR, "cert.pem"),
                "key_path": os.path.join(CERT_DIR, "key.pem"),
                "alpn": ["http/1.1"]
            }
        },
        {
            "type": "trojan",
            "tag": "trojan-ws",
            "listen": "0.0.0.0",
            "listen_port": 2083,
            "users": [{"password": trojan_pass}],
            "transport": {
                "type": "ws",
                "path": "/trojan-ws",
                "headers": {"Host": cf_domain or server_ip}
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": os.path.join(CERT_DIR, "cert.pem"),
                "key_path": os.path.join(CERT_DIR, "key.pem"),
                "alpn": ["http/1.1"]
            }
        },
        {
            "type": "hysteria2",
            "tag": "hysteria2",
            "listen": "0.0.0.0",
            "listen_port": 443,
            # 端口跳跃：客户端可通过21000-21200范围内的端口连接
            # iptables将21000-21200 DNAT到443，服务端只需监听443
            "users": [{"password": hysteria2_pass}],
            "tls": {
                "enabled": True,
                "server_name": "www.apple.com",
                "certificate_path": os.path.join(CERT_DIR, "cert.pem"),
                "key_path": os.path.join(CERT_DIR, "key.pem"),
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
    ] + ([{
        "type": "socks",
        "tag": "ai-residential",
        "server": ai_socks5_server,
        "server_port": int(ai_socks5_port),
        "version": "5",
        "username": ai_socks5_user,
        "password": ai_socks5_pass
    }] if ai_socks5_server and ai_socks5_port else []),
    "route": {
        "rules": [
            {"geoip": "cn", "outbound": "direct"},
            {"geosite": "cn", "outbound": "direct"},
        ] + ([{
            "domain_suffix": [
                "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
                "gemini.google.com", "bard.google.com", "ai.google",
                "perplexity.ai", "midjourney.com", "stability.ai",
                "cohere.com", "replicate.com"
            ],
            "domain_keyword": ["openai", "anthropic", "claude", "gemini", "perplexity"],
            "outbound": "ai-residential"
        }] if ai_socks5_server and ai_socks5_port else []) + [
            {"outbound": "direct"}
        ]
    }
}

with open(os.path.join(BASE_DIR, "config.json"), 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("[OK] Singbox配置已保存")
print(f"  配置文件: {os.path.join(BASE_DIR, 'config.json')}")
print(f"  入站协议: VLESS-Reality, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, Hysteria2, SOCKS5")
