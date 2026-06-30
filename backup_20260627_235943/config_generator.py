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
    from config import BASE_DIR, CERT_DIR, DATA_DIR, load_env_file, DEPLOY_MODE, CDN_MODE_ENABLED, DIRECT_MODE_ENABLED
except ImportError:
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
    CERT_DIR = os.path.join(BASE_DIR, 'cert')
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    load_env_file = None
    _dm = os.getenv('DEPLOY_MODE', 'cdn').lower().strip()
    DEPLOY_MODE = _dm if _dm in ('cdn', 'direct') else 'cdn'
    CDN_MODE_ENABLED = (DEPLOY_MODE == 'cdn')
    DIRECT_MODE_ENABLED = (DEPLOY_MODE == 'direct')

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
# v4.14.0: anyTLS 协议密码（与 Trojan 密码独立，避免一处泄露影响多协议）
anytls_pass = env_vars.get('ANYTLS_PASSWORD', '') or trojan_pass
# v4.14.0: TUIC v5 已下线（UDP 易被封 + QUIC 长流量被 QoS），保留变量仅为兼容旧 .env
tuic_pass = env_vars.get('TUIC_PASSWORD', ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(16)))
tuic_uuid = env_vars.get('TUIC_UUID', str(uuid.uuid4()))
enable_tuic = env_vars.get('ENABLE_TUIC', 'false').lower() == 'true'  # v4.14.0: 默认 false
tuic_port = int(env_vars.get('TUIC_PORT', '0')) or 50444
reality_private_key = env_vars.get('REALITY_PRIVATE_KEY', '')
reality_short_id = env_vars.get('REALITY_SHORT_ID') or secrets.token_hex(8)
# v4.10.20.2 兼容过渡：服务器端 short_id 数组同时保留旧客户端用的 abcd1234
# 待所有用户切到新订阅链接后，下个版本可删除
REALITY_SHORT_ID_LEGACY = 'abcd1234'
server_ip = env_vars.get('SERVER_IP', '')
cf_domain = env_vars.get('CF_DOMAIN', server_ip) or server_ip


def build_sub_domain(domain):
    """v4.13.3: 从主域名生成 sub-* 子域名（gray cloud 直连源站，绕过 CF DDoS L7）
    CDN 入站的 headers.Host / host 必须用 sub-* 子域名，与客户端订阅配置一致，
    否则 sing-box Host 校验失败报 "bad host" 拒绝连接。
    """
    if domain and '.' in domain:
        parts = domain.split('.', 1)
        return f"sub-{parts[0]}.{parts[1]}"
    return domain or server_ip


# CDN 入站用的 sub-* 直连子域名（与 subscription_service.py 的 get_sub_domain() 保持一致）
cdn_sub_domain = build_sub_domain(cf_domain)

# v4.15.0 dual-stack: _ws_host 由 DEPLOY_MODE 决定
# - cdn模式：JP/SG等节点用 cdn_sub_domain (sub-* 灰云)；HK特殊逻辑保留但优先遵循DEPLOY_MODE
# - direct模式：全部用主域名/IP直连，不使用sub-*子域名
_country_code = env_vars.get('COUNTRY_CODE', '').upper()
if DIRECT_MODE_ENABLED:
    _ws_host = cf_domain or server_ip
elif _country_code == 'HK':
    _ws_host = cf_domain or server_ip
else:
    _ws_host = cdn_sub_domain
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

# 解析 WARP_PEER_ENDPOINT "host:port" 为 endpoint schema 用的 address + port
# sing-box 1.11+ WireGuard 从 outbound 迁移到 endpoint，peers 字段从 endpoint(string) 改为 address+port
def parse_warp_peer_address_port(endpoint_str):
    if not endpoint_str:
        return None, None
    s = endpoint_str.rsplit(':', 1)
    if len(s) != 2:
        print(f"[WARN] WARP_PEER_ENDPOINT格式错误（应为host:port），已忽略: {endpoint_str}")
        return None, None
    try:
        return s[0].strip(), int(s[1].strip())
    except ValueError:
        print(f"[WARN] WARP_PEER_ENDPOINT端口非数字，已忽略: {endpoint_str}")
        return None, None

warp_peer_address, warp_peer_port = parse_warp_peer_address_port(warp_peer_endpoint)
if warp_unlock and warp_private_key and not warp_peer_address:
    print("[WARN] WARP_PEER_ENDPOINT解析失败，WARP解锁已禁用")
    warp_unlock = False

ai_socks5_enabled = False

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
ai_socks5_enabled = bool(socks5_pool) and ai_socks5_routing == 'on'

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
        ] + ([{
            # WARP DNS: AI/流媒体域名DNS查询走WARP隧道，避免DNS级地理封锁
            # OpenAI等AI服务使用DNS级地理封锁，如果DNS查询来自被封IP(如香港)，
            # 会返回错误的IP或拦截页面。通过WARP隧道查1.1.1.1可获取正确解析。
            "tag": "dns_warp",
            "type": "udp",
            "server": "1.1.1.1",
            "detour": "warp-wg"
        }] if warp_unlock and warp_private_key else []),
        "rules": ([{
            # AI+流媒体域名的DNS查询走WARP DNS服务器
            "domain_suffix": (AI_DOMAINS['suffix'] + AI_GOOGLE_DOMAINS['suffix'] + STREAM_DOMAINS['suffix']) if not ai_socks5_enabled else STREAM_DOMAINS['suffix'],
            "domain_keyword": (AI_DOMAINS['keyword'] + AI_GOOGLE_DOMAINS['keyword'] + STREAM_DOMAINS['keyword']) if not ai_socks5_enabled else STREAM_DOMAINS['keyword'],
            "server": "dns_warp"
        }] if warp_unlock and warp_private_key else []),
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
        }
    ] + ([
        # v4.15.0: VLESS-WS 和 Trojan-WS 仅在 CDN 模式（DEPLOY_MODE=cdn）下生成
        # 纯直连模式（direct）精简掉WS入站，减少端口暴露面
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
                "headers": {"Host": _ws_host}
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
                "headers": {"Host": _ws_host}
            },
            "tls": {
                "enabled": True,
                "server_name": cf_domain or server_ip,
                "certificate_path": _cert_chain,
                "key_path": _cert_key,
                "alpn": ["h2", "http/1.1"]
            }
        }
    ] if CDN_MODE_ENABLED else []) + [
        # v4.14.0 新增 anyTLS 入站：直连隐蔽协议，缓解 TLS-in-TLS 指纹检测
        # sing-box 1.12+ 原生支持，配置极简（无 path/Host/serviceName）
        # 两套模式都保留（直连模式核心协议之一）
        {
            "type": "anytls",
            "tag": "anytls-in",
            "listen": "0.0.0.0",
            "listen_port": 2096,
            "tcp_fast_open": True,
            "tcp_multi_path": False,
            "users": [{"password": anytls_pass}],
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
    # sing-box 1.11+ WireGuard outbound 已废弃并在 1.13.0 移除
    # 必须使用 endpoints[] 数组，schema 与 outbound 不同：
    # - 字段 address（不是 local_address）
    # - peers[] 用 address + port（不是 server+server_port，也不是 endpoint 字符串）
    "endpoints": ([{
        "type": "wireguard",
        "tag": "warp-wg",
        "address": [warp_client_ipv4] + ([warp_client_ipv6] if warp_client_ipv6 else []),
        "private_key": warp_private_key,
        "mtu": 1280,
        "peers": [
            {
                "address": warp_peer_address,
                "port": warp_peer_port,
                "public_key": warp_peer_public_key,
                **({"reserved": warp_reserved} if warp_reserved else {}),
                "allowed_ips": ["0.0.0.0/0", "::/0"]
            }
        ]
    }] if warp_unlock and warp_private_key else []),
    "outbounds": [
        {"type": "direct", "tag": "direct"},
        {"type": "block", "tag": "block"}
    ] + ([{
        "type": "selector",
        "tag": "unlock-warp",
        "outbounds": ["warp-wg", "direct"],
        "default": "warp-wg"
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
if DIRECT_MODE_ENABLED:
    print(f"  部署模式: 纯直连(direct) - 4协议精简")
    print(f"  入站协议: VLESS-Reality, VLESS-gRPC, Trojan-TCP, anyTLS" + (", SOCKS5" if socks5_user and socks5_pass else ""))
else:
    print(f"  部署模式: CDN混合(cdn) - 6协议全量")
    print(f"  入站协议: VLESS-Reality, VLESS-gRPC, Trojan-TCP, VLESS-WS, Trojan-WS, anyTLS" + (", SOCKS5" if socks5_user and socks5_pass else ""))
