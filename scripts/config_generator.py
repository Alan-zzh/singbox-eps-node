#!/usr/bin/env python3
"""
Singbox 配置生成器
Author: Alan
Version: v2.0.0
Date: 2026-04-23
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
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
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
socks5_user = env_vars.get('SOCKS5_USER', '')
socks5_pass = env_vars.get('SOCKS5_PASS', '')

ai_socks5_server = env_vars.get('AI_SOCKS5_SERVER', '')
ai_socks5_port = env_vars.get('AI_SOCKS5_PORT', '')
ai_socks5_user = env_vars.get('AI_SOCKS5_USER', '')
ai_socks5_pass = env_vars.get('AI_SOCKS5_PASS', '')

# ⚠️ SSL证书路径：优先fullchain.pem（Let's Encrypt/Cloudflare正式证书），降级cert.pem（自签名）
# cert_manager.py生成cert.pem+key.pem，acme.sh生成fullchain.pem+key.pem
# fullchain.pem包含完整证书链，客户端验证更可靠
_cert_chain = os.path.join(CERT_DIR, 'fullchain.pem')
_cert_key = os.path.join(CERT_DIR, 'key.pem')
if not os.path.exists(_cert_chain):
    _cert_chain = os.path.join(CERT_DIR, 'cert.pem')

# 如果证书文件不存在，自动生成自签名证书（避免singbox因证书缺失启动失败）
if not os.path.exists(_cert_chain) or not os.path.exists(_cert_key):
    import subprocess
    cert_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cert_manager.py')
    if os.path.exists(cert_script):
        subprocess.run([sys.executable, cert_script], capture_output=True, timeout=60)
    if not os.path.exists(_cert_key):
        _cert_key = os.path.join(CERT_DIR, 'key.pem')

# ⚠️ SOCKS5入站：仅当用户名和密码均非空时才启用，避免空凭据导致无认证暴露
socks5_inbound = [{
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
}] if socks5_user and socks5_pass else []

config = {
    "log": {
        "disabled": False,
        "level": "info",
        "output": "/var/log/singbox.log",
        "timestamp": True
    },
    # ⚠️ DNS配置 - 服务端也需要DNS解析能力
    # dns_proxy用8.8.8.8解析国外域名，detour=direct避免DNS查询走代理（Bug #23教训）
    # dns_direct用223.5.5.5解析国内域名（备用）
    "dns": {
        "servers": [
            {
                "tag": "dns_proxy",
                "address": "tls://8.8.8.8",
                "detour": "direct"
            },
            {
                "tag": "dns_direct",
                "address": "223.5.5.5",
                "detour": "direct"
            }
        ]
    },
    "inbounds": socks5_inbound + [
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
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
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
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
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
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
                "alpn": ["http/1.1"]
            }
        },
        {
            "type": "hysteria2",
            "tag": "hysteria2",
            "listen": "0.0.0.0",
            "listen_port": 443,
            "users": [{"password": hysteria2_pass}],
            "tls": {
                "enabled": True,
                "server_name": "www.apple.com",
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
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
        "type": "selector",
        "tag": "ai-residential",
        "outbounds": ["AI-SOCKS5", "direct"],
        "default": "AI-SOCKS5"
    }, {
        "type": "socks",
        "tag": "AI-SOCKS5",
        "server": ai_socks5_server,
        "server_port": int(ai_socks5_port),
        "version": "5",
        "username": ai_socks5_user,
        "password": ai_socks5_pass
    }] if ai_socks5_server and ai_socks5_port else []),
    "route": {
        "rules": [
        ] + ([{
            "domain_suffix": ["x.com", "twitter.com", "twimg.com", "t.co", "x.ai", "grok.com"],
            "domain_keyword": ["twitter", "grok"],
            "outbound": "direct"
        }, {
            "domain_suffix": [
                "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
                "gemini.google.com", "bard.google.com", "ai.google",
                "aistudio.google.com", "perplexity.ai", "midjourney.com",
                "stability.ai", "cohere.com", "replicate.com",
                "kimi.moonshot.cn", "deepseek.com",
                "cerebras.net", "inflection.ai", "mistral.ai",
                "meta.ai", "ai.com", "openai.org", "chat.openai.com",
                "api.openai.com", "platform.openai.com", "playground.openai.com"
            ],
            "domain_keyword": ["openai", "anthropic", "claude", "gemini", "perplexity", "aistudio", "ai", "chatgpt"],
            "domain": ["gemini.google.com"],
            "outbound": "ai-residential"
        }] if ai_socks5_server and ai_socks5_port else []),
        "final": "direct"
    }
}

with open(os.path.join(BASE_DIR, "config.json"), 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("[OK] Singbox配置已保存")
print(f"  配置文件: {os.path.join(BASE_DIR, 'config.json')}")
print(f"  入站协议: VLESS-Reality, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, Hysteria2" + (", SOCKS5" if socks5_user and socks5_pass else ""))
