#!/usr/bin/env python3
"""
Singbox 配置生成器
Author: Alan
Version: v1.0.82
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
        # ⚠️ ai-residential selector：AI网站流量自动路由到住宅代理
        # 【故障转移机制 - Bug #26教训】：
        # outbounds包含["AI-SOCKS5", "direct"]，AI-SOCKS5为默认首选
        # 当AI-SOCKS5不可用（住宅代理服务宕机、凭据过期、网络中断）时，
        # sing-box自动fallback到direct，从VPS直连出去
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
        # ⚠️ AI-SOCKS5是幕后路由出站，不是用户可见节点
        # 禁止将AI-SOCKS5加入Base64订阅链接或selector可选列表
        # 用户在客户端节点列表中看不到AI-SOCKS5，AI网站流量自动走此出站
        # 故障转移：AI-SOCKS5不可用时自动fallback到direct
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
            # 【路由规则匹配顺序说明】：
            # sing-box按数组顺序从上到下匹配，第一条命中的规则生效
            # 因此规则顺序至关重要，优先级高的必须放在前面
        ] + ([{
            # ⚠️ 排除X/推特/groK（不走AI-SOCKS5，服务器直连）- 必须放在AI规则之前！
            # 【Bug #25 路由顺序教训】：
            # sing-box路由规则是按数组顺序匹配的，第一条匹配到的规则生效！
            # 如果AI规则在前，x.com/twitter.com/grok.com会被AI规则匹配（因为它们也属于AI生态），
            # 导致走ai-residential → AI-SOCKS5，但这些网站不需要住宅IP，走VPS直连即可
            # 正确做法：排除规则必须放在AI规则之前，确保X/groK先被拦截走direct
            #
            # 【设计意图】：
            # X/推特/groK访问频率高，数据中心IP完全能正常访问，
            # 没必要浪费住宅代理流量（住宅代理通常按流量计费）
            # 而且住宅代理延迟更高，影响用户体验
            #
            # 【为什么这里outbound是direct而不是ePS-Auto】：
            # config_generator.py是服务端配置生成器，生成的是VPS上的singbox服务端配置
            # 服务端配置中的direct = 从VPS直连出去（不经过SOCKS5）
            # 这与服务端config.json的定位一致：服务端只负责接收流量并转发
            # 禁止将以下域名移入AI规则
            # 顺序说明：sing-box按顺序匹配，先匹配到的规则生效。如果AI规则在前，X/groK会先被AI规则匹配走SOCKS5
            "domain_suffix": ["x.com", "twitter.com", "twimg.com", "t.co", "x.ai", "grok.com"],
            "domain_keyword": ["twitter", "grok"],
            "outbound": "direct"
        }, {
            # ⚠️ AI网站自动走SOCKS5（无感路由，写死的规则，禁止随意修改）
            # 【设计意图】：
            # OpenAI/Anthropic/Google AI等网站对数据中心IP有严格封锁，
            # 必须使用住宅IP才能正常访问，否则会被403/验证码拦截
            #
            # 【故障转移机制 - Bug #26教训】：
            # ai-residential selector的outbounds包含["AI-SOCKS5", "direct"]
            # 当AI-SOCKS5不可用时自动fallback到direct
            # 虽然直连可能被AI网站封锁，但至少不会断网
            #
            # 【触发条件】：
            # 仅当配置了AI_SOCKS5_SERVER和AI_SOCKS5_PORT环境变量时，
            # 此规则才会被添加到路由规则中（由上面的条件判断控制）
            # 故障转移：AI-SOCKS5不可用时自动fallback到direct（outbounds已包含direct作为第二选项）
            # 出站标签ai-residential → AI-SOCKS5节点（故障转移：不可用时自动切direct）
            # 触发条件：配置了AI_SOCKS5_SERVER和AI_SOCKS5_PORT环境变量
            #
            # 【Bug #28 教训 - 延迟测高根因】：
            # 之前包含了google.com/googleapis.com/gstatic.com这3个通用域名，
            # 导致用户v2rayN延迟测试(www.google.com/generate_204)走了AI-SOCKS5住宅代理，
            # 延迟从正常的63ms(ping)+TLS开销飙升到360ms(SOCKS5住宅代理延迟)。
            # 必须只保留AI专用子域名，不能包含通用google域名！
            "domain_suffix": [
                "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
                "gemini.google.com", "bard.google.com", "ai.google",
                "aistudio.google.com", "perplexity.ai", "midjourney.com",
                "stability.ai", "cohere.com", "replicate.com"
            ],
            "domain_keyword": ["openai", "anthropic", "claude", "gemini", "perplexity", "aistudio"],
            "outbound": "ai-residential"
        }] if ai_socks5_server and ai_socks5_port else []),
        "final": "direct"
        # ⚠️ final规则 - 兜底出站：未匹配任何规则的流量走direct（VPS直连）
        # 服务端final是direct（VPS在海外，直连即可访问全球网站）
        # 客户端final是ePS-Auto（用户自选代理节点），两者不能混淆
    }
}

with open(os.path.join(BASE_DIR, "config.json"), 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("[OK] Singbox配置已保存")
print(f"  配置文件: {os.path.join(BASE_DIR, 'config.json')}")
print(f"  入站协议: VLESS-Reality, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, Hysteria2" + (", SOCKS5" if socks5_user and socks5_pass else ""))
