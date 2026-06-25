#!/usr/bin/env python3
"""
Singbox 配置生成器
Author: Alan
Version: v4.3.5
Date: 2026-05-01
功能：生成完整的 Singbox 配置
⚠️ 所有路径从config.py的BASE_DIR读取，禁止硬编码
"""

import sys
import os
import uuid
import json
import random
import string
import secrets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import BASE_DIR, CERT_DIR, DATA_DIR, load_env_file
except ImportError:
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
    CERT_DIR = os.path.join(BASE_DIR, 'cert')
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    load_env_file = None

# 读取环境变量
env_vars = {}
env_file = os.path.join(BASE_DIR, '.env')
if load_env_file is not None:
    env_vars = load_env_file(env_file)
elif os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.split(' #', 1)[0].split('\t#', 1)[0].strip()

vless_uuid = env_vars.get('VLESS_UUID', str(uuid.uuid4()))
vless_ws_uuid = env_vars.get('VLESS_WS_UUID', str(uuid.uuid4()))
trojan_pass = env_vars.get('TROJAN_PASSWORD', ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16)))
tuic_pass = env_vars.get('TUIC_PASSWORD', ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16)))
tuic_uuid = env_vars.get('TUIC_UUID', str(uuid.uuid4()))
enable_tuic = env_vars.get('ENABLE_TUIC', 'true').lower() == 'true'
tuic_port = int(env_vars.get('TUIC_PORT', '0')) or 50444
reality_private_key = env_vars.get('REALITY_PRIVATE_KEY', '')
reality_short_id = env_vars.get('REALITY_SHORT_ID') or secrets.token_hex(8)
# v4.10.20.2 兼容过渡：服务器端 short_id 数组同时保留旧客户端用的 abcd1234
# 待所有用户切到新订阅链接后，下个版本可删除
REALITY_SHORT_ID_LEGACY = 'abcd1234'
server_ip = env_vars.get('SERVER_IP', '')
cf_domain = env_vars.get('CF_DOMAIN', server_ip) or server_ip
socks5_user = env_vars.get('SOCKS5_USER', '')
socks5_pass = env_vars.get('SOCKS5_PASSWORD', '')

# 读取协议端口配置（从环境变量或使用默认值）
vless_grpc_port = int(env_vars.get('VLESS_GRPC_PORT', '50051'))
trojan_tcp_port = int(env_vars.get('TROJAN_TCP_PORT', '50443'))

ai_socks5_server = env_vars.get('AI_SOCKS5_SERVER', '')
ai_socks5_port = env_vars.get('AI_SOCKS5_PORT', '')
ai_socks5_user = env_vars.get('AI_SOCKS5_USER', '')
ai_socks5_pass = env_vars.get('AI_SOCKS5_PASS', '')
ai_socks5_pool = env_vars.get('AI_SOCKS5_POOL', '')
ai_socks5_routing = env_vars.get('AI_SOCKS5_ROUTING', 'off').lower()

warp_unlock = env_vars.get('WARP_UNLOCK', 'off').lower() == 'on'
warp_private_key = env_vars.get('WARP_PRIVATE_KEY', '')
warp_peer_public_key = env_vars.get('WARP_PEER_PUBLIC_KEY', 'bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=')
warp_peer_endpoint = env_vars.get('WARP_PEER_ENDPOINT', '162.159.193.10:2408')
warp_client_ipv4 = env_vars.get('WARP_CLIENT_IPV4', '')
warp_client_ipv6 = env_vars.get('WARP_CLIENT_IPV6', '')
warp_reserved_str = env_vars.get('WARP_RESERVED', '')

def parse_warp_reserved(reserved_str):
    if not reserved_str:
        return None
    try:
        parts = [int(x.strip()) for x in reserved_str.split(',')]
        if len(parts) != 3 or not all(0 <= v <= 255 for v in parts):
            print(f"[WARN] WARP_RESERVED格式错误，应为3个0-255整数，已忽略: {reserved_str}")
            return None
        return parts
    except ValueError:
        print(f"[WARN] WARP_RESERVED包含非数字值，已忽略: {reserved_str}")
        return None

warp_reserved = parse_warp_reserved(warp_reserved_str)

if warp_unlock and not warp_private_key:
    print("[WARN] WARP_UNLOCK=on但WARP_PRIVATE_KEY为空，WARP解锁已禁用")
    warp_unlock = False

if warp_unlock and not warp_client_ipv4:
    print("[WARN] WARP_UNLOCK=on但WARP_CLIENT_IPV4为空，WARP解锁已禁用")
    warp_unlock = False

ai_socks5_enabled = bool(socks5_pool and ai_socks5_routing == 'on')

AI_DOMAINS = {
    'suffix': [
        "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
        "oaiusercontent.com", "cdn.oaistatic.com", "ai.com",
        "claudeusercontent.com", "auth0.com",
        "perplexity.ai", "midjourney.com", "stability.ai",
    ],
    'keyword': ["openai", "chatgpt", "anthropic", "claude", "perplexity", "midjourney"]
}

AI_GOOGLE_DOMAINS = {
    'suffix': [
        "gemini.google.com", "bard.google.com", "aistudio.google.com",
        "generativelanguage.googleapis.com", "gemini.googleusercontent.com",
        "makersuite.google.com", "notebooklm.google.com", "geminicode.app",
        "ai.google",
    ],
    'keyword': ["gemini", "aistudio", "notebooklm", "makersuite"]
}

STREAM_DOMAINS = {
    'suffix': [
        "tiktok.com", "tiktokv.com", "tiktokcdn.com", "tiktokcdn-us.com",
        "muscdn.co", "musical.ly", "ibyteimg.com", "ipstatp.com",
        "p16-tiktokcdn.com", "p19-tiktokcdn.com", "p20-tiktokcdn.com",
        "p25-tiktokcdn.com", "p26-tiktokcdn.com", "p55-tiktokcdn.com",
        "p57-tiktokcdn.com", "p58-tiktokcdn.com", "p60-tiktokcdn.com",
        "p77-tiktokcdn.com", "p78-tiktokcdn.com", "p9-tiktokcdn.com",
        "netflix.com", "netflix.net", "nflximg.com", "nflximg.net",
        "nflxvideo.net", "nflxso.net", "nflxext.com",
    ],
    'keyword': ["tiktok", "netflix", "nflx"]
}

def parse_socks5_pool():
    if not ai_socks5_pool:
        if ai_socks5_server and ai_socks5_port:
            try:
                port = int(ai_socks5_port)
            except (ValueError, TypeError):
                print(f"[WARN] AI_SOCKS5_PORT格式错误，已忽略: {ai_socks5_port}")
                return []
            return [{'server': ai_socks5_server, 'port': port, 'user': ai_socks5_user, 'pass': ai_socks5_pass}]
        return []
    result = []
    for item in ai_socks5_pool.split(','):
        item = item.strip()
        if not item:
            continue
        parts = item.split('|')
        if len(parts) >= 4:
            try:
                port = int(parts[1].strip())
                result.append({'server': parts[0].strip(), 'port': port, 'user': parts[2].strip(), 'pass': parts[3].strip()})
            except (ValueError, TypeError):
                print(f"[WARN] SOCKS5代理端口格式错误，已忽略: {parts[1]}")
    return result

socks5_pool = parse_socks5_pool()

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
        subprocess.run([sys.executable, cert_script], capture_output=True, text=True, timeout=120)
        # 重新检测证书路径（cert_manager可能生成fullchain.pem或cert.pem）
        _cert_chain2 = os.path.join(CERT_DIR, 'fullchain.pem')
        if os.path.exists(_cert_chain2):
            _cert_chain = _cert_chain2
        _cert_key2 = os.path.join(CERT_DIR, 'key.pem')
        if os.path.exists(_cert_key2):
            _cert_key = _cert_key2

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
                "type": "tls",
                "server": "8.8.8.8"
            },
            {
                "tag": "dns_direct",
                "type": "udp",
                "server": "223.5.5.5"
            }
        ],
        "strategy": "prefer_ipv4"
    },
    "inbounds": [inbound for inbound in socks5_inbound + [
        {
            "type": "vless",
            "tag": "vless-reality",
            "listen": "0.0.0.0",
            "listen_port": 443,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
            "users": [{"uuid": vless_uuid, "flow": "xtls-rprx-vision"}],
            "tls": {
                "enabled": True,
                "server_name": "www.apple.com",
                "reality": {
                    "enabled": True,
                    "handshake": {"server": "www.apple.com", "server_port": 443},
                    "private_key": reality_private_key,
                    "short_id": list(dict.fromkeys([reality_short_id, REALITY_SHORT_ID_LEGACY]))
                }
            }
        },
        {
            "type": "vless",
            "tag": "vless-ws",
            "listen": "0.0.0.0",
            "listen_port": 8443,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
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
                "alpn": ["h2", "http/1.1"]
            }
        },
        {
            "type": "vless",
            "tag": "vless-upgrade",
            "listen": "0.0.0.0",
            "listen_port": 2053,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
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
                "alpn": ["h2", "http/1.1"]
            }
        },
        {
            "type": "trojan",
            "tag": "trojan-ws",
            "listen": "0.0.0.0",
            "listen_port": 2083,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
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
                "alpn": ["h2", "http/1.1"]
            }
        },
        {
            "type": "tuic",
            "tag": "tuic-in",
            "listen": "0.0.0.0",
            "listen_port": tuic_port,
            "congestion_control": "bbr",
            "users": [{"name": "tuic-user", "uuid": tuic_uuid, "password": tuic_pass}],
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
                "alpn": ["h3"]
            }
        } if enable_tuic else None,
        {
            "type": "vless",
            "tag": "vless-grpc",
            "listen": "0.0.0.0",
            "listen_port": vless_grpc_port,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
            "users": [{"uuid": vless_uuid}],
            "transport": {
                "type": "grpc",
                "service_name": "gun"
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
                "alpn": ["h2", "http/1.1"]
            }
        },
        {
            "type": "trojan",
            "tag": "trojan-tcp",
            "listen": "0.0.0.0",
            "listen_port": trojan_tcp_port,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
            "users": [{"password": trojan_pass}],
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
                "alpn": ["h2", "http/1.1"]
            }
        }
    ] if inbound is not None],
    "outbounds": [
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"}
    ] + ([{
        "type": "selector",
        "tag": "unlock-warp",
        "outbounds": ["warp-wg", "direct"],
        "default": "warp-wg"
    }, {
        "type": "wireguard",
        "tag": "warp-wg",
        "local_address": [warp_client_ipv4] + ([warp_client_ipv6] if warp_client_ipv6 else []),
        "private_key": warp_private_key,
        "peers": [
            {
                "public_key": warp_peer_public_key,
                "endpoint": warp_peer_endpoint,
                **({"reserved": warp_reserved} if warp_reserved else {}),
                "allowed_ips": ["0.0.0.0/0", "::/0"]
            }
        ]
    }] if warp_unlock and warp_private_key else []) + ([{
        # ai-residential selector：AI网站流量自动路由到住宅代理池
        # 【故障转移机制 - Bug #26教训】：
        # outbounds包含["AI-SOCKS5-1", "AI-SOCKS5-2", ..., "direct"]
        # 当某个SOCKS5代理不可用时，sing-box自动尝试下一个代理
        # 如果所有SOCKS5代理均不可用，最终fallback到direct，从VPS直连出去
        # 虽然直连可能被AI网站封锁，但至少不会无限转圈，用户能看到错误页面
        #
        # 【为什么selector而不是urltest】：
        # selector允许管理员通过Clash API手动切换（如长期故障时切到direct）
        # urltest是自动测速切换，无法手动干预
        #
        # 【Bug #26 故障转移教训】：
        # 之前outbounds只有["AI-SOCKS5"]，没有direct备选
        # 住宅代理宕机时所有AI网站流量全部中断，修复后加入direct作为第二选项
        #
        # AI-SOCKS5是幕后路由出站，不是用户可见节点
        # 禁止将AI-SOCKS5加入Base64订阅链接或selector可选列表
        # 用户在客户端节点列表中看不到AI-SOCKS5，AI网站流量自动走此出站
        # 故障转移：所有SOCKS5不可用时自动fallback到direct
        "type": "selector",
        "tag": "ai-residential",
        "outbounds": [f"AI-SOCKS5-{i+1}" for i in range(len(socks5_pool))] + ["direct"],
        "default": "AI-SOCKS5-1"
    }] + [{
        "type": "socks",
        "tag": f"AI-SOCKS5-{i+1}",
        "server": proxy['server'],
        "server_port": int(proxy['port']),
        "version": "5",
        "username": proxy['user'],
        "password": proxy['pass']
    } for i, proxy in enumerate(socks5_pool)] if ai_socks5_enabled else []),
    "route": {
        "rules": [
            # 【路由规则匹配顺序说明】：
            # sing-box按数组顺序从上到下匹配，第一条命中的规则生效
            # 因此规则顺序至关重要，优先级高的必须放在前面
            # [TRAE SOLO CN] v4.10.4 私有地址拒绝：客户端TUN模式可能将本地SOCKS5连接(127.0.0.1:5151)捕获路由到代理隧道，
            # 服务端收到后尝试直连127.0.0.1失败产生大量错误日志，必须最前面拦截
        ] + [{
            "ip_cidr": ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fd00::/8", "::1/128"],
            "outbound": "block"
        }, {
            # ⚠️ 排除X/推特/grok - 全局直连，必须放在所有代理规则之前！
            "domain_suffix": ["x.com", "twitter.com", "twimg.com", "t.co", "x.ai", "grok.com"],
            "domain_keyword": ["twitter", "grok"],
            "outbound": "direct"
        }] + ([{
            "domain_suffix": (AI_DOMAINS['suffix'] + AI_GOOGLE_DOMAINS['suffix'] + STREAM_DOMAINS['suffix']) if not ai_socks5_enabled else STREAM_DOMAINS['suffix'],
            "domain_keyword": (AI_DOMAINS['keyword'] + AI_GOOGLE_DOMAINS['keyword'] + STREAM_DOMAINS['keyword']) if not ai_socks5_enabled else STREAM_DOMAINS['keyword'],
            "outbound": "unlock-warp"
        }] if warp_unlock and warp_private_key else []) + ([{
            # ⚠️ AI网站自动走SOCKS5住宅代理（优先级高于WARP）
            "domain_suffix": AI_DOMAINS['suffix'] + AI_GOOGLE_DOMAINS['suffix'] + [
                "cohere.com", "replicate.com", "kimi.moonshot.cn", "deepseek.com",
                "cerebras.net", "inflection.ai", "mistral.ai", "meta.ai", "openai.org"
            ],
            "domain_keyword": AI_DOMAINS['keyword'] + AI_GOOGLE_DOMAINS['keyword'],
            "outbound": "ai-residential"
        }] if ai_socks5_enabled else []) + [{
            # ⚠️ 非AI的Google/YouTube域名 - 全局直连（放在代理规则之后，AI子域名已被前面规则匹配）
            "domain_suffix": [
                "google.com", "googleapis.com", "gstatic.com", "googleusercontent.com",
                "googlevideo.com", "ggpht.com", "youtube.com", "youtu.be", "ytimg.com",
                "blogger.com", "blogblog.com", "blogspot.com", "ampproject.org",
                "android.com", "chrome.com", "chromium.org", "g.co", "goo.gl"
            ],
            "domain_keyword": ["google", "youtube"],
            "outbound": "direct"
        }],
        # sing-box 1.14+ 会移除旧式 DNS 兼容开关，这里显式指定默认解析器，
        # 避免 REALITY 握手域名等内部域名解析再次依赖 ENABLE_DEPRECATED_* 环境变量。
        "default_domain_resolver": "dns_proxy",
        "final": "direct"
        # final规则 - 兜底出站：未匹配任何规则的流量走direct（VPS直连）
        # 服务端final是direct（VPS在海外，直连即可访问全球网站）
        # 客户端final是ePS-Auto（用户自选代理节点），两者不能混淆
    }
}

with open(os.path.join(BASE_DIR, "config.json"), 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("[OK] Singbox配置已保存")
print(f"  配置文件: {os.path.join(BASE_DIR, 'config.json')}")
print(f"  入站协议: VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS" + (", TUIC v5" if enable_tuic else "") + (", SOCKS5" if socks5_user and socks5_pass else ""))
