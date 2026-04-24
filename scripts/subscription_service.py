#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v1.0.85
Date: 2026-04-23
功能：
  - 提供Base64订阅链接（包含所有节点）
  - 提供完整sing-box JSON配置（含自动路由规则）
  - CDN优选IP自动分配（每个协议独立IP）
  - HTTPS支持（Cloudflare正式证书）

订阅链接格式: 
  - Base64: https://{CF_DOMAIN}:{SUB_PORT}/sub/{国家代码}
  - sing-box JSON: https://{CF_DOMAIN}:{SUB_PORT}/singbox/{国家代码}
  ⚠️ 必须使用域名访问（走CDN），IP访问会导致SSL证书不匹配
  ⚠️ CF_DOMAIN从.env动态读取，禁止硬编码域名

节点命名规则: {国家代码}-{协议}（共5个用户可见节点）
- {COUNTRY_CODE}-VLESS-Reality (直连节点，苹果域名伪装)
- {COUNTRY_CODE}-VLESS-WS (CDN节点，独立优选IP)
- {COUNTRY_CODE}-VLESS-HTTPUpgrade (CDN节点，独立优选IP)
- {COUNTRY_CODE}-Trojan-WS (CDN节点，独立优选IP)
- {COUNTRY_CODE}-Hysteria2 (直连节点，端口跳跃)

⚠️ AI-SOCKS5不是用户节点，是幕后路由出站：
- 仅出现在sing-box JSON的outbounds和route.rules中
- 用户在客户端节点列表中看不到AI-SOCKS5
- AI网站流量自动走SOCKS5，用户无感，无需手动选择
- 禁止将AI-SOCKS5加入Base64订阅链接或selector可选列表
"""

import os
import sys
import base64
import urllib.parse
import urllib.request
import sqlite3
import random
import json
from datetime import datetime
import ssl

# ⚠️ 必须先加载.env，再导入config.py（config.py会读取环境变量）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, CF_DOMAIN, DATA_DIR, CERT_DIR, DB_FILE, SUB_PORT,
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, HYSTERIA2_PORT, SOCKS5_PORT,
        HYSTERIA2_UDP_PORTS, REALITY_SHORT_ID, REALITY_DEST, REALITY_SNI,
        AI_SOCKS5_SERVER, AI_SOCKS5_PORT, AI_SOCKS5_USER, AI_SOCKS5_PASS,
        get_sub_domain, BASE_DIR
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)
    SERVER_IP = os.getenv('SERVER_IP', '')
    CF_DOMAIN = os.getenv('CF_DOMAIN', '')
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    CERT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cert')
    DB_FILE = os.path.join(DATA_DIR, 'singbox.db')
    SUB_PORT = int(os.getenv('SUB_PORT', '2087'))
    VLESS_WS_PORT = int(os.getenv('VLESS_WS_PORT', '8443'))
    VLESS_UPGRADE_PORT = int(os.getenv('VLESS_UPGRADE_PORT', '2053'))
    TROJAN_WS_PORT = int(os.getenv('TROJAN_WS_PORT', '2083'))
    HYSTERIA2_PORT = int(os.getenv('HYSTERIA2_PORT', '443'))
    SOCKS5_PORT = int(os.getenv('SOCKS5_PORT', '1080'))
    HYSTERIA2_UDP_PORTS = list(range(21000, 21201))
    REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
    REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
    REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
    AI_SOCKS5_SERVER = os.getenv('AI_SOCKS5_SERVER', '')
    AI_SOCKS5_PORT = os.getenv('AI_SOCKS5_PORT', '')
    AI_SOCKS5_USER = os.getenv('AI_SOCKS5_USER', '')
    AI_SOCKS5_PASS = os.getenv('AI_SOCKS5_PASS', '')
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    def get_sub_domain():
        """降级：config.py导入失败时，用CF_DOMAIN或SERVER_IP作为订阅地址"""
        return CF_DOMAIN if CF_DOMAIN else SERVER_IP

logger = get_logger('subscription_service')

# ⚠️ 以下变量从环境变量读取，不从config.py导入（config.py不导出这些值）
# SERVER_IP和CF_DOMAIN优先使用config.py的值（已从.env读取+自动检测）
# 如果config.py导入失败，降级使用os.getenv
SERVER_IP = SERVER_IP if SERVER_IP else os.getenv('SERVER_IP', '')
CF_DOMAIN = CF_DOMAIN if CF_DOMAIN else os.getenv('CF_DOMAIN', '')
DB_PATH = DB_FILE if 'DB_FILE' in dir() else os.path.join(DATA_DIR, 'singbox.db')
COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'US')
USE_DOMAIN = bool(CF_DOMAIN and CF_DOMAIN.strip() != '')

# 协议密码和UUID：这些值只在.env中，config.py不导出，必须从环境变量读取
VLESS_UUID = os.getenv('VLESS_UUID', '')
VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', '')
# ⚠️ VLESS_UPGRADE_PORT优先使用config.py的硬编码值（2053，已锁定）
# 如果config.py导入失败，降级使用环境变量
VLESS_UPGRADE_PORT = VLESS_UPGRADE_PORT if 'VLESS_UPGRADE_PORT' in dir() else int(os.getenv('VLESS_UPGRADE_PORT', '2053'))
TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
HYSTERIA2_PASSWORD = os.getenv('HYSTERIA2_PASSWORD', '')
REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
EXTERNAL_SUBS = os.getenv('EXTERNAL_SUBS', '')
SUB_TOKEN = os.getenv('SUB_TOKEN', '')

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cdn_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # 按月流量统计表（每月14号自动归零）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traffic_stats (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()

def update_traffic(bytes_count):
    """更新流量统计（按月统计，每月14号自动归零）
    - 检查月份是否变化，变化则重置
    - 检查今天是否14号且本月未重置过，是则重置
    - 累加字节数
    """
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    today_str = now.strftime('%Y-%m-%d')
    need_reset = False

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 读取当前统计值
        cursor.execute("SELECT key, value FROM traffic_stats")
        rows = cursor.fetchall()
        stats = {row[0]: row[1] for row in rows}

        stored_month = stats.get('current_month', '')
        stored_bytes = int(stats.get('current_bytes', '0'))
        last_reset = stats.get('last_reset', '')

        # 判断是否需要重置：月份变了，或者今天是14号且本月还没重置过
        if stored_month != current_month:
            need_reset = True
        elif now.day == 14 and not last_reset.startswith(current_month):
            need_reset = True

        if need_reset:
            stored_bytes = 0
            cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                           ('current_month', current_month))
            cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                           ('last_reset', today_str))

        # 累加流量
        new_bytes = stored_bytes + bytes_count
        cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                       ('current_bytes', str(new_bytes)))
        conn.commit()
    except Exception as e:
        logger.error(f"流量统计更新失败: {e}")
    finally:
        if conn:
            conn.close()

def get_traffic_stats():
    """获取当月流量统计数据"""
    now = datetime.now()
    current_month = now.strftime('%Y-%m')

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM traffic_stats")
        rows = cursor.fetchall()
        stats = {row[0]: row[1] for row in rows}

        stored_month = stats.get('current_month', '')
        stored_bytes = int(stats.get('current_bytes', '0'))
        last_reset = stats.get('last_reset', '')

        # 如果月份变了但还没被update_traffic触发重置，返回0
        if stored_month != current_month:
            stored_bytes = 0
            last_reset = ''

        return {
            'month': current_month,
            'bytes_used': stored_bytes,
            'mb_used': round(stored_bytes / (1024 * 1024), 2),
            'gb_used': round(stored_bytes / (1024 * 1024 * 1024), 2),
            'reset_day': 14,
            'last_reset': last_reset
        }
    except Exception as e:
        logger.error(f"流量统计读取失败: {e}")
        return {
            'month': current_month,
            'bytes_used': 0,
            'mb_used': 0.0,
            'gb_used': 0.0,
            'reset_day': 14,
            'last_reset': ''
        }
    finally:
        if conn:
            conn.close()

def format_traffic(bytes_count):
    """格式化流量显示：小于1MB显示KB，小于1GB显示MB，大于1GB显示GB"""
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.2f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"

def get_cdn_ip_for_protocol(protocol_key):
    """获取指定协议的CDN优选IP"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (protocol_key,))
        row = cursor.fetchone()
        if row and row[0] and row[0] != SERVER_IP:
            return row[0]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN
    return SERVER_IP

def get_sub_address():
    """获取订阅服务地址（域名或IP）- 使用config.py统一逻辑"""
    return get_sub_domain()

def generate_all_links():
    """生成所有节点链接"""
    links = []

    vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
    vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
    trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')

    use_cdn = (vless_ws_addr != SERVER_IP)
    cdn_suffix = "-CDN" if use_cdn else ""

    # CDN节点的SNI：优先使用域名，没有域名则使用服务器IP
    cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP

    # 1. VLESS-Reality (直连)
    params = {
        'encryption': 'none',
        'flow': 'xtls-rprx-vision',
        'type': 'tcp',
        'security': 'reality',
        'sni': REALITY_SNI,
        'fp': 'chrome',
        'pbk': REALITY_PUBLIC_KEY,
        'sid': REALITY_SHORT_ID,
        'spx': '',
        'dest': REALITY_DEST,
        'headerType': 'none'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_UUID}@{SERVER_IP}:443?{param_str}#{COUNTRY_CODE}-VLESS-Reality")

    # 2. VLESS-WS (CDN)
    params = {
        'encryption': 'none',
        'type': 'ws',
        'security': 'tls',
        'sni': cdn_sni,
        'path': '/vless-ws',
        'host': cdn_sni,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{vless_ws_addr}:{VLESS_WS_PORT}?{param_str}#{COUNTRY_CODE}-VLESS-WS{cdn_suffix}")

    # 3. VLESS-HTTPUpgrade (CDN)
    params = {
        'encryption': 'none',
        'type': 'httpupgrade',
        'security': 'tls',
        'sni': cdn_sni,
        'path': '/vless-upgrade',
        'host': cdn_sni,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{vless_upgrade_addr}:{VLESS_UPGRADE_PORT}?{param_str}#{COUNTRY_CODE}-VLESS-HTTPUpgrade{cdn_suffix}")

    # 4. Trojan-WS (CDN)
    params = {
        'type': 'ws',
        'security': 'tls',
        'sni': cdn_sni,
        'insecure': '1',
        'allowInsecure': '1',
        'path': '/trojan-ws',
        'host': cdn_sni,
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
    links.append(f"trojan://{TROJAN_PASSWORD}@{trojan_ws_addr}:{TROJAN_WS_PORT}?{param_str}#{COUNTRY_CODE}-Trojan-WS{cdn_suffix}")

    # 5. Hysteria2 (直连) - 端口443，iptables端口跳跃21000-21200→443
    # ⚠️ mport范围必须与cert_manager.py中setup_hysteria2_port_hopping()一致
    # ⚠️ obfs=salamander用于规避QUIC检测，obfs-password取HY2密码前8位
    params = {
        'sni': REALITY_SNI,
        'insecure': '1',
        'obfs': 'salamander',
        'obfs-password': HYSTERIA2_PASSWORD[:8],
        'mport': '443,21000-21200'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"hysteria2://{HYSTERIA2_PASSWORD}@{SERVER_IP}:443?{param_str}#{COUNTRY_CODE}-Hysteria2")

    return links

def generate_singbox_config():
    """生成完整sing-box JSON配置（含自动路由规则）"""
    vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
    vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
    trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')

    cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP

    config = {
        "log": {
            "level": "info",
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns_proxy",
                    "address": "tls://8.8.8.8",
                    "detour": "direct"
                    # ⚠️ detour必须是direct，不能是"ePS-Auto"或其他代理出站！
                    # 【Bug #23 DNS代理死循环教训】：
                    # 当detour指向代理出站（如ePS-Auto）时，DNS查询本身要走代理，
                    # 但代理连接又需要先解析代理服务器的域名（如AI-SOCKS5的域名），
                    # 这会导致DNS解析再次触发dns_proxy，形成无限递归，最终singbox崩溃。
                    # 正确做法：所有DNS服务器都走direct直连，让DNS查询从VPS直接发出，
                    # 不经过任何代理链路，避免循环依赖。
                    # 原理：DNS是基础设施，必须100%可靠。直连DNS虽然可能延迟略高，
                    # 但保证了稳定性。代理出站依赖DNS解析，DNS不能反过来依赖代理。
                },
                {
                    "tag": "dns_direct",
                    "address": "h3://dns.alidns.com/dns-query",
                    "detour": "direct"
                    # 国内DNS（阿里DoH），专门用于解析中国大陆网站域名
                    # detour同样必须是direct，理由同上
                    # 使用h3协议（HTTP/3）可绕过国内对传统DoH(853)的干扰
                },
                {
                    "tag": "dns_block",
                    "address": "rcode://success"
                    # 屏蔽DNS：返回success但不返回任何IP，用于屏蔽广告/恶意域名
                    # 原理：当route.rules中某条规则的outbound是"dns_block"时，
                    # 该域名的DNS查询会被此服务器处理，返回空响应，客户端无法连接
                },
                {
                    "tag": "dns_fakeip",
                    "address": "fakeip"
                    # FakeIP模式：返回198.18.0.0/15范围内的假IP，真实连接时singbox自动替换
                    # 优势：减少DNS查询延迟，避免DNS污染
                    # 注意：本项目未启用fakeip作为默认DNS，仅在dns.fakeip.enabled=True时生效
                }
            ],
            "rules": [
                {
                    "outbound": "any",
                    "server": "dns_direct"
                    # 最高优先级：只要流量走了任何出站（无论代理还是直连），DNS都用国内服务器
                    # 这是sing-box的内置规则，确保已分类流量的DNS解析走正确路径
                },
                {
                    "rule_set": "geosite-cn",
                    "server": "dns_direct"
                    # 中国大陆网站 → 用阿里DoH解析，返回真实国内CDN IP
                    # 原理：国内网站在国内有CDN节点，用国内DNS能拿到最优IP
                },
                {
                    "rule_set": "geosite-geolocation-!cn",
                    "server": "dns_proxy"
                    # 非中国大陆网站 → 用Google DNS(tls)解析
                    # 注意：虽然tag叫dns_proxy，但detour是direct，DNS查询本身还是直连
                    # 只是解析结果会被标记为"需要代理"，后续路由规则决定走哪个出站
                }
            ],
            "rule_set": [
                {
                    "tag": "geosite-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs"
                },
                {
                    "tag": "geosite-geolocation-!cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-!cn.srs"
                }
            ],
            "final": "dns_proxy",
            # DNS final规则：未被前面任何DNS规则匹配的域名，统一用dns_proxy解析
            # 即：非中国大陆网站默认用Google DNS，确保全球网站都能正常解析
            "fakeip": {
                "enabled": True,
                "inet4_range": "198.18.0.0/15"
            }
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": 2080
            },
            {
                "type": "tun",
                "tag": "tun-in",
                "inet4_address": "172.19.0.1/30",
                "auto_route": True,
                "strict_route": True,
                "stack": "mixed"
            }
        ],
        "outbounds": [
            # ePS-Auto: 用户可见的节点选择器（只包含5个代理节点+direct）
            # ⚠️ AI-SOCKS5不在此列表中，它是幕后路由出站，用户不应手动选择
            {
                "type": "selector",
                "tag": "ePS-Auto",
                "outbounds": [
                    f"{COUNTRY_CODE}-VLESS-Reality",
                    f"{COUNTRY_CODE}-VLESS-WS",
                    f"{COUNTRY_CODE}-VLESS-HTTPUpgrade",
                    f"{COUNTRY_CODE}-Trojan-WS",
                    f"{COUNTRY_CODE}-Hysteria2",
                    "direct"
                ],
                "default": f"{COUNTRY_CODE}-VLESS-Reality"
            },
        ] + ([{
                # ai-residential: 幕后路由出站，AI网站流量自动走此出站
                # 用户在客户端看不到这个选项，路由规则自动匹配AI域名后走SOCKS5
                # 故障转移：AI-SOCKS5不可用时自动fallback到direct
                "type": "selector",
                "tag": "ai-residential",
                "outbounds": ["AI-SOCKS5", "direct"],
                "default": "AI-SOCKS5"
            }] if AI_SOCKS5_SERVER and AI_SOCKS5_PORT else []) + [
            {
                "type": "direct",
                "tag": "direct"
            },
            {
                "type": "block",
                "tag": "block"
            },
            {
                "type": "dns",
                "tag": "dns-out"
            },
            # VLESS-Reality
            {
                "type": "vless",
                "tag": f"{COUNTRY_CODE}-VLESS-Reality",
                "server": SERVER_IP,
                "server_port": 443,
                "uuid": VLESS_UUID,
                "flow": "xtls-rprx-vision",
                "packet_encoding": "xudp",
                "tls": {
                    "enabled": True,
                    "server_name": REALITY_SNI,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
                    "reality": {
                        "enabled": True,
                        "public_key": REALITY_PUBLIC_KEY,
                        "short_id": REALITY_SHORT_ID
                    }
                }
            },
            # VLESS-WS (CDN)
            {
                "type": "vless",
                "tag": f"{COUNTRY_CODE}-VLESS-WS",
                "server": vless_ws_addr,
                "server_port": VLESS_WS_PORT,
                "uuid": VLESS_WS_UUID,
                "packet_encoding": "xudp",
                "tls": {
                    "enabled": True,
                    "server_name": cdn_sni,
                    "insecure": True,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    }
                },
                "transport": {
                    "type": "ws",
                    "path": "/vless-ws",
                    "headers": {
                        "Host": cdn_sni
                    }
                }
            },
            # VLESS-HTTPUpgrade (CDN)
            {
                "type": "vless",
                "tag": f"{COUNTRY_CODE}-VLESS-HTTPUpgrade",
                "server": vless_upgrade_addr,
                "server_port": VLESS_UPGRADE_PORT,
                "uuid": VLESS_WS_UUID,
                "packet_encoding": "xudp",
                "tls": {
                    "enabled": True,
                    "server_name": cdn_sni,
                    "insecure": True,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    }
                },
                "transport": {
                    "type": "httpupgrade",
                    "path": "/vless-upgrade",
                    "host": cdn_sni
                }
            },
            # Trojan-WS (CDN)
            {
                "type": "trojan",
                "tag": f"{COUNTRY_CODE}-Trojan-WS",
                "server": trojan_ws_addr,
                "server_port": TROJAN_WS_PORT,
                "password": TROJAN_PASSWORD,
                "tls": {
                    "enabled": True,
                    "server_name": cdn_sni,
                    "insecure": True
                },
                "transport": {
                    "type": "ws",
                    "path": "/trojan-ws",
                    "headers": {
                        "Host": cdn_sni
                    }
                }
            },
            # Hysteria2 - 支持端口跳跃，无感切换不掉线
            # hop_ports：客户端在连接时自动在指定端口范围内跳跃
            # 工作原理：客户端初始连443，后续QUIC连接自动切换到21000-21200范围内的端口
            # 服务端iptables将21000-21200全部DNAT到443，所以无论客户端跳到哪个端口都能到达HY2
            # 效果：当某个端口被封锁/干扰时，客户端自动跳到其他端口，无需断线重连
            {
                "type": "hysteria2",
                "tag": f"{COUNTRY_CODE}-Hysteria2",
                "server": SERVER_IP,
                "server_port": 443,
                "hop_ports": "21000-21200",
                "password": HYSTERIA2_PASSWORD,
                "tls": {
                    "enabled": True,
                    "server_name": REALITY_SNI,
                    "insecure": True
                },
                "obfs": {
                    "type": "salamander",
                    "password": HYSTERIA2_PASSWORD[:8]
                },
                "up_mbps": 100,
                "down_mbps": 100
            },
            # AI-SOCKS5 - 从环境变量读取，禁止硬编码凭据
            {
                "type": "socks",
                "tag": "AI-SOCKS5",
                "server": AI_SOCKS5_SERVER,
                "server_port": AI_SOCKS5_PORT,
                "version": "5",
                "username": AI_SOCKS5_USER,
                "password": AI_SOCKS5_PASS
            } if AI_SOCKS5_SERVER and AI_SOCKS5_PORT else None
        ],
        "route": {
            "rules": [
                {
                    "protocol": "dns",
                    "outbound": "dns-out"
                    # 最高优先级：DNS流量直接交给sing-box内部DNS引擎处理
                    # 原理：DNS是UDP 53端口的特殊流量，必须先于所有HTTP/HTTPS流量被匹配
                    # 如果这条规则在后面，DNS查询可能被误发到代理节点，导致解析失败
                },
                {
                    "ip_is_private": True,
                    "outbound": "direct"
                    # 私有IP（192.168.x.x, 10.x.x.x, 172.16-31.x.x等）必须直连
                    # 原理：这些是内网地址，走代理没有意义，且可能导致代理节点连接本地服务失败
                },
                {
                    "rule_set": ["geosite-cn", "geoip-cn"],
                    "outbound": "direct"
                    # 中国大陆网站和IP → 直连，不消耗代理流量
                    # 原理：国内网站在国内访问延迟低，不需要绕行VPS
                    # 注意：geosite-cn（域名匹配）和geoip-cn（IP匹配）是"或"关系，
                    # 只要满足任一条件就走direct，确保国内流量100%直连
                },
                # ⚠️ 排除X/推特/groK（不走AI-SOCKS5，走ePS-Auto正常代理）- 必须放在AI规则之前！
                # 【Bug #25 路由顺序教训】：
                # sing-box路由规则是按数组顺序匹配的，第一条匹配到的规则生效！
                # 如果AI规则在前，x.com/twitter.com/grok.com会先被AI规则匹配（因为它们也是AI相关），
                # 导致走ai-residential → AI-SOCKS5，但用户其实希望这些网站走普通代理（ePS-Auto）
                # 正确做法：排除规则必须放在AI规则之前，确保X/groK先被拦截，走ePS-Auto
                #
                # 【设计意图】：
                # X/推特/groK虽然是AI相关（x.ai是Elon Musk的AI，grok是xAI产品），
                # 但它们的访问频率极高，且不需要住宅IP伪装，走VPS代理完全够用
                # 如果把它们塞进AI-SOCKS5，不仅浪费住宅代理流量，还会增加延迟
                #
                # 【故障转移机制】：
                # 出站标签是ePS-Auto（用户可见的节点选择器），包含5个代理节点+direct
                # 如果当前选择的节点不可用，用户可以手动切换到其他节点或直连
                # 禁止将以下域名移入AI规则
                # 顺序说明：sing-box按顺序匹配，先匹配到的规则生效。如果AI规则在前，X/groK会先被AI规则匹配走SOCKS5
                {
                    "domain_suffix": [
                        "x.com",
                        "twitter.com",
                        "twimg.com",
                        "t.co",
                        "x.ai",
                        "grok.com"
                    ],
                    "domain_keyword": [
                        "twitter",
                        "grok"
                    ],
                    "outbound": "ePS-Auto"
                },
                # ⚠️ AI网站自动走SOCKS5（无感路由，写死的规则，禁止随意修改）
                # 【设计意图】：
                # OpenAI/Anthropic/Google AI等网站对数据中心IP有严格封锁，
                # 必须使用住宅IP（residential IP）才能正常访问。
                # AI-SOCKS5提供住宅代理出口，确保AI网站不会被403/验证码拦截。
                #
                # 【Bug #28 教训】：
                # 之前AI规则包含了google.com/googleapis.com/gstatic.com，
                # 导致v2rayN延迟测试(www.google.com/generate_204)走了SOCKS5，
                # 延迟测到360ms(SOCKS5延迟)而非正常代理延迟。
                # 已移除这3个通用域名，只保留AI专用子域名(gemini.google.com等)。
                #
                # 【故障转移机制 - Bug #26教训】：
                # ai-residential selector的outbounds包含["AI-SOCKS5", "direct"]
                # 当AI-SOCKS5不可用（如住宅代理服务宕机、网络中断）时，
                # sing-box会自动fallback到direct（从VPS直连出去）
                # 虽然直连可能被AI网站封锁，但至少不会断网，用户仍能看到错误页面
                # 而不是无限转圈或连接超时
                #
                # 【为什么selector而不是直接写outbound】：
                # selector类型允许后续手动切换（如通过Clash API），
                # 如果AI-SOCKS5长期故障，管理员可以手动切到direct
                # 如果是urltest或loadbalance类型，则无法手动干预
                #
                # 【Bug #26 故障转移教训】：
                # 之前ai-residential的outbounds只有["AI-SOCKS5"]，没有direct备选
                # 当AI-SOCKS5宕机时，所有AI网站流量全部中断，用户无法访问
                # 修复后加入direct作为第二选项，确保至少不断网
                # 出站标签ai-residential → AI-SOCKS5节点（故障转移：不可用时自动切direct）
                # 触发条件：配置了AI_SOCKS5_SERVER和AI_SOCKS5_PORT环境变量
                # 故障转移：AI-SOCKS5不可用时自动fallback到direct（outbounds已包含direct作为第二选项）
                {
                    "domain_suffix": [
                        "openai.com",
                        "chatgpt.com",
                        "anthropic.com",
                        "claude.ai",
                        "gemini.google.com",
                        "bard.google.com",
                        "ai.google",
                        "aistudio.google.com",
                        "perplexity.ai",
                        "midjourney.com",
                        "stability.ai",
                        "cohere.com",
                        "replicate.com"
                    ],
                    "domain_keyword": [
                        "openai",
                        "anthropic",
                        "claude",
                        "gemini",
                        "perplexity",
                        "aistudio"
                    ],
                    "outbound": "ai-residential"
                }
            ],
            "rule_set": [
                {
                    "tag": "geosite-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs"
                },
                {
                    "tag": "geoip-cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs"
                },
                {
                    "tag": "geosite-geolocation-!cn",
                    "type": "remote",
                    "format": "binary",
                    "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-!cn.srs"
                }
            ],
            "auto_detect_interface": True,
            "final": "ePS-Auto"
            # 【final规则 - 兜底出站】：
            # 未被前面任何路由规则匹配的流量，全部走ePS-Auto
            #
            # 【为什么是ePS-Auto而不是direct】：
            # ePS-Auto是用户可见的节点选择器，包含5个代理节点（VLESS-Reality、VLESS-WS、
            # VLESS-HTTPUpgrade、Trojan-WS、Hysteria2）+ direct
            # 默认值是VLESS-Reality，用户可以手动切换到其他节点或直连
            #
            # 【设计意图】：
            # final规则覆盖的是"未被分类的全球网站"（如github.com、youtube.com等）
            # 这些网站需要走代理才能访问，所以final不能是direct
            # 如果final是direct，用户访问未分类网站时会从VPS直连（VPS在海外，国内用户无法直连）
            # 正确做法：final走ePS-Auto，让用户自己选择用哪个代理节点访问全球网站
            #
            # 【匹配流程总结】：
            # 1. DNS流量 → dns-out（内部处理）
            # 2. 私有IP → direct（直连）
            # 3. 中国大陆网站/IP → direct（直连）
            # 4. X/推特/groK → ePS-Auto（普通代理，排除AI-SOCKS5）
            # 5. AI网站 → ai-residential → AI-SOCKS5（住宅代理，故障时切direct）
            # 6. 其他所有网站 → ePS-Auto（兜底，用户自选节点）
        },
        "experimental": {
            "cache_file": {
                "enabled": True
            },
            "clash_api": {
                "external_controller": "127.0.0.1:9090",
                "external_ui": "dashboard"
            }
        }
    }

    config["outbounds"] = [ob for ob in config["outbounds"] if ob is not None]
    return config

def create_app():
    """创建Flask应用"""
    from flask import Flask, Response, jsonify, request

    app = Flask(__name__)

    @app.route('/')
    def home():
        # 获取当月流量统计
        traffic = get_traffic_stats()
        traffic_display = format_traffic(traffic['bytes_used'])

        html = """
        <html>
        <head>
            <title>Singbox订阅服务</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                h1 {{ color: #333; }}
                .sub-box {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .sub-link {{ font-size: 18px; color: #0066cc; word-break: break-all; }}
                .info {{ color: #666; font-size: 14px; }}
                .traffic-box {{ background: #e8f4fd; padding: 20px; border-radius: 10px; margin: 20px 0; border: 1px solid #b3d9f2; }}
                .traffic-value {{ font-size: 28px; color: #0066cc; font-weight: bold; }}
                .traffic-label {{ color: #666; font-size: 14px; margin-top: 5px; }}
            </style>
        </head>
        <body>
            <h1>Singbox 订阅服务</h1>
            <div class="traffic-box">
                <p><strong>当月流量统计</strong></p>
                <p class="traffic-value">{traffic_display}</p>
                <p class="traffic-label">统计月份：{month} | 每月{reset_day}号自动归零 | 上次重置：{last_reset}</p>
            </div>
            <div class="sub-box">
                <p><strong>Base64订阅链接：</strong></p>
                <p class="sub-link">https://{server}:{port}/sub/{country}</p>
                <p class="info">（包含5个节点：{country}-VLESS-Reality、{country}-VLESS-WS、{country}-VLESS-HTTPUpgrade、{country}-Trojan-WS、{country}-Hysteria2）</p>
            </div>
            <div class="sub-box">
                <p><strong>sing-box JSON配置（含自动路由）：</strong></p>
                <p class="sub-link">https://{server}:{port}/singbox/{country}</p>
                <p class="info">（导入后AI流量自动走SOCKS5，无需手动选择）</p>
            </div>
            <div class="info">
                <p>服务器IP: {server}</p>
                <p>域名: {domain}</p>
                <p>使用HTTPS: 是</p>
            </div>
        </body>
        </html>
        """.format(
            server=CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP,
            port=SUB_PORT,
            country=COUNTRY_CODE,
            domain=CF_DOMAIN if CF_DOMAIN else '未配置',
            traffic_display=traffic_display,
            month=traffic['month'],
            reset_day=traffic['reset_day'],
            last_reset=traffic['last_reset'] if traffic['last_reset'] else '尚未重置'
        )
        return Response(html, mimetype='text/html')

    @app.route(f'/sub/{COUNTRY_CODE}')
    @app.route('/sub')
    def get_subscription():
        """Base64订阅链接（兼容旧客户端）
        ⚠️ 禁止加token认证！订阅链接必须直接访问，不需要任何验证参数。
        历史教训：v1.0.54擅自加了SUB_TOKEN认证导致订阅不可用，已回退。
        铁律13：订阅链接不加token认证，保持原有规则直接访问。
        """
        links = generate_all_links()
        if EXTERNAL_SUBS and EXTERNAL_SUBS.strip():
            for sub_url in EXTERNAL_SUBS.split('|'):
                sub_url = sub_url.strip()
                if sub_url:
                    try:
                        req = urllib.request.Request(sub_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            raw = resp.read().decode('utf-8').strip()
                            try:
                                padded_raw = raw + '=' * (-len(raw) % 4)
                                decoded = base64.b64decode(padded_raw).decode('utf-8')
                                links.extend([line for line in decoded.split('\n') if line.strip()])
                            except Exception:
                                links.append(raw)
                    except Exception as e:
                        logger.warning(f"Failed to fetch external sub {sub_url}: {e}")
        sub_text = '\n'.join(links)
        sub_b64 = base64.b64encode(sub_text.encode('utf-8')).decode('utf-8')
        # 记录本次请求产生的流量
        update_traffic(len(sub_b64.encode('utf-8')))
        return Response(sub_b64, mimetype='text/plain')

    @app.route(f'/singbox/{COUNTRY_CODE}')
    @app.route('/singbox')
    def get_singbox_config():
        """完整sing-box JSON配置（含自动路由规则）
        ⚠️ 禁止加token认证！同/sub路由，直接访问。
        """
        config = generate_singbox_config()
        config_json = json.dumps(config, indent=2, ensure_ascii=False)
        # 记录本次请求产生的流量
        update_traffic(len(config_json.encode('utf-8')))
        return Response(
            config_json,
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=singbox-config.json'}
        )

    @app.route('/api/traffic')
    def traffic_api():
        """流量统计API（不加token认证，铁律13）
        返回当月流量使用情况JSON
        """
        stats = get_traffic_stats()
        return jsonify(stats)

    @app.route('/api/cdn', methods=['GET', 'POST'])
    def cdn_api():
        if request.method == 'POST':
            data = request.get_json()
            protocol = data.get('protocol', '').strip()
            new_ip = data.get('ip', '').strip()
            if not protocol or not new_ip:
                return jsonify({'error': 'protocol and ip required'}), 400
            # IP格式验证
            import re
            IP_REGEX = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
            if not IP_REGEX.match(new_ip):
                return jsonify({'error': 'Invalid IP format'}), 400
            valid_keys = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']
            if protocol not in valid_keys:
                return jsonify({'error': 'Invalid protocol key'}), 400
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (protocol, new_ip))
                conn.commit()
                return jsonify({'message': 'OK', 'protocol': protocol, 'ip': new_ip})
            except Exception as e:
                logger.error(f"CDN API错误: {e}")
                return jsonify({'error': 'Internal server error'}), 500
            finally:
                if conn:
                    conn.close()
        else:
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM cdn_settings")
                rows = cursor.fetchall()
                result = {row[0]: row[1] for row in rows}
                return jsonify(result)
            except Exception as e:
                logger.error(f"CDN API错误: {e}")
                return jsonify({'error': 'Internal server error'}), 500
            finally:
                if conn:
                    conn.close()

    return app

if __name__ == '__main__':
    init_db()

    try:
        from config import verify_port_integrity, save_port_lock
        is_valid, msg = verify_port_integrity()
        if not is_valid:
            logger.warning(f"端口完整性校验失败: {msg}，重新生成锁定文件")
            save_port_lock()
        else:
            logger.info(f"端口完整性校验通过: {msg}")
    except Exception as e:
        logger.warning(f"端口校验异常: {e}")

    sub_domain = get_sub_domain()
    app = create_app()
    logger.info(f"Starting HTTPS subscription service on 0.0.0.0:{SUB_PORT}")
    logger.info(f"Base64订阅: https://{sub_domain}:{SUB_PORT}/sub/{COUNTRY_CODE}")
    logger.info(f"sing-box JSON: https://{sub_domain}:{SUB_PORT}/singbox/{COUNTRY_CODE}")

    # ⚠️ SSL证书路径：优先使用fullchain.pem（Let's Encrypt/Cloudflare正式证书）
    # 如果fullchain.pem不存在，降级使用cert.pem（cert_manager.py自签名证书）
    # cert_manager.py自签名证书文件名：cert.pem + key.pem
    # Cloudflare API证书文件名：cert.pem + key.pem（写入CERT_FILE/KEY_FILE）
    # Let's Encrypt证书文件名：fullchain.pem + key.pem（acme.sh生成）
    cert_chain = os.path.join(CERT_DIR, 'fullchain.pem')
    cert_key = os.path.join(CERT_DIR, 'key.pem')
    if not os.path.exists(cert_chain):
        cert_chain = os.path.join(CERT_DIR, 'cert.pem')
    if not os.path.exists(cert_key):
        cert_key = os.path.join(CERT_DIR, 'key.pem')

    if not os.path.exists(cert_chain) or not os.path.exists(cert_key):
        logger.error(f"SSL证书文件不存在: {cert_chain} 或 {cert_key}")
        logger.error("请先运行 cert_manager.py 生成证书")
        sys.exit(1)

    logger.info(f"SSL证书: {cert_chain}")
    app.run(host='0.0.0.0', port=SUB_PORT, threaded=True,
            ssl_context=(cert_chain, cert_key))
