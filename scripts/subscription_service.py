#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v4.15.0
Date: 2026-06-27
功能：
  - 提供Base64订阅链接（包含所有节点）
  - 提供完整sing-box JSON配置（含自动路由规则）
  - 提供Clash Meta YAML配置（含url-test自动测速）
  - CDN优选IP自动分配（每个协议独立IP）
  - HTTPS支持（Cloudflare正式证书）
  - 按月流量统计（iptables 内核级计数器）
  - DEPLOY_MODE 双模式支持：CDN全量（6节点）/ 直连精简（4节点）

订阅链接格式:
  - Base64: https://{CF_DOMAIN}:{SUB_PORT}/sub/{国家代码}
    - 自动识别客户端 UA：Clash/sing-box/NekoBox/v2rayN/v2rayNG/Shadowrocket → 6 节点
    - 强制控制：?client=full|standard|clash|v2rayn|shadowrocket
  - sing-box JSON: https://{CF_DOMAIN}:{SUB_PORT}/singbox/{国家代码}
  - Clash Meta YAML: https://{CF_DOMAIN}:{SUB_PORT}/clash/{国家代码}
  - 流量查询: https://{CF_DOMAIN}:{SUB_PORT}/info/{国家代码}
  ⚠️ 必须使用域名访问（走CDN），IP访问会导致SSL证书不匹配
  ⚠️ CF_DOMAIN从.env动态读取，禁止硬编码域名

节点命名规则: {国家代码}-{协议}（v4.15.0 起 CDN 模式 6 节点 / 直连模式 4 节点）
- {COUNTRY_CODE}-VLESS-Reality (直连节点，苹果域名伪装)
- {COUNTRY_CODE}-Trojan-TCP (直连节点，TCP+TLS)
- {COUNTRY_CODE}-anyTLS (直连节点，TLS-in-TLS 加密)
- {COUNTRY_CODE}-TUIC-v5 (直连节点，v4.15.0 加回，QUIC 多路复用 + UDP relay)
- {COUNTRY_CODE}-VLESS-WS-CDN (CDN节点，主域名/CF优选IP；CF L7 阻断时自动降级 sub-* 直连)
- {COUNTRY_CODE}-Trojan-WS-CDN (CDN节点，主域名/CF优选IP；CF L7 阻断时自动降级 sub-* 直连)

【v4.15.0 协议栈调整】:
  - 加回 TUIC v5（用户要求 TCP+UDP 双协议支持，TUIC 提供 UDP relay）
  - 删除 VLESS-gRPC（用 TUIC v5 替代，QUIC 多路复用比 gRPC 更高效）
  - v2rayN 6.x+ / v2rayNG 1.x+ 归 full 能力（内置 sing-box 内核，支持 anytls:// 和 tuic://）
  - 节点数：CDN 模式 6 节点 / 直连模式 4 节点（ENABLE_TUIC=false 时各 -1）

【v4.14.0 协议栈精简】:
  - 删除 VLESS-HTTPUpgrade-CDN（故障最多，兼容最窄）
  - 新增 anyTLS（sing-box 1.12+ 原生，配置极简）

【v4.12.1 流量统计修复】:
  - 原版 iptables 只统计 INPUT 方向，导致下载流量被低估 50%
  - 修复：INPUT + OUTPUT 同时计数，反映真实双向流量
  - 修复：增加 UDP 规则（TUIC v5 是 QUIC 协议）

v3.1.3修复：
  1. check_single_socks5: sock_mod→socket（致命Bug修复）
  2. check_single_socks5: finally块确保socket关闭（防泄漏）
  3. test_cdn_ip_connectivity: finally块确保socket关闭（防泄漏）
  4. 移除冗余的sock_mod导入和import socket
"""

import os
import sys
import base64
import urllib.parse
import urllib.request
import sqlite3
import socket
import random
import json
import subprocess
from datetime import datetime
import ssl
import time
import re

# ⚠️ 必须先加载.env，再导入config.py（config.py会读取环境变量）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, CF_DOMAIN, DATA_DIR, CERT_DIR, DB_FILE, SUB_PORT,
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, TUIC_PORT, SOCKS5_PORT,
        TROJAN_TCP_PORT, ANYTLS_PORT, ANYTLS_PASSWORD,
        REALITY_SHORT_ID, REALITY_DEST, REALITY_SNI,
        AI_SOCKS5_SERVER, AI_SOCKS5_PORT, AI_SOCKS5_USER, AI_SOCKS5_PASS,
        AI_SOCKS5_ROUTING, AI_SOCKS5_POOL, COUNTRY_CODE, SUB_TOKEN, get_sub_domain, BASE_DIR,
        CDN_PREFERRED_IPS, CDN_IP_BLACKLIST, CDN_IP_HARD_REJECT, CDN_MODE, CDN_OPTIMIZED_DOMAINS,
        HK_DIRECT_MODE,
        DEPLOY_MODE, CDN_MODE_ENABLED, DIRECT_MODE_ENABLED
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
    ANYTLS_PORT = int(os.getenv('ANYTLS_PORT', '2096'))
    TUIC_PORT = int(os.getenv('TUIC_PORT', '0')) or 50444
    SOCKS5_PORT = int(os.getenv('SOCKS5_PORT', '1080'))
    # v4.15.8: VLESS_GRPC_PORT 已删除（v4.15.0 移除 gRPC 协议）
    TROJAN_TCP_PORT = int(os.getenv('TROJAN_TCP_PORT', '0')) or 50443
    TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
    VLESS_UUID = os.getenv('VLESS_UUID', '')
    REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
    VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', VLESS_UUID)
    CDN_MODE = os.getenv('CDN_MODE', 'ip_optimized')
    CDN_OPTIMIZED_DOMAINS = [d.strip() for d in os.getenv('CDN_OPTIMIZED_DOMAINS', 'icook.hk,icook.tw,cf.090227.xyz').split(',') if d.strip()]
    SOCKS5_USER = os.getenv('SOCKS5_USER', '')
    SOCKS5_PASS = os.getenv('SOCKS5_PASS', '')
    REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID') or __import__('secrets').token_hex(8)
    REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
    REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
    AI_SOCKS5_SERVER = os.getenv('AI_SOCKS5_SERVER', '')
    AI_SOCKS5_PORT = os.getenv('AI_SOCKS5_PORT', '')
    AI_SOCKS5_USER = os.getenv('AI_SOCKS5_USER', '')
    AI_SOCKS5_PASS = os.getenv('AI_SOCKS5_PASS', '')
    AI_SOCKS5_ROUTING = os.getenv('AI_SOCKS5_ROUTING', 'off').lower()
    AI_SOCKS5_POOL = os.getenv('AI_SOCKS5_POOL', '')
    COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'US')
    SUB_TOKEN = os.getenv('SUB_TOKEN', '')
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    CDN_PREFERRED_IPS = []
    CDN_IP_BLACKLIST = []
    CDN_IP_HARD_REJECT = {'latency_ms': 500, 'packet_loss_rate': 0.3, 'download_speed_mbps': 5}
    # v4.15.2: HK1 判断改为基于 CF_DOMAIN 域名前缀（hk1.），禁止用 COUNTRY_CODE
    # HK 与 HK1 地理都在香港，COUNTRY_CODE 无法区分；hk1. 才是直连（香港阿里云）
    _hk_direct_fallback = (os.getenv('CF_DOMAIN', '') or '').strip().lower().startswith('hk1.')
    _env_dm = os.getenv('DEPLOY_MODE', '').lower().strip()
    if _env_dm in ('cdn', 'direct'):
        DEPLOY_MODE = _env_dm
    else:
        DEPLOY_MODE = 'direct' if _hk_direct_fallback else 'cdn'
    CDN_MODE_ENABLED = (DEPLOY_MODE == 'cdn')
    DIRECT_MODE_ENABLED = (DEPLOY_MODE == 'direct')
    HK_DIRECT_MODE = _hk_direct_fallback
    def get_sub_domain():
        """降级：config.py导入失败时，生成 sub-* 子域名绕过 CF DDoS L7"""
        if DIRECT_MODE_ENABLED:
            return SERVER_IP if SERVER_IP else (CF_DOMAIN if CF_DOMAIN and CF_DOMAIN.strip() else '127.0.0.1')
        if CF_DOMAIN and CF_DOMAIN.strip():
            domain = CF_DOMAIN.strip()
            if '.' in domain:
                parts = domain.split('.', 1)
                return f"sub-{parts[0]}.{parts[1]}"
            return domain
        return SERVER_IP

logger = get_logger('subscription_service')

IP_REGEX = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')
# v4.14.0: 删除 vless_upgrade_cdn_ip（HTTPUpgrade 已下线）
CDN_PROTOCOL_KEYS = ['vless_ws_cdn_ip', 'trojan_ws_cdn_ip']

# v4.15.0: HK_DIRECT_MODE 作为 legacy 标志从 config.py 导入
# 实际逻辑以 CDN_MODE_ENABLED / DIRECT_MODE_ENABLED 为准
# v4.15.2: fallback 改为基于 CF_DOMAIN 域名前缀（hk1.），禁止用 COUNTRY_CODE
if 'HK_DIRECT_MODE' not in dir():
    HK_DIRECT_MODE = (CF_DOMAIN or '').strip().lower().startswith('hk1.')

# 标准 6 节点 SOP：Reality / Trojan-TCP / anyTLS / TUIC + WS-CDN / Trojan-WS-CDN
#   full     = 完整 6 节点（含 anyTLS anytls:// + TUIC v5 tuic:// URI）
#              - Clash Meta (mihomo) 系、sing-box 系、NekoBox/NekoRay
#              - v2rayN 6.x+ / v2rayNG 1.x+（内置 sing-box 内核，支持 anytls:// + tuic://）
#              - Shadowrocket（小火箭）iOS 版：原生支持 TUIC v5，anytls:// 安全忽略
#   xray     = Xray 兼容节点（不含 anyTLS/TUIC），只返回标准 vless:// 和 trojan:// 链接
#              - Quantumult/Surge/Loon/Pharos/Potatso 等纯 Xray 内核客户端
#   standard = 同 xray（兼容旧参数）
#   unknown  = 按 xray 处理（安全默认，避免非标准 URI 导致解析失败）
#
# 【v4.15.0 修正】：v2rayN 6.x+ / v2rayNG 1.x+ 默认内置 sing-box 内核，
# 原生支持 tuic:// URI scheme，不应再排除。
# 老版本 v2rayN 用户可通过 ?client=xray 强制降级到 Xray 兼容模式。
#
# 【v4.15.3 修正】：Shadowrocket（小火箭）iOS 版实际支持 TUIC v5（2023年起），
# anytls:// URI 在 Shadowrocket 中不会被解析也不会导致崩溃，安全归类为 full。
# 补充 Clash Meta 系列 UA 关键词（修复 ClashMetaForAndroid 等无连字符 UA 匹配失败）。
CLIENT_CAPABILITIES = {
    # Clash 系（mihomo 内核支持 Reality/gRPC/TUIC，能正确解析 tuic://）
    'clash-meta': 'full',
    'clash meta': 'full',
    'clashmeta': 'full',
    'clash verge': 'full',
    'clash-verge': 'full',
    'clashforwindows': 'full',
    'clash for windows': 'full',
    'clashforandroid': 'full',
    'clash for android': 'full',
    'clashx': 'full',
    'mihomo': 'full',
    'mihomo-party': 'full',
    'stash': 'full',
    # sing-box 原生客户端（支持所有协议，含 anyTLS + TUIC v5）
    'sing-box': 'full',
    'singbox': 'full',
    'nekobox': 'full',
    'nekoray': 'full',
    # v4.15.0: v2rayN 6.x+ / v2rayNG 1.x+ 内置 sing-box 内核，归 full 能力
    # 老版本 v2rayN 可通过 ?client=xray 强制降级
    'v2rayn': 'full',
    'v2rayng': 'full',
    'v2ray ng': 'full',
    # v4.15.3: Shadowrocket（小火箭）iOS 版归 full——支持 TUIC v5，anytls:// 自动忽略
    'shadowrocket': 'full',
    # 纯 Xray 内核客户端不支持 anytls:// 和 tuic:// scheme，必须排除
    'v2box': 'xray',
    'quantumult': 'xray',
    'quantumult x': 'xray',
    'surge': 'xray',
    'surfboard': 'xray',
    'loon': 'xray',
    'pharos': 'xray',
    'potatso': 'xray',
    # 浏览器/curl/wget 默认 xray（安全保守，不输出非标准 URI）
    'mozilla': 'xray',
    'chrome': 'xray',
    'safari': 'xray',
    'curl': 'xray',
    'wget': 'xray',
    'python-requests': 'xray',
}

CLIENT_QUERY_ALIASES = {
    'full': 'full',
    'standard': 'xray',
    'xray': 'xray',
    'clash': 'full',
    'clash-meta': 'full',
    'clashmeta': 'full',
    'clashforandroid': 'full',
    'mihomo': 'full',
    'singbox': 'full',
    'sing-box': 'full',
    'nekobox': 'full',
    'nekoray': 'full',
    # v4.15.0: v2rayN/v2rayNG 内置 sing-box 内核，归 full
    'v2rayn': 'full',
    'v2rayng': 'full',
    'v2box': 'xray',
    # v4.15.3: Shadowrocket 归 full（支持 TUIC v5）
    'shadowrocket': 'full',
    'surge': 'xray',
    'quantumult-x': 'xray',
    'loon': 'xray',
}


def node_name(protocol, cdn=False):
    """[Codex] 统一所有订阅格式中的节点名称。"""
    suffix = '-CDN' if cdn else ''
    return f"{COUNTRY_CODE}-{protocol}{suffix}"


def share_fragment(protocol, cdn=False):
    """分享 URI 的 fragment 必须 URL 编码，避免 v2rayN 将空格等字符判为无效内容。"""
    return urllib.parse.quote(node_name(protocol, cdn=cdn), safe='')


def detect_client_capability(user_agent=''):
    """根据 User-Agent 判断客户端能力
    返回 'full' / 'xray' / 'unknown'
    原则：识别不出按 xray（安全默认），避免非标准 anytls:// URI 导致客户端解析失败
    """
    if not user_agent:
        return 'unknown'
    ua_lower = user_agent.lower()
    for keyword, capability in CLIENT_CAPABILITIES.items():
        if keyword in ua_lower:
            return capability
    return 'unknown'


def resolve_subscription_capability(forced='', user_agent=''):
    """[Codex] 解析 ?client= 强制参数，未知时回退到 UA 自动识别。
    v4.15.0: unknown 默认返回 'xray'（安全保守，不输出非标准 URI）
    """
    forced_key = (forced or '').lower().strip()
    if forced_key in CLIENT_QUERY_ALIASES:
        return CLIENT_QUERY_ALIASES[forced_key]
    detected = detect_client_capability(user_agent)
    return detected if detected != 'unknown' else 'xray'


def is_valid_ipv4(ip):
    if not IP_REGEX.match(ip):
        return False
    parts = ip.split('.')
    return all(0 <= int(part) <= 255 for part in parts)


def load_cdn_settings(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM cdn_settings")
    rows = cursor.fetchall()
    return {row[0]: row[1] for row in rows}


def parse_cdn_ips_list(raw_value):
    return [item['ip'] for item in parse_cdn_pool_details(raw_value) if item.get('ip')]


def parse_cdn_pool_details(raw_value):
    if not raw_value:
        return []
    raw = raw_value.strip()
    if raw.startswith('['):
        try:
            items = json.loads(raw)
            if isinstance(items, list) and items and isinstance(items[0], dict):
                return [item for item in items if isinstance(item, dict) and item.get('ip')]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return [{'ip': ip.strip()} for ip in raw.split(',') if ip.strip()]


def get_cdn_pool_state(conn):
    settings = load_cdn_settings(conn)
    current = {key: settings.get(key, '') for key in CDN_PROTOCOL_KEYS}
    pool_raw = settings.get('cdn_ips_list', '')
    pool = parse_cdn_ips_list(pool_raw)
    return settings, current, pool


def get_ip_performance_snapshot(cursor, ip):
    """[Codex] 读取单个 CDN IP 的性能快照，兼容旧库缺列。"""
    if not ip:
        return {}
    try:
        cursor.execute("PRAGMA table_info(ip_performance)")
        columns = [row[1] for row in cursor.fetchall()]
        if not columns:
            return {}
        cursor.execute("SELECT * FROM ip_performance WHERE ip=?", (ip,))
        row = cursor.fetchone()
        if not row:
            return {}
        perf = dict(zip(columns, row))
        return {
            'score': perf.get('composite_score_v2', 0) or 0,
            'latency_ms': perf.get('avg_latency', 0) or 0,
            'speed_mbps': perf.get('speed_mbps', 0) or 0,
            'success_count': perf.get('success_count', 0) or 0,
            'total_tests': perf.get('total_tests', 0) or 0,
            'fail_count': perf.get('fail_count', 0) or 0,
            'consecutive_fails': perf.get('consecutive_fails', 0) or 0,
            'cross_isp_score': perf.get('user_isp_match', 0) or 0,
            'last_test_time': perf.get('last_test_time'),
            'last_success_time': perf.get('last_success_time'),
            'source': perf.get('source'),
        }
    except Exception:
        return {}


def save_cdn_pool(conn, pool):
    pool_value = ','.join(pool)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES ('cdn_ips_list', ?)", (pool_value,))
    conn.commit()


def add_ips_to_pool(conn, ips):
    _, _, pool = get_cdn_pool_state(conn)
    existing = set(pool)
    added = []
    for ip in ips:
        if ip not in existing:
            pool.append(ip)
            existing.add(ip)
            added.append(ip)
    if added:
        save_cdn_pool(conn, pool)
    return added, pool


def remove_ips_from_pool(conn, ips):
    _, current, pool = get_cdn_pool_state(conn)
    remove_set = set(ips)
    new_pool = [ip for ip in pool if ip not in remove_set]
    removed = [ip for ip in pool if ip in remove_set]
    if removed:
        save_cdn_pool(conn, new_pool)
        cursor = conn.cursor()
        for key, value in current.items():
            if value in remove_set:
                cursor.execute("DELETE FROM cdn_settings WHERE key=?", (key,))
        conn.commit()
    return removed, new_pool

# ============================================================
# SOCKS5 代理池 + 健康检测 + 自动容错切换
# 每次生成订阅时检测所有代理，自动剔除不可用的
# 如果全部不可用，AI路由降级为普通代理（ePS-Auto）
# ============================================================
SOCKS5_POOL = []  # 可用代理列表，每个元素为dict: {server, port, user, pass}

def parse_socks5_pool():
    """解析代理池配置，返回代理列表"""
    pool_str = AI_SOCKS5_POOL
    if not pool_str:
        # 兼容旧配置：单个代理
        if AI_SOCKS5_SERVER and AI_SOCKS5_PORT:
            return [{
                'server': AI_SOCKS5_SERVER,
                'port': int(AI_SOCKS5_PORT),
                'user': AI_SOCKS5_USER or '',
                'pass': AI_SOCKS5_PASS or ''
            }]
        return []
    result = []
    for item in pool_str.split(','):
        item = item.strip()
        if not item:
            continue
        parts = item.split('|')
        if len(parts) >= 4:
            result.append({
                'server': parts[0].strip(),
                'port': int(parts[1].strip()),
                'user': parts[2].strip(),
                'pass': parts[3].strip()
            })
    return result

def check_single_socks5(proxy):
    """检测单个SOCKS5代理是否能正常连接Google
    返回True表示正常，False表示不可用
    """
    s = None
    try:
        proxy_host = proxy['server']
        proxy_port = proxy['port']
        target_host = "www.google.com"
        target_port = 443
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((proxy_host, proxy_port))
        s.send(bytes([0x05, 0x02, 0x00, 0x02]))
        resp = s.recv(2)
        if len(resp) < 2:
            return False
        if resp[1] == 0x02:
            if proxy['user'] and proxy['pass']:
                user_bytes = proxy['user'].encode()
                pass_bytes = proxy['pass'].encode()
                auth_pkt = bytes([0x01, len(user_bytes)]) + user_bytes + bytes([len(pass_bytes)]) + pass_bytes
                s.send(auth_pkt)
                auth_resp = s.recv(2)
                if len(auth_resp) < 2 or auth_resp[1] != 0x00:
                    return False
            else:
                return False
        target_ip = socket.gethostbyname(target_host)
        host_bytes = bytes([int(x) for x in target_ip.split('.')])
        conn_pkt = bytes([0x05, 0x01, 0x00, 0x01]) + host_bytes + target_port.to_bytes(2, 'big')
        s.send(conn_pkt)
        conn_resp = s.recv(10)
        if len(conn_resp) >= 2 and conn_resp[1] == 0x00:
            return True
        return False
    except Exception:
        return False
    finally:
        if s:
            try:
                s.close()
            except Exception:
                pass

def check_socks5_pool():
    """检测代理池中所有代理，返回可用列表"""
    global SOCKS5_POOL
    pool = parse_socks5_pool()
    if not pool:
        SOCKS5_POOL = []
        logger.warning("未配置SOCKS5代理，AI流量将走普通代理")
        return []
    available = []
    for proxy in pool:
        addr = f"{proxy['server']}:{proxy['port']}"
        if check_single_socks5(proxy):
            available.append(proxy)
            logger.info(f"SOCKS5健康检测通过: {addr}")
        else:
            logger.warning(f"SOCKS5健康检测失败: {addr}，已剔除")
    SOCKS5_POOL = available
    if not available:
        logger.warning("所有SOCKS5代理均不可用，AI流量将降级为普通代理")
    return available

# 启动时检测代理池
check_socks5_pool()

# ⚠️ 以下变量从环境变量读取，不从config.py导入（config.py不导出这些值）
# SERVER_IP和CF_DOMAIN优先使用config.py的值（已从.env读取+自动检测）
# 如果config.py导入失败，降级使用os.getenv
SERVER_IP = SERVER_IP if SERVER_IP else os.getenv('SERVER_IP', '')
CF_DOMAIN = CF_DOMAIN if CF_DOMAIN else os.getenv('CF_DOMAIN', '')
DB_PATH = DB_FILE if 'DB_FILE' in dir() else os.path.join(DATA_DIR, 'singbox.db')
USE_DOMAIN = bool(CF_DOMAIN and CF_DOMAIN.strip() != '')

# 协议密码和UUID：这些值只在.env中，config.py不导出，必须从环境变量读取
VLESS_UUID = os.getenv('VLESS_UUID', '')
VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', '')
# ⚠️ VLESS_UPGRADE_PORT优先使用config.py的硬编码值（2053，已锁定）
# 如果config.py导入失败，降级使用环境变量
VLESS_UPGRADE_PORT = VLESS_UPGRADE_PORT if 'VLESS_UPGRADE_PORT' in dir() else int(os.getenv('VLESS_UPGRADE_PORT', '2053'))
TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
# v4.14.0: anyTLS 密码，优先使用 config.py 的 ANYTLS_PASSWORD，降级时从 .env 读取
ANYTLS_PASSWORD_ENV = ANYTLS_PASSWORD if 'ANYTLS_PASSWORD' in dir() and ANYTLS_PASSWORD else os.getenv('ANYTLS_PASSWORD', '')
# v4.14.0: anyTLS 密码为空时降级使用 TROJAN_PASSWORD（保持向后兼容旧 .env）
ANYTLS_PASSWORD_ENV = ANYTLS_PASSWORD_ENV or TROJAN_PASSWORD
TUIC_PASSWORD = os.getenv('TUIC_PASSWORD', '')
TUIC_UUID = os.getenv('TUIC_UUID', '')
ENABLE_TUIC = os.getenv('ENABLE_TUIC', 'true').lower() == 'true'  # v4.15.0: 默认 true（加回 TUIC）
# P1 修复（v4.15.0 审查）：凭据缺失时自动禁用 TUIC，避免订阅端生成空凭据 URI 导致客户端连接失败
# 服务端 config_generator.py 凭据缺失时会随机生成，但订阅端必须使用相同凭据
# 凭据缺失说明 .env 异常或未通过 install.sh 正常部署，应禁用 TUIC 而非生成无效 URI
if ENABLE_TUIC and not (TUIC_UUID and TUIC_PASSWORD):
    ENABLE_TUIC = False
TUIC_PORT_ENV = int(os.getenv('TUIC_PORT', '0')) or TUIC_PORT
REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
EXTERNAL_SUBS = os.getenv('EXTERNAL_SUBS', '')

COUNTRY_NAME_MAP = {
    'SG': '新加坡', 'JP': '日本', 'US': '美国', 'UK': '英国',
    'DE': '德国', 'HK': '香港', 'TW': '台湾', 'KR': '韩国',
    'CA': '加拿大', 'AU': '澳洲', 'NL': '荷兰', 'FR': '法国',
}

def get_country_name():
    return COUNTRY_NAME_MAP.get(COUNTRY_CODE, COUNTRY_CODE)

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
        # [Codex] 按月流量统计表（每月14号更新baseline，不清零iptables）
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

def setup_iptables_traffic_counters():
    """配置iptables流量计数器（sing-box各入站端口）
    机场面板标准做法：
    - 在INPUT/OUTPUT链中添加针对sing-box各入站端口的统计规则
    - iptables计数器是内核级别的，持久化、重启不丢失
    - v4.15.0 端口：443(VLESS-Reality), 8443(VLESS-WS), 2083(Trojan-WS), 2096(anyTLS), TUIC_PORT(TUIC v5)
    - 加上 Trojan-TCP 随机端口（VLESS-gRPC 已删除，TUIC v5 替代）
    - [TRAE SOLO CN] v4.12.1 修复：原版只统计 INPUT，导致用户实际流量被低估50%（OUTPUT 没算）
      修复方案：INPUT + OUTPUT 同时计数，反映真实双向流量
    幂等操作：重复调用不会添加重复规则
    """
    # v4.15.0: 删除 2053(HTTPUpgrade)，新增 2096(anyTLS)，加回 TUIC_PORT(TUIC v5)
    singbox_ports = [443, 8443, 2083, 2096, TROJAN_TCP_PORT, TUIC_PORT_ENV]

    for port in singbox_ports:
        if not port or port == 0:
            continue
        tcp_rules = (
            ('INPUT', 'dpt', f'iptables -I INPUT 1 -p tcp --dport {port} -j ACCEPT'),
            ('OUTPUT', 'spt', f'iptables -I OUTPUT 1 -p tcp --sport {port} -j ACCEPT'),
        )
        for chain, marker, add_cmd in tcp_rules:
            check_cmd = f'iptables -L {chain} -v -n -x | grep -c "tcp {marker}:{port}"'
            ret, out, err = _run_cmd(check_cmd)
            if ret == 0 and int(out.strip()) > 0:
                continue
            _run_cmd(add_cmd)

        # TUIC 是 QUIC（UDP），UDP 也要单独建规则
        if port == TUIC_PORT_ENV and TUIC_PORT_ENV:
            udp_rules = (
                ('INPUT', 'dpt', f'iptables -I INPUT 1 -p udp --dport {port} -j ACCEPT'),
                ('OUTPUT', 'spt', f'iptables -I OUTPUT 1 -p udp --sport {port} -j ACCEPT'),
            )
            for chain, marker, add_cmd in udp_rules:
                check_cmd = f'iptables -L {chain} -v -n -x | grep -c "udp {marker}:{port}"'
                ret, out, err = _run_cmd(check_cmd)
                if ret == 0 and int(out.strip()) > 0:
                    continue
                _run_cmd(add_cmd)

def _run_cmd(cmd):
    """执行shell命令，返回(exit_code, stdout, stderr)"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, '', str(e)

def get_iptables_traffic_bytes():
    """通过iptables获取sing-box各入站端口的总流量（字节）
    原理：iptables -L INPUT/OUTPUT -v -n -x 返回每条规则的packet/byte计数器
    取所有sing-box端口规则的bytes总和（INPUT + OUTPUT 双向）
    [TRAE SOLO CN] v4.12.1 修复：原版只取 INPUT，下载流量被低估50%
    """
    singbox_ports = [443, 8443, 2083, 2096, TROJAN_TCP_PORT, TUIC_PORT_ENV]
    total_bytes = 0

    # 同时统计 INPUT 和 OUTPUT，反映真实双向流量
    for chain in ('INPUT', 'OUTPUT'):
        cmd = f'iptables -L {chain} -v -n -x'
        ret, out, err = _run_cmd(cmd)
        if ret != 0:
            logger.warning(f"iptables命令执行失败: {err}")
            continue

        port_marker = 'dpt' if chain == 'INPUT' else 'spt'
        for line in out.split('\n'):
            if f'{port_marker}:' not in line:
                continue
            for port in singbox_ports:
                if not port or port == 0:
                    continue
                port_prefix = f'dpt:{port}' if chain == 'INPUT' else f'spt:{port}'
                if port_prefix in line:
                    # 行格式: pkts bytes target prot opt in out source destination
                    # 例: 12345 6789012345 ACCEPT tcp -- * * 0.0.0.0/0 0.0.0.0/0 tcp dpt:443/spt:443
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            byte_count = int(parts[1])
                            total_bytes += byte_count
                        except (ValueError, IndexError):
                            pass
                    break

    return total_bytes

def check_and_reset_month():
    """检查月份是否变化，是则重置流量统计（保留iptables计数器不清零）"""
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    today_str = now.strftime('%Y-%m-%d')
    need_reset = False

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM traffic_stats")
        rows = cursor.fetchall()
        stats = {row[0]: row[1] for row in rows}

        stored_month = stats.get('current_month', '')
        last_reset = stats.get('last_reset', '')
        has_baseline = 'iptables_baseline' in stats

        # 首次升级到iptables方案：需要初始化基准值
        if not has_baseline:
            iptables_bytes = get_iptables_traffic_bytes()
            if iptables_bytes >= 0:
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('current_month', current_month))
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('last_reset', today_str))
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('iptables_baseline', str(iptables_bytes)))
                logger.info(f"iptables基准值初始化: {iptables_bytes} bytes")
                # 同时清除旧的current_bytes（旧版本update_traffic写入的订阅文件大小）
                cursor.execute("DELETE FROM traffic_stats WHERE key='current_bytes'")
                conn.commit()
                return  # 初始化完成，不需要重置月份
            else:
                # iptables不可用，创建空基准值
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('current_month', current_month))
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('last_reset', today_str))
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('iptables_baseline', '0'))
                conn.commit()
                return

        # 判断是否需要重置：月份变了，或者今天是14号且本月还没重置过
        if stored_month != current_month:
            need_reset = True
        elif now.day == 14 and not last_reset.startswith(current_month):
            need_reset = True

        if need_reset:
            cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                           ('current_month', current_month))
            cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                           ('last_reset', today_str))
            # 重置月份时，更新iptables计数器基准值
            iptables_bytes = get_iptables_traffic_bytes()
            if iptables_bytes >= 0:
                cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)",
                               ('iptables_baseline', str(iptables_bytes)))
                logger.info(f"月份重置: {current_month}, iptables基准值: {iptables_bytes} bytes")
            conn.commit()
    except Exception as e:
        logger.error(f"流量统计重置检查失败: {e}")
    finally:
        if conn:
            conn.close()

def get_last_reset_date():
    """获取上次重置日期"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM traffic_stats")
        rows = cursor.fetchall()
        stats = {row[0]: row[1] for row in rows}
        return stats.get('last_reset', '')
    except Exception:
        return ''
    finally:
        if conn:
            conn.close()

def get_traffic_stats():
    """获取当月流量统计数据（通过iptables内核级计数器，持久化、重启不丢失）"""
    now = datetime.now()
    current_month = now.strftime('%Y-%m')

    # 先从数据库检查是否需要重置月份
    check_and_reset_month()

    # 从iptables获取sing-box各入站端口的总流量
    iptables_bytes = get_iptables_traffic_bytes()

    # 从数据库读取iptables基准值（上次重置时的计数器值）
    baseline_bytes = 0
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM traffic_stats")
        rows = cursor.fetchall()
        stats = {row[0]: row[1] for row in rows}

        stored_month = stats.get('current_month', '')
        if stored_month == current_month:
            baseline_bytes = int(stats.get('iptables_baseline', '0'))
    except Exception as e:
        logger.error(f"流量统计基准值读取失败: {e}")
    finally:
        if conn:
            conn.close()

    # 当月流量 = iptables当前计数器值 - 基准值
    if iptables_bytes >= 0:
        bytes_used = max(iptables_bytes - baseline_bytes, 0)
    else:
        # iptables不可用时，降级使用数据库缓存
        bytes_used = 0

    return {
        'month': current_month,
        'bytes_used': bytes_used,
        'mb_used': round(bytes_used / (1024 * 1024), 2),
        'gb_used': round(bytes_used / (1024 * 1024 * 1024), 2),
        'reset_day': 14,
        'last_reset': get_last_reset_date()
    }

def format_traffic(bytes_count):
    """格式化流量显示：小于1MB显示KB，小于1GB显示MB，大于1GB显示GB"""
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.2f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"

# CDN IP 检测结果缓存：{ip: (result, timestamp, tls_ok)}
_cdn_ip_cache = {}
_CDN_IP_CACHE_TTL = 600
_CDN_IP_CACHE_TTL_TLS_FAIL = 300

def test_cdn_ip_connectivity(ip, port=443, timeout=3):
    """测试CDN IP连通性（TCP + TLS握手验证，带缓存）
    【v4.7修复】：增加TLS握手验证，Cloudflare已启用SNI严格验证，TCP通但TLS失败视为不可用
    """
    now = time.time()
    if ip in _cdn_ip_cache:
        cached_result, cached_time, cached_tls_ok = _cdn_ip_cache[ip]
        cache_ttl = _CDN_IP_CACHE_TTL if cached_tls_ok else _CDN_IP_CACHE_TTL_TLS_FAIL
        if now - cached_time < cache_ttl:
            return cached_result

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        if result != 0:
            _cdn_ip_cache[ip] = (False, now, False)
            return False
    except Exception:
        _cdn_ip_cache[ip] = (False, now, False)
        return False

    tls_ok = False
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(timeout)
        raw_sock.connect((ip, port))
        ssock = ctx.wrap_socket(raw_sock, server_hostname=CF_DOMAIN if CF_DOMAIN else 'cloudflare.com')
        ssock.close()
        raw_sock.close()
        tls_ok = True
    except Exception:
        tls_ok = False

    ok = tls_ok
    _cdn_ip_cache[ip] = (ok, now, tls_ok)
    return ok

# v4.5 CDN质量筛选器（全局单例）
_cdn_quality_filter = None
def get_cdn_quality_filter():
    """获取或初始化CDN质量筛选器"""
    global _cdn_quality_filter
    if _cdn_quality_filter is None:
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from cdn_quality_filter import CdnQualityFilter
            from config import USER_DDNS_DOMAIN, USER_EXPECTED_ISP, CDN_IP_HARD_REJECT, USER_QUALITY_THRESHOLD, HUNAN_CT_OPTIMAL_PREFIXES
            _cdn_quality_filter = CdnQualityFilter(
                db_path=DB_PATH,
                ddns_domain=USER_DDNS_DOMAIN,
                expected_isp=USER_EXPECTED_ISP,
                hard_reject=CDN_IP_HARD_REJECT,
                user_quality=USER_QUALITY_THRESHOLD,
                optimal_prefixes=HUNAN_CT_OPTIMAL_PREFIXES,
            )
        except Exception as e:
            logger.warning(f"无法初始化CdnQualityFilter: {e}")
    return _cdn_quality_filter

# 换IP冷却机制：连续失败3次后暂停15分钟
_ip_switch_fail_count = 0
_ip_switch_cooldown_until = 0  # 冷却结束时间戳
_IP_SWITCH_MAX_FAILS = 3
_IP_SWITCH_COOLDOWN_SECONDS = 900  # 15分钟
# [Trae CN] v4.12.13 迟滞阈值：新IP评分必须比当前高15%才触发切换（避免频繁切换加剧封禁）
_IP_HYSTERESIS_THRESHOLD = 0.15

def get_cdn_ip_for_protocol(protocol_key):
    """获取指定协议的CDN优选IP（被阻断自动换IP，不切换域名）

    【Bug #57修复】：
    1. 从数据库读取CDN IP和cdn_ips_list
    2. 快速测试连通性（3秒超时）
    3. 连不上就从cdn_ips_list中换一个IP（不切换域名）
    4. 被拦截的IP不淘汰，保留在池中，过段时间可能恢复

    【v4.3.8优化】：
    - 被阻断自动从池中换IP，不切换域名
    - 不淘汰被拦截的IP，只有黑名单IP才永久淘汰
    - 不每小时自动换IP，只有被阻断时才换

    【v4.3.9优化】：
    - 换IP冷却机制：连续失败3次后暂停15分钟，避免频繁换IP加剧封禁
    - 当前IP可用时重置失败计数

    【v4.10.1优化】：
    - 检测cdn_monitor更新信号，自动清空缓存刷新IP
    """
    global _ip_switch_fail_count, _ip_switch_cooldown_until, _cdn_ip_cache

    # [TRAE SOLO CN] v4.10.1 检测cdn_monitor更新信号，清空缓存
    signal_file = os.path.join(DATA_DIR, '.cdn_ip_updated')
    try:
        if os.path.exists(signal_file):
            _cdn_ip_cache.clear()
            os.remove(signal_file)
    except Exception:
        pass

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 获取当前CDN IP
        cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (protocol_key,))
        row = cursor.fetchone()

        if not row or not row[0] or row[0] == SERVER_IP:
            return None  # 没有CDN IP配置

        current_ip = row[0]

        # 冷却机制检查
        now = time.time()
        if now < _ip_switch_cooldown_until:
            # 冷却期内，直接返回当前IP（不检测不换IP）
            return current_ip

        # 快速连通性检测
        if test_cdn_ip_connectivity(current_ip):
            # v4.5 硬淘汰检查：即使连通，但延时/丢包/速度不达标也自动换
            cursor.execute("SELECT avg_latency, success_count, total_tests, fail_count, consecutive_fails, speed_mbps FROM ip_performance WHERE ip = ?", (current_ip,))
            perf_row = cursor.fetchone()
            if perf_row and perf_row[2] >= 3:  # 至少3次测试数据
                avg_lat, success_cnt, total_tests, fail_cnt, consec_fails, speed_mbps = perf_row
                fail_rate = fail_cnt / total_tests if total_tests > 0 else 0
                should_reject = False
                reject_reason = ''
                if avg_lat > 0 and avg_lat > CDN_IP_HARD_REJECT['latency_ms']:
                    should_reject = True
                    reject_reason = f'延时{avg_lat:.0f}ms>{CDN_IP_HARD_REJECT["latency_ms"]}ms'
                elif fail_rate > CDN_IP_HARD_REJECT['packet_loss_rate']:
                    should_reject = True
                    reject_reason = f'失败率{fail_rate*100:.0f}%>{CDN_IP_HARD_REJECT["packet_loss_rate"]*100:.0f}%'
                elif speed_mbps and speed_mbps > 0 and speed_mbps < CDN_IP_HARD_REJECT['download_speed_mbps']:
                    should_reject = True
                    reject_reason = f'速度{speed_mbps:.1f}Mbps<{CDN_IP_HARD_REJECT["download_speed_mbps"]}Mbps'
                if should_reject:
                    logger.warning(f"CDN IP {current_ip} 硬淘汰: {reject_reason}，自动换IP")
                    # 不返回current_ip，继续执行换IP逻辑
                else:
                    _ip_switch_fail_count = 0
                    return current_ip  # 当前IP正常，直接用
            else:
                _ip_switch_fail_count = 0
                return current_ip  # 数据不足，暂不淘汰
        # 当前IP被阻断或被硬淘汰，从cdn_ips_list中换一个
        logger.warning(f"CDN IP {current_ip} 被阻断，从池中换IP")
        print(f"[CDN IP切换] CDN IP {current_ip} 被阻断，从池中换IP")

        # 获取cdn_ips_list
        cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
        row = cursor.fetchone()
        if not row or not row[0]:
            logger.warning(f"cdn_ips_list为空，无法换IP")
            # 没有候选IP，触发冷却
            _ip_switch_fail_count += 1
            if _ip_switch_fail_count >= _IP_SWITCH_MAX_FAILS:
                _ip_switch_cooldown_until = time.time() + _IP_SWITCH_COOLDOWN_SECONDS
                logger.warning(f"连续{_ip_switch_fail_count}次换IP失败，进入{_IP_SWITCH_COOLDOWN_SECONDS//60}分钟冷却期")
                _ip_switch_fail_count = 0
            return current_ip  # 返回当前IP，不返回None

        # 过滤黑名单IP
        try:
            from config import CDN_IP_BLACKLIST
            blacklist = set(CDN_IP_BLACKLIST)
        except ImportError:
            blacklist = set()

        # [TRAE SOLO CN] v4.10.2 解析JSON格式的cdn_ips_list（含评分+延迟），按评分选IP
        try:
            ips_data = json.loads(row[0])
            if isinstance(ips_data, list) and ips_data and isinstance(ips_data[0], dict):
                all_ips = [item['ip'] for item in ips_data if item.get('ip')]
                scored_available = [item for item in ips_data
                                    if item.get('ip') and item['ip'] not in blacklist and item['ip'] != current_ip]
                scored_available.sort(key=lambda x: -x.get('score', 0))
            else:
                all_ips = [ip.strip() for ip in row[0].split(',') if ip.strip()]
                scored_available = None
        except (json.JSONDecodeError, TypeError):
            all_ips = [ip.strip() for ip in row[0].split(',') if ip.strip()]
            scored_available = None

        available_ips = [ip for ip in all_ips if ip not in blacklist and ip != current_ip]

        if not available_ips:
            logger.warning(f"没有可用的IP可以替换")
            # 所有候选IP都不可用，触发冷却
            _ip_switch_fail_count += 1
            if _ip_switch_fail_count >= _IP_SWITCH_MAX_FAILS:
                _ip_switch_cooldown_until = time.time() + _IP_SWITCH_COOLDOWN_SECONDS
                logger.warning(f"连续{_ip_switch_fail_count}次换IP失败，进入{_IP_SWITCH_COOLDOWN_SECONDS//60}分钟冷却期")
                _ip_switch_fail_count = 0
            return current_ip  # 返回当前IP，不返回None

        # [TRAE SOLO CN] v4.10.2 优先按评分选IP，不再随机
        new_ip = None
        cqf = get_cdn_quality_filter()
        if scored_available:
            new_ip = scored_available[0]['ip']
            new_score = scored_available[0].get('score', 0)
            logger.info(f"从{len(scored_available)}个候选IP中按评分选择: {new_ip} (score={new_score:.1f})")

            # [Trae CN] v4.12.13 迟滞检查：新IP评分必须比当前高15%才换（避免频繁切换加剧封禁）
            # 从原始 ips_data 中查找当前 IP 的评分（scored_available 已过滤掉 current_ip）
            current_score = 0
            for item in ips_data if isinstance(ips_data, list) else []:
                if isinstance(item, dict) and item.get('ip') == current_ip:
                    current_score = item.get('score', 0)
                    break
            if current_score > 0 and new_score > 0:
                threshold = current_score * (1 + _IP_HYSTERESIS_THRESHOLD)
                if new_score < threshold:
                    logger.info(f"迟滞保护：新IP {new_ip}({new_score:.1f}) 未比当前 {current_ip}({current_score:.1f}) 好15%（需>{threshold:.1f}），保持当前IP")
                    _ip_switch_fail_count = 0
                    return current_ip
        elif cqf:
            user_probe = cqf.probe_user_network()
            ranked = cqf.filter_and_rank(available_ips, user_probe)
            if ranked:
                new_ip = ranked[0][0]
                logger.info(f"从{len(ranked)}个合格IP中选择: {new_ip}")

        # 兜底：随机选
        if not new_ip:
            new_ip = random.choice(available_ips)

        # 更新数据库
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (protocol_key, new_ip))
        conn.commit()

        logger.info(f"CDN IP已替换: {current_ip} -> {new_ip}")
        print(f"[CDN IP切换] CDN IP切换: {current_ip} -> {new_ip}")
        return new_ip

    except Exception as e:
        logger.debug(f"获取CDN IP失败: {e}")
        print(f"[CDN IP切换] 获取CDN IP失败: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_sub_address():
    """获取订阅服务地址（域名或IP）- 使用config.py统一逻辑"""
    return get_sub_domain()

def get_cdn_optimized_domain():
    """获取优选域名（从数据库读取cdn_monitor测速选出的最优域名）
    [TRAE SOLO CN] v4.8：优选域名模式，走优化线路
    [v4.12.19] 修复 init_db() 无返回值导致数据库读取永远失效的bug
    """
    init_db()
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM cdn_settings WHERE key='cdn_optimized_domain'")
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return row[0].strip()
    except Exception:
        pass
    if CDN_OPTIMIZED_DOMAINS:
        return CDN_OPTIMIZED_DOMAINS[0]
    return None


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")






def resolve_ws_targets():
    """Resolve WS node address/SNI/name mode for Base64, sing-box, and Clash outputs."""
    cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP

    if not CDN_MODE_ENABLED:
        return SERVER_IP, SERVER_IP, cdn_sni, False

    if CDN_MODE == 'domain_default':
        vless_ws_addr = CF_DOMAIN
        trojan_ws_addr = CF_DOMAIN
    elif CDN_MODE == 'domain_optimized':
        optimized_domain = get_cdn_optimized_domain()
        vless_ws_addr = optimized_domain or CF_DOMAIN
        trojan_ws_addr = optimized_domain or CF_DOMAIN
    else:
        vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
        trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
        if not vless_ws_addr or vless_ws_addr == SERVER_IP:
            vless_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not trojan_ws_addr or trojan_ws_addr == SERVER_IP:
            trojan_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP

    if HK_DIRECT_MODE:
        return SERVER_IP, SERVER_IP, cdn_sni, True

    return vless_ws_addr, trojan_ws_addr, cdn_sni, True

def generate_all_links(capability='full'):
    """生成所有节点链接

    【v4.15.0 dual-stack 双模式支持 + anyTLS/TUIC v5】:
    - DIRECT_MODE_ENABLED（直连精简模式）：
      * full: 4节点（VLESS-Reality/Trojan-TCP/anyTLS/TUIC-v5），ENABLE_TUIC=false 时 3 节点
      * xray: 2节点（VLESS-Reality/Trojan-TCP，不含 anyTLS/TUIC）
    - CDN_MODE_ENABLED（CDN全量模式）：
      * full: 6节点（加上 VLESS-WS-CDN/Trojan-WS-CDN），ENABLE_TUIC=false 时 5 节点
      * xray: 4节点（加上 VLESS-WS-CDN/Trojan-WS-CDN，不含 anyTLS/TUIC）
    - capability='xray'：纯 Xray 内核客户端，跳过 anytls:// 和 tuic:// 非标准URI
    - capability='standard'：等同 xray（兼容旧参数）
    - v4.15.0: v2rayN 6.x+ 归 full（内置 sing-box 内核，支持 anytls:// 和 tuic://）
    """
    # v4.15.0: anyTLS 和 TUIC v5 都是非标准 URI，统一由 full 能力控制
    include_advanced = (capability == 'full')
    links = []

    ws_addr = None
    ws_sni = None

    vless_ws_addr, trojan_ws_addr, ws_sni, _ = resolve_ws_targets()
    ws_addr = (vless_ws_addr, trojan_ws_addr)

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
        'dest': REALITY_DEST,
        'headerType': 'none'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_UUID}@{SERVER_IP}:443?{param_str}#{share_fragment('VLESS-Reality')}")

    # 2. Trojan-TCP (直连)
    params = {
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP,
        'type': 'tcp',
        'headerType': 'none',
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"trojan://{TROJAN_PASSWORD}@{SERVER_IP}:{TROJAN_TCP_PORT}?{param_str}#{share_fragment('Trojan-TCP')}")

    if CDN_MODE_ENABLED:
        vless_ws_addr, trojan_ws_addr = ws_addr
        # 3. VLESS-WS (CDN)
        params = {
            'encryption': 'none',
            'type': 'ws',
            'security': 'tls',
            'sni': ws_sni,
            'path': '/api/v1/stream',
            'host': ws_sni,
            'allowInsecure': '1'
        }
        param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
        links.append(f"vless://{VLESS_WS_UUID}@{vless_ws_addr}:{VLESS_WS_PORT}?{param_str}#{share_fragment('VLESS-WS')}")

        # 4. Trojan-WS (CDN)
        params = {
            'type': 'ws',
            'security': 'tls',
            'sni': ws_sni,
            'insecure': '1',
            'allowInsecure': '1',
            'path': '/api/v1/data',
            'host': ws_sni,
        }
        param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
        links.append(f"trojan://{TROJAN_PASSWORD}@{trojan_ws_addr}:{TROJAN_WS_PORT}?{param_str}#{share_fragment('Trojan-WS')}")

    # 5. anyTLS (直连) - 仅 full 能力客户端输出（anytls:// 非标准URI，纯Xray内核客户端不认识）
    if include_advanced:
        anytls_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
        params = {
            'sni': anytls_sni,
            'insecure': '1',
            'fp': 'chrome',
        }
        param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
        links.append(f"anytls://{ANYTLS_PASSWORD_ENV}@{SERVER_IP}:{ANYTLS_PORT}/?{param_str}#{share_fragment('anyTLS')}")

    # 6. TUIC v5 (直连, UDP) - v4.15.0 加回：用户要求 TCP+UDP 双协议支持
    # tuic:// 非标准 URI，纯 Xray 内核客户端不认识，仅 full 能力输出
    # TUIC v5 认证：uuid + password 双因素
    # P0 修复（v4.15.0 审查）：ENABLE_TUIC=false 时不输出 TUIC URI，与服务端入站+防火墙三处同步
    if include_advanced and ENABLE_TUIC:
        tuic_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
        params = {
            'congestion_control': 'bbr',
            'alpn': 'h3',
            'udp_relay_mode': 'native',
            'sni': tuic_sni,
            'allow_insecure': '1',
        }
        param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
        links.append(f"tuic://{TUIC_UUID}:{TUIC_PASSWORD}@{SERVER_IP}:{TUIC_PORT}?{param_str}#{share_fragment('TUIC-v5')}")

    return links

def generate_singbox_config(capability='full'):
    """生成完整sing-box JSON配置（含自动路由规则）

    【标准 SOP 6 节点 / 直连 4 节点】:
    - DIRECT_MODE_ENABLED（直连精简模式）：4 节点（Reality/Trojan-TCP/anyTLS/TUIC）
    - CDN_MODE_ENABLED（CDN全量模式）：6 节点（加 WS-CDN/Trojan-WS-CDN）
    - capability='full' / 'standard' 等同（v4.14.0 起两者无差异）
    """
    ws_outbounds = []
    _auto_test_proxies_base = [
        node_name("VLESS-Reality"),
        node_name("Trojan-TCP"),
    ]

    if CDN_MODE_ENABLED:
        vless_ws_addr, trojan_ws_addr, ws_sni, _ = resolve_ws_targets()
        cdn_sni = ws_sni

        _auto_test_proxies = _auto_test_proxies_base + [
            node_name("VLESS-WS"),
            node_name("Trojan-WS"),
            node_name("anyTLS"),
        ] + ([node_name("TUIC-v5")] if ENABLE_TUIC else [])
    else:
        vless_ws_addr = SERVER_IP
        trojan_ws_addr = SERVER_IP
        ws_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
        # v4.15.1: 直连模式下 cdn_sni 也统一用主域名（而非 get_sub_domain() 返回 IP），
        # 保持 Trojan-TCP 等直连节点的 TLS SNI 与证书 CN 一致
        cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
        _auto_test_proxies = _auto_test_proxies_base + [
            node_name("anyTLS"),
        ] + ([node_name("TUIC-v5")] if ENABLE_TUIC else [])

    config = {
        "log": {
            "level": "info",
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns_proxy",
                    "type": "tls",
                    "server": "8.8.8.8"
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
                    "type": "h3",
                    "server": "dns.alidns.com",
                    "path": "/dns-query",
                    "domain_resolver": {
                        "server": "dns_proxy",
                        "strategy": "prefer_ipv4"
                    }
                    # 国内DNS（阿里DoH），专门用于解析中国大陆网站域名
                    # detour同样必须是direct，理由同上
                    # 使用h3协议（HTTP/3）可绕过国内对传统DoH(853)的干扰
                },
                {
                    "tag": "dns_block",
                    "type": "rcode",
                    "rcode": "success"
                    # 屏蔽DNS：返回success但不返回任何IP，用于屏蔽广告/恶意域名
                    # 原理：当route.rules中某条规则的outbound是"dns_block"时，
                    # 该域名的DNS查询会被此服务器处理，返回空响应，客户端无法连接
                },
                {
                    "tag": "dns_fakeip",
                    "type": "fakeip"
                    # FakeIP模式：返回198.18.0.0/15范围内的假IP，真实连接时singbox自动替换
                    # 优势：减少DNS查询延迟，避免DNS污染
                    # 注意：本项目未启用fakeip作为默认DNS，仅在dns.fakeip.enabled=True时生效
                }
            ],
            "rules": [
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
                },
                {
                    "outbound": "any",
                    "server": "dns_proxy"
                    # 兜底规则：未匹配任何规则的域名（如highvcc.vip等小众海外网站）
                    # 用Google DNS解析，确保海外网站能正常访问
                    # 【Bug #30 教训】：之前这条规则用dns_direct，导致海外网站通过国内DNS解析
                    # 可能拿到错误的IP或无法解析，必须用dns_proxy
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
            "strategy": "prefer_ipv4",
            "final": "dns_proxy",
            # DNS final规则：未被前面任何DNS规则匹配的域名，统一用dns_proxy解析
            # 即：非中国大陆网站默认用Google DNS，确保全球网站都能正常解析
            "fakeip": {
                # 默认关闭 FakeIP。
                # 原因：本项目的主要客户端是 v2rayN / sing-box TUN 场景，FakeIP 会让
                # ping/延迟测试经常命中本机分配的假 IP，出现 "<1ms" 这类误导性结果，
                # 用户会误以为节点或地区判断出了问题。真实线路质量应以实际连接体感
                # 和外部出口检测为准，而不是本机对 FakeIP 的 ICMP 响应。
                "enabled": False,
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
            # ePS-Auto: 用户可见的节点选择器
            # v4.15.0 dual-stack：CDN 模式 6 节点，直连模式 4 节点
            {
                "type": "selector",
                "tag": "ePS-Auto",
                "outbounds": _auto_test_proxies + [
                    "ePS-Auto-Test",
                    "direct"
                ],
                "default": "ePS-Auto-Test"
            },
            # ePS-Auto-Test: 自动测速选优节点（urltest类型，每60秒测速一次）
            {
                "type": "urltest",
                "tag": "ePS-Auto-Test",
                "outbounds": _auto_test_proxies,
                "interval": "60s",
                "tolerance": 150,
                "url": "http://cp.cloudflare.com/generate_204",
                "timeout": "5s"
            },
        ] + ([{
                # ai-residential: 幕后路由出站，AI网站流量自动走此出站
                # 用户在客户端看不到这个选项，路由规则自动匹配AI域名后走SOCKS5
                # 故障转移：所有SOCKS5不可用时自动fallback到direct
                "type": "selector",
                "tag": "ai-residential",
                "outbounds": [f"AI-SOCKS5-{i+1}" for i in range(len(SOCKS5_POOL))] + ["direct"],
                "default": "AI-SOCKS5-1"
            }] if SOCKS5_POOL and AI_SOCKS5_ROUTING == 'on' else []) + [
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
                "tag": node_name("VLESS-Reality"),
                "server": SERVER_IP,
                "server_port": 443,
                "uuid": VLESS_UUID,
                "flow": "xtls-rprx-vision",
                "packet_encoding": "xudp",
                "tcp_multi_path": False,
                "multiplex": {
                    "enabled": False
                },
                "connect_timeout": "5s",
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
                        "short_id": [REALITY_SHORT_ID]
                    }
                }
            },
            # Trojan-TCP (直连)
            {
                "type": "trojan",
                "tag": node_name("Trojan-TCP"),
                "server": SERVER_IP,
                "server_port": TROJAN_TCP_PORT,
                "password": TROJAN_PASSWORD,
                "tcp_multi_path": False,
                "multiplex": {
                    "enabled": False
                },
                "connect_timeout": "5s",
                "tls": {
                    "enabled": True,
                    "server_name": cdn_sni,
                    "insecure": True,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
                    "alpn": ["h2", "http/1.1"]
                }
            },
        ] + ([
            # VLESS-WS (CDN模式)
            {
                "type": "vless",
                "tag": node_name("VLESS-WS"),
                "server": vless_ws_addr,
                "server_port": VLESS_WS_PORT,
                "uuid": VLESS_WS_UUID,
                "packet_encoding": "xudp",
                "tcp_multi_path": False,
                "multiplex": {
                    "enabled": False
                },
                "connect_timeout": "5s",
                "tls": {
                    "enabled": True,
                    "server_name": ws_sni,
                    "insecure": True,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
                    "alpn": ["h2", "http/1.1"]
                },
                "transport": {
                    "type": "ws",
                    "path": "/api/v1/stream",
                    "headers": {
                        "Host": ws_sni
                    }
                }
            },
            # Trojan-WS (CDN模式)
            {
                "type": "trojan",
                "tag": node_name("Trojan-WS"),
                "server": trojan_ws_addr,
                "server_port": TROJAN_WS_PORT,
                "password": TROJAN_PASSWORD,
                "tcp_multi_path": False,
                "multiplex": {
                    "enabled": False
                },
                "connect_timeout": "5s",
                "tls": {
                    "enabled": True,
                    "server_name": ws_sni,
                    "insecure": True,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
                    "alpn": ["h2", "http/1.1"]
                },
                "transport": {
                    "type": "ws",
                    "path": "/api/v1/data",
                    "headers": {
                        "Host": ws_sni
                    }
                }
            },
        ] if CDN_MODE_ENABLED else []) + [
            # anyTLS (直连)
            # 缓解 TLS-in-TLS 指纹检测，配置极简（无 path/Host/serviceName）
            # 直连源站不走 CDN，SNI 用主域名（与证书匹配）
            {
                "type": "anytls",
                "tag": node_name("anyTLS"),
                "server": SERVER_IP,
                "server_port": ANYTLS_PORT,
                "password": ANYTLS_PASSWORD_ENV,
                "tls": {
                    "enabled": True,
                    "server_name": CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP,
                    "insecure": True,
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
                    "alpn": ["h2", "http/1.1"]
                },
                "connect_timeout": "5s"
            },
            # TUIC v5 (直连, UDP) - v4.15.0 加回
            # 用户要求 TCP+UDP 双协议支持，TUIC v5 提供 UDP relay
            # sing-box 1.11+ 支持 tuic outbound，认证方式 uuid+password
            # congestion_control=bbr 提升吞吐，udp_relay_mode=native 保留 UDP 语义
            # P0 修复（v4.15.0 审查）：ENABLE_TUIC=false 时不输出 TUIC outbound，与服务端入站+防火墙三处同步
            *([{
                "type": "tuic",
                "tag": node_name("TUIC-v5"),
                "server": SERVER_IP,
                "server_port": TUIC_PORT,
                "uuid": TUIC_UUID,
                "password": TUIC_PASSWORD,
                "congestion_control": "bbr",
                "udp_relay_mode": "native",
                "zero_rtt_handshake": False,
                "tls": {
                    "enabled": True,
                    "server_name": CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP,
                    "insecure": True,
                    "alpn": ["h3"]
                }
            }] if ENABLE_TUIC else []),
        ] + ([
            # AI-SOCKS5代理池 - 多代理自动容错切换
            # 从SOCKS5_POOL生成多个SOCKS5出站，ai-residential selector自动包含所有可用代理
            {
                "type": "socks",
                "tag": f"AI-SOCKS5-{i+1}",
                "server": proxy['server'],
                "server_port": proxy['port'],
                "version": "5",
                "username": proxy['user'],
                "password": proxy['pass']
            } for i, proxy in enumerate(SOCKS5_POOL)] if SOCKS5_POOL and AI_SOCKS5_ROUTING == 'on' else []) + [
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
            ] + ([
                # ⚠️ 排除X/推特/groK（不走AI-SOCKS5，走ePS-Auto正常代理）- 必须放在geosite-cn和AI规则之前！
                # 【Bug #25 路由顺序教训】：
                # sing-box路由规则是按数组顺序匹配的，第一条匹配到的规则生效！
                # 如果AI规则在前，x.com/twitter.com/grok.com会先被AI规则匹配（因为它们也是AI相关），
                # 导致走ai-residential → AI-SOCKS5，但用户其实希望这些网站走普通代理（ePS-Auto）
                # 正确做法：排除规则必须放在AI规则之前，确保X/groK先被拦截，走ePS-Auto
                #
                # 【Bug #29 致命教训 - geosite-cn 拦截 Google 子域名】：
                # 之前geosite-cn规则在AI规则之前（规则#3），而geosite-cn包含google.com及所有子域名！
                # gemini.google.com 被 geosite-cn 先匹配，走了 direct 直连，根本没轮到 AI 规则！
                # 修复：AI规则和排除规则必须放在 geosite-cn 之前，确保 Google AI 子域名被精确匹配。
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
                # 【Bug #29 致命教训 - geosite-cn 拦截】：
                # AI规则必须在 geosite-cn 之前！否则 gemini.google.com 等 Google 子域名
                # 会被 geosite-cn（包含所有 google.* 域名）先匹配，走了 direct 直连！
                #
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
                # ai-residential selector的outbounds包含["AI-SOCKS5-1", "AI-SOCKS5-2", ..., "direct"]
                # 当某个SOCKS5代理不可用时，sing-box会自动尝试下一个代理
                # 如果所有SOCKS5代理均不可用，最终fallback到direct（从VPS直连出去）
                # 虽然直连可能被AI网站封锁，但至少不会断网，用户仍能看到错误页面
                # 而不是无限转圈或连接超时
                #
                # 【为什么selector而不是直接写outbound】：
                # selector类型允许后续手动切换（如通过Clash API），
                # 如果某个SOCKS5长期故障，管理员可以手动切到其他代理或direct
                # 如果是urltest或loadbalance类型，则无法手动干预
                #
                # 【Bug #26 故障转移教训】：
                # 之前ai-residential的outbounds只有["AI-SOCKS5"]，没有direct备选
                # 当AI-SOCKS5宕机时，所有AI网站流量全部中断，用户无法访问
                # 修复后加入direct作为第二选项，确保至少不断网
                # 出站标签ai-residential → SOCKS5代理池（故障转移：不可用时自动切direct）
                # 触发条件：配置了AI_SOCKS5_POOL环境变量
                # 故障转移：所有SOCKS5不可用时自动fallback到direct（outbounds已包含direct作为第二选项）
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
                        "replicate.com",
                        "kimi.moonshot.cn",
                        "deepseek.com",
                        "cerebras.net",
                        "inflection.ai",
                        "mistral.ai",
                        "meta.ai",
                        "openai.org",
                        "chat.openai.com",
                        "api.openai.com",
                        "platform.openai.com",
                        "playground.openai.com",
                        "generativelanguage.googleapis.com",
                        "gemini.googleusercontent.com",
                        "makersuite.google.com",
                        "notebooklm.google.com",
                        "geminicode.app"
                    ],
                    "domain_keyword": [
                        "openai",
                        "anthropic",
                        "claude",
                        "gemini",
                        "perplexity",
                        "aistudio",
                        "chatgpt"
                    ],
                    "domain": [
                        "gemini.google.com"
                    ],
                    "outbound": "ai-residential"
                },
                # 非 AI 的 Google 域名排除规则：防止 geosite-cn 误匹配走 direct
                # 【Bug #31 教训】：geosite-cn 包含 google.com 及所有子域名
                # www.google.com、google.com 等会被 geosite-cn 先匹配走 direct 直连
                # 但服务器在海外，国内用户通过代理访问时，这些域名应该走代理而非直连
                # 注意：AI 子域名（gemini.google.com 等）已在上面规则中匹配，不会走到这里
                {
                    "domain_suffix": [
                        "google.com",
                        "googleapis.com",
                        "gstatic.com",
                        "googleusercontent.com",
                        "googlevideo.com",
                        "ggpht.com",
                        "blogger.com",
                        "blogblog.com",
                        "blogspot.com",
                        "ampproject.org",
                        "android.com",
                        "chrome.com",
                        "chromium.org",
                        "g.co",
                        "goo.gl",
                        "google.org",
                        "googleanalytics.com",
                        "googleapps.com",
                        "googlecode.com",
                        "googledrive.com",
                        "googleearth.com",
                        "googlemail.com",
                        "googlemaps.com",
                        "googlesource.com",
                        "googlestore.com",
                        "googletagmanager.com",
                        "googletagservices.com",
                        "googleweblight.com",
                        "googlezip.net",
                        "gvt1.com",
                        "gvt2.com",
                        "gvt3.com",
                        "withgoogle.com",
                        "youtube.com",
                        "youtu.be",
                        "ytimg.com",
                        "google.cn",
                        "google.com.hk",
                        "google.com.tw"
                    ],
                    "domain_keyword": [
                        "google"
                    ],
                    "outbound": "ePS-Auto"
                },
            ] if SOCKS5_POOL and AI_SOCKS5_ROUTING == 'on' else []) + [
                {
                    "rule_set": ["geosite-cn", "geoip-cn"],
                    "outbound": "direct"
                    # 中国大陆网站和IP → 直连，不消耗代理流量
                    # 原理：国内网站在国内访问延迟低，不需要绕行VPS
                    # 注意：geosite-cn（域名匹配）和geoip-cn（IP匹配）是"或"关系，
                    # 只要满足任一条件就走direct，确保国内流量100%直连
                    # ⚠️ 必须在 AI规则和X/groK排除规则 之后！
                    # 【Bug #29教训】：geosite-cn包含google.com及所有子域名，
                    # 如果放在AI规则之前，Gemini等Google AI子域名会被先匹配走direct！
                },
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
            # sing-box 1.14+ 不再接受缺省域名解析行为，客户端配置里显式指定默认解析器，
            # 这样 CDN 域名、阿里 DoH 域名、SOCKS5 主机名都不会再依赖 deprecated 开关。
            "default_domain_resolver": "dns_proxy",
            "final": "ePS-Auto"
            # 【final规则 - 兜底出站】：
            # 未被前面任何路由规则匹配的流量，全部走ePS-Auto
            #
            # 【为什么是ePS-Auto而不是direct】：
            # ePS-Auto是用户可见的节点选择器，包含5个代理节点（VLESS-Reality、VLESS-WS、
            # VLESS-HTTPUpgrade、Trojan-WS、TUIC v5）+ direct
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
            # 3. X/推特/groK → ePS-Auto（普通代理，排除AI-SOCKS5）
            # 4. AI网站 → ai-residential → AI-SOCKS5（住宅代理，故障时切direct）
            # 5. 中国大陆网站/IP → direct（直连）
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


def generate_clash_config(capability='full'):
    """生成Clash Meta (mihomo) 订阅配置（含url-test自动故障转移）

    【v4.15.0 dual-stack 双模式支持】:
    - DIRECT_MODE_ENABLED（直连精简模式）：4 节点代理
    - CDN_MODE_ENABLED（CDN全量模式）：6 节点代理
    - capability='full' / 'standard' 等同（v4.14.0 起两者无差异）

    ⚠️ Clash Meta v1.18.0+ 支持 VLESS-Reality 协议
    Clash Verge Rev 内置 mihomo 内核，完全支持所有协议
    配置自带url-test节点组，每60秒自动测速，断线3秒内自动切换
    """
    if CDN_MODE_ENABLED:
        vless_ws_addr, trojan_ws_addr, ws_sni, _ = resolve_ws_targets()
        cdn_sni = ws_sni
    else:
        vless_ws_addr = SERVER_IP
        trojan_ws_addr = SERVER_IP
        ws_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
        # v4.15.1: 直连模式下 cdn_sni 也统一用主域名（而非 get_sub_domain() 返回 IP），
        # 保持 Trojan-TCP 等直连节点的 TLS SNI 与证书 CN 一致
        cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP

    proxies = []
    
    # 1. VLESS-Reality (直连) - Clash Meta v1.18.0+ 支持
    proxies.append({
        "name": node_name("VLESS-Reality"),
        "type": "vless",
        "server": SERVER_IP,
        "port": 443,
        "uuid": VLESS_UUID,
        "tls": True,
        "udp": True,
        "network": "tcp",
        "flow": "xtls-rprx-vision",
        "multiplex": {
            "enabled": False
        },
        "reality-opts": {
            "public-key": REALITY_PUBLIC_KEY,
            "short-id": REALITY_SHORT_ID
        },
        "client-fingerprint": "chrome",
        "servername": REALITY_SNI
    })

    # 2. Trojan-TCP (直连)
    proxies.append({
        "name": node_name("Trojan-TCP"),
        "type": "trojan",
        "server": SERVER_IP,
        "port": TROJAN_TCP_PORT,
        "password": TROJAN_PASSWORD,
        "tls": True,
        "udp": True,
        "network": "tcp",
        "client-fingerprint": "chrome",
        "sni": cdn_sni,
        "alpn": ["h2", "http/1.1"],
        "skip-cert-verify": True
    })
    
    if CDN_MODE_ENABLED:
        # 3. VLESS-WS (CDN模式) - Clash Meta支持
        proxies.append({
            "name": node_name("VLESS-WS"),
            "type": "vless",
            "server": vless_ws_addr,
            "port": VLESS_WS_PORT,
            "uuid": VLESS_WS_UUID,
            "tls": True,
            "udp": True,
            "network": "ws",
            "multiplex": {
                "enabled": False
            },
            "servername": ws_sni,
            "ws-opts": {
                "path": "/api/v1/stream",
                "headers": {"Host": ws_sni}
            },
            "client-fingerprint": "chrome",
            "alpn": ["h2", "http/1.1"],
            "skip-cert-verify": True
        })
        
        # 4. Trojan-WS (CDN模式) - Clash Meta支持
        proxies.append({
            "name": node_name("Trojan-WS"),
            "type": "trojan",
            "server": trojan_ws_addr,
            "port": TROJAN_WS_PORT,
            "password": TROJAN_PASSWORD,
            "tls": True,
            "udp": True,
            "network": "ws",
            "multiplex": {
                "enabled": False
            },
            "sni": ws_sni,
            "ws-opts": {
                "path": "/api/v1/data",
                "headers": {"Host": ws_sni}
            },
            "client-fingerprint": "chrome",
            "skip-cert-verify": True,
            "alpn": ["h2", "http/1.1"]
        })

    # 5. anyTLS (直连) - v4.14.0 新增
    # Clash Meta (mihomo) 1.18+ 原生支持 anytls 协议类型
    # 缓解 TLS-in-TLS 指纹检测，配置极简（无 path/Host/serviceName）
    # 直连源站不走 CDN，SNI 用主域名（与证书匹配）
    anytls_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
    proxies.append({
        "name": node_name("anyTLS"),
        "type": "anytls",
        "server": SERVER_IP,
        "port": ANYTLS_PORT,
        "password": ANYTLS_PASSWORD_ENV,
        "udp": True,
        "sni": anytls_sni,
        "skip-cert-verify": True,
        "client-fingerprint": "chrome",
        "alpn": ["h2", "http/1.1"]
    })

    # 6. TUIC v5 (直连, UDP) - v4.15.0 加回
    # Clash Meta (mihomo) 1.18+ 原生支持 tuic 协议类型
    # 提供 UDP relay 支持，与 TCP 协议互补
    # congestion-controller=bbr 提升吞吐，udp-relay-mode=native 保留 UDP 语义
    # P0 修复（v4.15.0 审查）：ENABLE_TUIC=false 时不输出 TUIC 节点，与服务端入站+防火墙三处同步
    if ENABLE_TUIC:
        tuic_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
        proxies.append({
            "name": node_name("TUIC-v5"),
            "type": "tuic",
            "server": SERVER_IP,
            "port": TUIC_PORT,
            "uuid": TUIC_UUID,
            "password": TUIC_PASSWORD,
            "udp": True,
            "congestion-controller": "bbr",
            "udp-relay-mode": "native",
            "alpn": ["h3"],
            "sni": tuic_sni,
            "skip-cert-verify": True,
        })

    proxy_names = [p["name"] for p in proxies]
    # 标准 SOP：CDN 模式 6 节点（含 anyTLS+TUIC），直连模式 4 节点（含 anyTLS+TUIC）
    # ENABLE_TUIC=false 时各减 1 节点
    auto_proxy_names_base = [
        node_name("VLESS-Reality"),
        node_name("Trojan-TCP"),
    ]
    _tuic_proxy_name = [node_name("TUIC-v5")] if ENABLE_TUIC else []
    if CDN_MODE_ENABLED:
        auto_proxy_names = auto_proxy_names_base + [
            node_name("VLESS-WS"),
            node_name("Trojan-WS"),
            node_name("anyTLS"),
        ] + _tuic_proxy_name
    else:
        auto_proxy_names = auto_proxy_names_base + [
            node_name("anyTLS"),
        ] + _tuic_proxy_name
    
    config = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,
        "dns": {
            "enable": True,
            "listen": "0.0.0.0:1053",
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "default-nameserver": [
                "223.5.5.5",
                "119.29.29.29"
            ],
            "nameserver": [
                "223.5.5.5",
                "119.29.29.29",
                "https://dns.alidns.com/dns-query"
            ],
            "fallback": [
                "https://dns.google/dns-query",
                "https://cloudflare-dns.com/dns-query"
            ],
            "fallback-filter": {
                "geoip": True,
                "ipcidr": ["240.0.0.0/4"]
            }
        },
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": f"{COUNTRY_CODE}-节点选择",
                "type": "select",
                "proxies": [f"{COUNTRY_CODE}-自动选择"] + proxy_names
            },
            {
                "name": f"{COUNTRY_CODE}-自动选择",
                "type": "url-test",
                "proxies": auto_proxy_names,
                "url": "http://cp.cloudflare.com/generate_204",
                "interval": 60,
                "tolerance": 150,
                "lazy": False,
                "timeout": 5000
            }
        ],
        "rules": [
            "GEOIP,CN,DIRECT",
            "MATCH,{}".format(f"{COUNTRY_CODE}-节点选择")
        ]
    }
    
    return config


def create_app():
    """创建Flask应用"""
    from flask import Flask, Response, jsonify, request

    app = Flask(__name__)

    @app.after_request
    def add_cors_and_security_headers(response):
        """统一添加CORS和安全相关响应头，避免各端点重复设置
        [v4.12.19] 新增CORS支持，解决浏览器/在线订阅工具跨域问题
        """
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response

    @app.route('/')
    def home():
        traffic = get_traffic_stats()
        traffic_display = format_traffic(traffic['bytes_used'])
        total_gb = 900
        used_gb = round(traffic['bytes_used'] / (1024**3), 2)
        remaining_gb = round((total_gb - used_gb), 2)
        usage_percent = round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0

        # v4.15.0: 删除 VLESS-gRPC（用 TUIC v5 替代），节点数减 1
        # full 能力：CDN 模式 6 节点（含 anyTLS+TUIC），直连模式 4 节点（含 anyTLS+TUIC）
        # xray 能力：CDN 模式 4 节点（不含 anyTLS+TUIC），直连模式 2 节点（不含 anyTLS+TUIC）
        # ENABLE_TUIC=false 时 full 各减 1（xray 本就不含 TUIC，不受影响）
        _tuic_count = 1 if ENABLE_TUIC else 0
        node_count_full = (3 if DIRECT_MODE_ENABLED else 5) + _tuic_count
        node_count_xray = (2 if DIRECT_MODE_ENABLED else 4)
        mode_label = '直连精简模式' if DIRECT_MODE_ENABLED else 'CDN全量模式'
        mode_desc = '无CDN节点，直连协议' if DIRECT_MODE_ENABLED else '含CDN节点，WS-CDN协议'

        if DIRECT_MODE_ENABLED:
            cdn_section_html = '<div class="sub-box" style="opacity:0.5;"><p><strong>CDN延时测试：</strong></p><p class="info">当前为直连精简模式，CDN功能已禁用</p></div>'
            cdn_script_html = ''
        else:
            cdn_section_html = '''
            <div class="sub-box" id="cdn-test-section">
                <p><strong>CDN延时测试：</strong></p>
                <button onclick="runCdnTest()" style="padding:10px 20px;font-size:16px;background:#0066cc;color:white;border:none;border-radius:5px;cursor:pointer;">开始测速</button>
                <div id="cdn-test-result" style="margin-top:15px;"></div>
            </div>
            <script>
            async function runCdnTest() {
                const resultDiv = document.getElementById('cdn-test-result');
                const btn = event.target;
                btn.disabled = true;
                btn.textContent = '测试中...';
                resultDiv.innerHTML = '<p style="color:#666;">正在获取CDN IP列表...</p>';
                try {
                    const resp = await fetch('/api/cdn-test');
                    const data = await resp.json();
                    if (data.code !== 200 || !data.data.ips.length) {
                        resultDiv.innerHTML = '<p style="color:red;">无可用CDN IP</p>';
                        btn.disabled = false;
                        btn.textContent = '开始测速';
                        return;
                    }
                    const ips = data.data.ips;
                    resultDiv.innerHTML = '<p style="color:#666;">正在测试 ' + ips.length + ' 个CDN IP...</p>';
                    const results = [];
                    for (const ip of ips) {
                        const start = performance.now();
                        let ok = false;
                        try {
                            await fetch('https://' + ip + '/', {
                                method: 'HEAD', mode: 'no-cors',
                                signal: AbortSignal.timeout(5000)
                            });
                            ok = true;
                        } catch(e) { ok = false; }
                        const latency = Math.round(performance.now() - start);
                        results.push({ip: ip, latency: latency, ok: ok});
                    }
                    results.sort((a, b) => a.latency - b.latency);
                    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
                    html += '<tr style="background:#e8f4fd;"><th style="padding:6px;border:1px solid #ddd;">IP</th><th style="padding:6px;border:1px solid #ddd;">延时</th><th style="padding:6px;border:1px solid #ddd;">状态</th></tr>';
                    for (const r of results) {
                        const color = r.ok ? (r.latency < 200 ? 'green' : 'orange') : 'red';
                        html += '<tr><td style="padding:4px;border:1px solid #ddd;">' + r.ip + '</td>';
                        html += '<td style="padding:4px;border:1px solid #ddd;color:' + color + ';">' + (r.ok ? r.latency + 'ms' : '超时') + '</td>';
                        html += '<td style="padding:4px;border:1px solid #ddd;color:' + color + ';">' + (r.ok ? '可用' : '不可用') + '</td></tr>';
                    }
                    html += '</table>';
                    try {
                        await fetch('/api/cdn-test', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(results)
                        });
                    } catch(e) {}
                    resultDiv.innerHTML = html;
                } catch(e) {
                    resultDiv.innerHTML = '<p style="color:red;">测试失败: ' + e.message + '</p>';
                }
                btn.disabled = false;
                btn.textContent = '开始测速';
            }
            </script>
            '''
            # v4.15.2 修复：CDN 模式下 cdn_script_html 必须定义，否则第 2307 行 {cdn_script_html} 抛 UnboundLocalError
            # CDN 测试的 JS 已内联在 cdn_section_html 中，这里设为空字符串占位
            cdn_script_html = ''

        sub_info_cdn = ''
        if not DIRECT_MODE_ENABLED:
            sub_info_cdn = '<p class="info">- VLESS-WS-CDN / Trojan-WS-CDN：优先走 Cloudflare CDN；CF L7 阻断时自动降级 sub-* 直连保可用</p>'

        html = f"""
        <html>
        <head>
            <title>Singbox订阅服务</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
                h1 {{ color: #333; }}
                .sub-box {{ background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .sub-link {{ font-size: 16px; color: #0066cc; word-break: break-all; }}
                .info {{ color: #666; font-size: 14px; }}
                .traffic-box {{ background: #e8f4fd; padding: 20px; border-radius: 10px; margin: 20px 0; border: 1px solid #b3d9f2; }}
                .traffic-value {{ font-size: 28px; color: #0066cc; font-weight: bold; }}
                .traffic-bar-bg {{ background: #d0e4f7; height: 12px; border-radius: 6px; margin: 10px 0; overflow: hidden; }}
                .traffic-bar {{ background: #0066cc; height: 100%; border-radius: 6px; transition: width 0.3s; }}
                .traffic-label {{ color: #666; font-size: 14px; margin-top: 5px; }}
                .traffic-tip {{ color: #888; font-size: 12px; margin-top: 8px; }}
                .mode-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 13px; font-weight: bold; margin-left: 10px; }}
                .mode-direct {{ background: #e6f7e6; color: #2e7d32; }}
                .mode-cdn {{ background: #fff3e0; color: #e65100; }}
            </style>
        </head>
        <body>
            <h1>Singbox 订阅服务 <span class="mode-badge {'mode-direct' if DIRECT_MODE_ENABLED else 'mode-cdn'}">{mode_label}</span></h1>
            <p class="info">当前模式：{mode_desc}（Clash/sing-box/Shadowrocket/v2rayN 客户端 {node_count_full} 节点 | Surge/Quantumult X 等纯 Xray 客户端 {node_count_xray} 节点）</p>
            <div class="traffic-box">
                <p><strong>📊 当月流量统计（{get_country_name()}）</strong></p>
                <p class="traffic-value">{used_gb} GB / {total_gb} GB ({usage_percent}%)</p>
                <div class="traffic-bar-bg"><div class="traffic-bar" style="width: {usage_percent}%;"></div></div>
                <p class="traffic-label">统计月份：{traffic['month']} | 剩余：{remaining_gb} GB | 每月{traffic['reset_day']}号 00:03 更新baseline</p>
                <p class="traffic-tip">上次重置：{traffic['last_reset'] if traffic['last_reset'] else '尚未重置'} | 数据来源：iptables 内核级计数器（重启不丢失）</p>
                <p class="traffic-tip">💡 v2rayN 等客户端不显示流量？直接访问 <a href="/info">/info</a> 或 <a href="/api/traffic">/api/traffic</a> 查看</p>
            </div>
            <div class="sub-box">
                <p><strong>🔗 Base64订阅链接（自动适配客户端）</strong></p>
                <p class="sub-link">https://{get_sub_domain()}:{SUB_PORT}/sub/{COUNTRY_CODE}</p>
                <p class="info">- Clash Meta / sing-box / NekoBox / NekoRay / v2rayN 6.x+ / Shadowrocket：{node_count_full} 节点（含 anyTLS + TUIC v5）</p>
                <p class="info">- Surge / Quantumult X / v2Box 等纯 Xray 内核：{node_count_xray} 节点（不含 anyTLS/TUIC，标准 URI 兼容）</p>
                <p class="info">- Shadowrocket CONNECT/HTTP 测速更接近真实可用性；ICMP 仅作裸线路参考</p>
                <p class="info">- 💡 强制指定：?client=full 获全量节点 | ?client=xray 获 Xray 兼容节点（老版本客户端）</p>
                {sub_info_cdn}
            </div>
            <div class="sub-box">
                <p><strong>📦 sing-box JSON配置（含自动路由）</strong></p>
                <p class="sub-link">https://{get_sub_domain()}:{SUB_PORT}/singbox/{COUNTRY_CODE}</p>
                <p class="info">（导入后AI流量自动走SOCKS5，无需手动选择）</p>
                <p class="info">- 节点数：{node_count_full}（{mode_label}，含 anyTLS + TUIC v5）</p>
            </div>
            <div class="sub-box">
                <p><strong>⚔️ Clash Meta 配置（含 url-test 自动测速）</strong></p>
                <p class="sub-link">https://{get_sub_domain()}:{SUB_PORT}/clash/{COUNTRY_CODE}</p>
                <p class="info">（Clash Verge Rev / mihomo-party / Clash Nyanpasu 适用）</p>
                <p class="info">- 节点数：{node_count_full}（{mode_label}，含 anyTLS + TUIC v5）</p>
            </div>
            <div class="sub-box">
                <p><strong>📈 流量查询（所有客户端通用）</strong></p>
                <p class="sub-link">https://{get_sub_domain()}:{SUB_PORT}/info/{COUNTRY_CODE}</p>
                <p class="info">（纯文本输出 v2rayN 也能查看 / JSON 格式：Accept: application/json）</p>
            </div>
            <div class="info">
                <p>服务器IP: {SERVER_IP}</p>
                <p>订阅域名: {get_sub_domain()}（直连源站，绕过CF DDoS L7）</p>
                <p>主域名: {CF_DOMAIN if CF_DOMAIN else '未配置'}</p>
                <p>使用HTTPS: 是</p>
                <p>部署模式: {DEPLOY_MODE}（{mode_label}）</p>
            </div>
            {cdn_section_html}
            {cdn_script_html}
        </body>
        </html>
        """
        return Response(html, mimetype='text/html')

    @app.route(f'/sub/{COUNTRY_CODE}')
    @app.route(f'/sub/{COUNTRY_CODE.lower()}')
    @app.route('/sub')
    def get_subscription():
        """Base64订阅链接（兼容旧客户端）
        ⚠️ 禁止加token认证！订阅链接必须直接访问，不需要任何验证参数。
        历史教训：v1.0.54擅自加了SUB_TOKEN认证导致订阅不可用，已回退。
        铁律13：订阅链接不加token认证，保持原有规则直接访问。

        【v4.15.3 客户端能力适配（修复 Shadowrocket 节点缺失问题）】:
        - 根据 User-Agent 自动判断客户端能力
        - Clash Meta/mihomo/sing-box/NekoBox/NekoRay/v2rayN/v2rayNG/Shadowrocket（full）→ 6 节点（含 anyTLS + TUIC v5）
        - Surge/Quantumult X/Loon/v2Box（xray）→ 标准URI，4 节点（不含 anyTLS/TUIC）
        - 默认未知客户端按 xray 处理（安全保守，避免非标准 anytls:// URI 导致解析失败）
        - ?client=clash / ?client=full 强制返回全量节点（含 anyTLS）
        - ?client=v2rayn / ?client=xray / ?client=standard 强制返回 Xray 兼容节点（不含 anyTLS）
        """
        try:
            ua = request.headers.get('User-Agent', '')
            forced = request.args.get('client', '').lower().strip()
            capability = resolve_subscription_capability(forced, ua)

            links = generate_all_links(capability=capability)
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

            traffic = get_traffic_stats()
            total_bytes = 900 * 1024 * 1024 * 1024
            traffic_gb = round(traffic['bytes_used'] / (1024**3), 2)
            total_gb = round(total_bytes / (1024**3), 0)
            sub_text = '\n'.join(line for line in links if line.strip() and not line.lstrip().startswith('#'))
            sub_b64 = base64.b64encode(sub_text.encode('utf-8')).decode('utf-8')

            userinfo = f"upload=0; download={traffic['bytes_used']}; total={total_bytes}; expire=0"
            sub_name_cn = f"{get_country_name()}"
            sub_name_encoded = urllib.parse.quote(sub_name_cn, safe='')
            sub_name_ascii = f"{COUNTRY_CODE}.txt"
            profile_title = urllib.parse.quote(f"{get_country_name()}", safe='')
            return Response(sub_b64, mimetype='text/plain',
                            headers={
                                'subscription-userinfo': userinfo,
                                'Content-Disposition': f"attachment; filename=\"{sub_name_ascii}\"; filename*=UTF-8''{sub_name_encoded}.txt",
                                'profile-update-interval': '6',
                                'profile-title': profile_title,
                                'profile-web-page-url': f'https://{get_sub_domain()}:{SUB_PORT}/info',
                            })
        except Exception as e:
            logger.error(f"sub订阅生成失败: {e}")
            return Response("", mimetype='text/plain', status=500)

    @app.route(f'/singbox/{COUNTRY_CODE}')
    @app.route(f'/singbox/{COUNTRY_CODE.lower()}')
    @app.route('/singbox')
    def get_singbox_config():
        """完整sing-box JSON配置（含自动路由规则）
        ⚠️ 禁止加token认证！同/sub路由，直接访问。
        【v4.12.19】支持 ?client=full|standard 和 UA 自动检测，补齐RFC5987中文文件名
        """
        try:
            ua = request.headers.get('User-Agent', '')
            forced = request.args.get('client', '').lower().strip()
            capability = resolve_subscription_capability(forced, ua)
            config = generate_singbox_config(capability=capability)
            config_json = json.dumps(config, indent=2, ensure_ascii=False)
            traffic = get_traffic_stats()
            bytes_used = traffic['bytes_used']
            total_bytes = 900 * 1024 * 1024 * 1024
            total_gb = 900
            userinfo = f"upload=0; download={bytes_used}; total={total_bytes}; expire=0"
            sub_name_ascii = f"{COUNTRY_CODE}.json"
            sub_name_cn = f"{get_country_name()}"
            sub_name_encoded = urllib.parse.quote(sub_name_cn, safe='')
            profile_title = urllib.parse.quote(f"{get_country_name()}", safe='')
            return Response(
                config_json,
                mimetype='application/json',
                headers={
                    'subscription-userinfo': userinfo,
                    'Content-Disposition': f'attachment; filename="{sub_name_ascii}"; filename*=UTF-8\'\'{sub_name_encoded}',
                    'profile-update-interval': '6',
                    'profile-title': profile_title,
                    'profile-web-page-url': f'https://{get_sub_domain()}:{SUB_PORT}/info',
                }
            )
        except Exception as e:
            logger.error(f"singbox配置生成失败: {e}")
            return Response(json.dumps({"error": "config generation failed"}),
                            mimetype='application/json', status=500)

    @app.route(f'/clash/{COUNTRY_CODE}')
    @app.route(f'/clash/{COUNTRY_CODE.lower()}')
    @app.route('/clash')
    def get_clash_config():
        """Clash Meta (mihomo) 订阅配置（含url-test自动故障转移）
        ⚠️ 禁止加token认证！同/sub路由，直接访问。
        ⚠️ Clash Meta v1.18.0+ 支持 Reality 协议
        【v4.12.19】支持 ?client= 参数/UA检测，补alpn/tls/udp-relay，text/yaml，异常保护
        """
        try:
            import yaml
            ua = request.headers.get('User-Agent', '')
            forced = request.args.get('client', '').lower().strip()
            capability = resolve_subscription_capability(forced, ua)
            config = generate_clash_config(capability=capability)
            config_yaml = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
            traffic = get_traffic_stats()
            bytes_used = traffic['bytes_used']
            total_bytes = 900 * 1024 * 1024 * 1024
            total_gb = 900
            userinfo = f"upload=0; download={bytes_used}; total={total_bytes}; expire=0"
            sub_name_ascii = f"{COUNTRY_CODE}.yaml"
            sub_name_cn = f"{get_country_name()}"
            sub_name_encoded = urllib.parse.quote(sub_name_cn, safe='')
            profile_title = urllib.parse.quote(f"{get_country_name()}", safe='')
            return Response(
                config_yaml,
                mimetype='text/yaml',
                headers={
                    'subscription-userinfo': userinfo,
                    'Content-Disposition': f'attachment; filename="{sub_name_ascii}"; filename*=UTF-8\'\'{sub_name_encoded}',
                    'profile-update-interval': '6',
                    'profile-title': profile_title,
                    'profile-web-page-url': f'https://{get_sub_domain()}:{SUB_PORT}/info',
                }
            )
        except Exception as e:
            logger.error(f"clash配置生成失败: {e}")
            return Response(f"# config generation failed: {e}",
                            mimetype='text/plain', status=500)

    @app.route('/api/traffic')
    def traffic_api():
        """流量统计API（不加token认证，铁律13）
        返回当月流量使用情况JSON
        """
        stats = get_traffic_stats()
        stats['total_bytes'] = 900 * 1024 * 1024 * 1024
        stats['total_gb'] = 900
        stats['remaining_bytes'] = max(stats['total_bytes'] - stats['bytes_used'], 0)
        stats['remaining_gb'] = round(stats['remaining_bytes'] / (1024**3), 2)
        stats['usage_percent'] = round(stats['bytes_used'] / stats['total_bytes'] * 100, 2) if stats['total_bytes'] > 0 else 0
        return jsonify(stats)

    @app.route(f'/info/{COUNTRY_CODE}')
    @app.route(f'/info/{COUNTRY_CODE.lower()}')
    @app.route('/info')
    def info_endpoint():
        """流量信息端点（纯文本，给所有客户端看）
        [TRAE SOLO CN] v4.12.1：v2rayN 不解析 subscription-userinfo header，
        用户需要直接访问此端点查看流量。
        """
        from flask import request as _req
        accept = _req.headers.get('Accept', '')
        stats = get_traffic_stats()
        total_bytes = 900 * 1024 * 1024 * 1024
        traffic_gb = round(stats['bytes_used'] / (1024**3), 2)
        total_gb = int(total_bytes / (1024**3))
        remaining_gb = round((total_bytes - stats['bytes_used']) / (1024**3), 2)
        usage_percent = round(stats['bytes_used'] / total_bytes * 100, 2) if total_bytes > 0 else 0

        if 'application/json' in accept:
            return jsonify({
                'server': get_country_name(),
                'month': stats['month'],
                'used_gb': traffic_gb,
                'used_bytes': stats['bytes_used'],
                'total_gb': total_gb,
                'total_bytes': total_bytes,
                'remaining_gb': remaining_gb,
                'remaining_bytes': max(total_bytes - stats['bytes_used'], 0),
                'usage_percent': usage_percent,
                'reset_day': stats['reset_day'],
                'last_reset': stats['last_reset'] or '尚未重置',
                'reset_note': f'每月{stats["reset_day"]}号 00:03 更新baseline（不清零iptables计数器）',
            })
        # 默认纯文本（最通用，v2rayN 浏览器都能看）
        text = (
            f"📊 {get_country_name()}服务器流量统计\n"
            f"==========================================\n"
            f"统计月份: {stats['month']}\n"
            f"已用流量: {traffic_gb} GB ({stats['bytes_used']:,} bytes)\n"
            f"剩余流量: {remaining_gb} GB\n"
            f"套餐总量: {total_gb} GB\n"
            f"使用百分比: {usage_percent}%\n"
            f"重置规则: 每月{stats['reset_day']}号 00:03 更新baseline（不清零iptables）\n"
            f"上次重置: {stats['last_reset'] or '尚未重置'}\n"
            f"==========================================\n"
            f"提示：\n"
            f"- Clash/Stash/Clash Verge 客户端：打开订阅即可看到流量\n"
            f"- v2rayN/v2rayNG：每次更新订阅看不到流量属客户端限制（不支持 subscription-userinfo header），\n"
            f"  请直接访问 https://{get_sub_domain()}:{SUB_PORT}/info 查看\n"
            f"- 流量来源：iptables 内核级计数器（重启不丢失）\n"
        )
        return Response(text, mimetype='text/plain; charset=utf-8')

    @app.route('/api/cdn', methods=['GET', 'POST'])
    def cdn_api():
        if DIRECT_MODE_ENABLED:
            return jsonify({'code': 200, 'msg': 'direct mode - CDN features disabled', 'data': {'mode': DEPLOY_MODE}})
        if request.method == 'POST':
            data = request.get_json() or {}
            protocol = data.get('protocol', '').strip()
            new_ip = data.get('ip', '').strip()
            if not protocol or not new_ip:
                return jsonify({'error': 'protocol and ip required'}), 400
            if not is_valid_ipv4(new_ip):
                return jsonify({'error': 'Invalid IP format'}), 400
            if protocol not in CDN_PROTOCOL_KEYS:
                return jsonify({'error': 'Invalid protocol key'}), 400
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (protocol, new_ip))
                added, pool = add_ips_to_pool(conn, [new_ip])
                return jsonify({
                    'code': 200,
                    'data': {
                        'protocol': protocol,
                        'ip': new_ip,
                        'pool_added': added,
                        'pool_size': len(pool)
                    },
                    'msg': 'success'
                })
            except Exception as e:
                logger.error(f"CDN API错误: {e}")
                return jsonify({'code': 500, 'data': {}, 'msg': 'error'}), 500
            finally:
                if conn:
                    conn.close()
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            settings, current, pool = get_cdn_pool_state(conn)
            return jsonify({
                'code': 200,
                'data': {
                    'settings': settings,
                    'current': current,
                    'pool': pool,
                    'pool_size': len(pool),
                    'blacklist_size': len(CDN_IP_BLACKLIST)
                },
                'msg': 'success'
            })
        except Exception as e:
            logger.error(f"CDN API错误: {e}")
            return jsonify({'code': 500, 'data': {}, 'msg': 'error'}), 500
        finally:
            if conn:
                conn.close()

    @app.route('/api/preferred-ips', methods=['GET', 'POST', 'DELETE'])
    def preferred_ips_api():
        if DIRECT_MODE_ENABLED:
            return jsonify({'code': 200, 'msg': 'direct mode - CDN features disabled', 'data': {'mode': DEPLOY_MODE}})
        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            if request.method == 'GET':
                settings, current, pool = get_cdn_pool_state(conn)
                return jsonify({
                    'code': 200,
                    'data': {
                        'current': current,
                        'pool': pool,
                        'pool_size': len(pool),
                        'static_preferred_count': len(CDN_PREFERRED_IPS),
                        'blacklist': CDN_IP_BLACKLIST
                    },
                    'msg': 'success'
                })

            data = request.get_json(silent=True)
            if request.method == 'POST':
                if isinstance(data, dict):
                    candidates = [data]
                elif isinstance(data, list):
                    candidates = data
                else:
                    return jsonify({'code': 400, 'data': {}, 'msg': 'invalid payload'}), 400
                normalized = []
                invalid = []
                for item in candidates:
                    ip = str(item.get('ip', '')).strip() if isinstance(item, dict) else ''
                    if is_valid_ipv4(ip):
                        normalized.append(ip)
                    else:
                        invalid.append(ip)
                if not normalized:
                    return jsonify({'code': 400, 'data': {'invalid': invalid}, 'msg': 'no valid ips'}), 400
                added, pool = add_ips_to_pool(conn, normalized)
                return jsonify({
                    'code': 200,
                    'data': {
                        'added': added,
                        'invalid': invalid,
                        'pool_size': len(pool)
                    },
                    'msg': 'success'
                })

            payload = data or {}
            remove_all = bool(payload.get('all')) if isinstance(payload, dict) else False
            if remove_all:
                _, _, pool = get_cdn_pool_state(conn)
                removed, new_pool = remove_ips_from_pool(conn, pool)
                return jsonify({
                    'code': 200,
                    'data': {'removed': removed, 'pool_size': len(new_pool)},
                    'msg': 'success'
                })
            if isinstance(payload, dict):
                ips = payload.get('ips')
                if not ips and payload.get('ip'):
                    ips = [payload.get('ip')]
            else:
                ips = None
            if not isinstance(ips, list):
                return jsonify({'code': 400, 'data': {}, 'msg': 'ips required'}), 400
            normalized = [str(ip).strip() for ip in ips if is_valid_ipv4(str(ip).strip())]
            removed, new_pool = remove_ips_from_pool(conn, normalized)
            return jsonify({
                'code': 200,
                'data': {
                    'removed': removed,
                    'requested': normalized,
                    'pool_size': len(new_pool)
                },
                'msg': 'success'
            })
        except Exception as e:
            logger.error(f"Preferred IP API错误: {e}")
            return jsonify({'code': 500, 'data': {}, 'msg': 'error'}), 500
        finally:
            if conn:
                conn.close()

    # v4.5 浏览器端CDN延时测试API
    @app.route('/api/cdn-test', methods=['GET', 'POST'])
    def cdn_test_api():
        """
        浏览器端CDN延时测试
        GET: 返回CDN IP池列表供浏览器测试
        POST: 接收浏览器端测试结果，写入评分数据库
        """
        if DIRECT_MODE_ENABLED:
            return jsonify({'code': 200, 'msg': 'direct mode - CDN features disabled', 'data': {'mode': DEPLOY_MODE}})
        if request.method == 'GET':
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
                row = cursor.fetchone()
                ips = parse_cdn_ips_list(row[0]) if row and row[0] else []
                return jsonify({
                    'code': 200,
                    'data': {'ips': ips, 'count': len(ips)},
                    'msg': 'success'
                })
            except Exception as e:
                return jsonify({'code': 500, 'data': {}, 'msg': str(e)}), 500
            finally:
                if conn:
                    conn.close()

        # POST: 接收浏览器端测试结果
        data = request.get_json(silent=True)
        if not data or not isinstance(data, list):
            return jsonify({'code': 400, 'data': {}, 'msg': '需要IP测试结果列表'}), 400

        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            saved = 0
            for item in data:
                ip = str(item.get('ip', '')).strip()
                latency = item.get('latency', -1)
                ok = item.get('ok', False)
                if not ip or latency < 0:
                    continue
                # 写入测试历史
                now = datetime.now().isoformat()
                cursor.execute(
                    "INSERT INTO ip_test_history (ip, latency, success, test_time) VALUES (?, ?, ?, ?)",
                    (ip, latency if ok else None, 1 if ok else 0, now)
                )
                # 更新性能数据
                cursor.execute("SELECT * FROM ip_performance WHERE ip = ?", (ip,))
                row = cursor.fetchone()
                if row:
                    total = row[1] + 1
                    success_cnt = row[2] + (1 if ok else 0)
                    fail_cnt = row[3] + (0 if ok else 1)
                    consec_fails = (row[4] + 1) if not ok else 0
                    old_avg = row[5]
                    old_success_cnt = row[2]
                    if ok and latency is not None:
                        new_avg = (old_avg * old_success_cnt + latency) / (old_success_cnt + 1)
                    else:
                        new_avg = old_avg
                    min_lat = min(row[6], latency) if ok and latency is not None else row[6]
                    max_lat = max(row[7], latency) if ok and latency is not None else row[7]
                    last_success = now if ok else row[9]
                    cursor.execute("""
                        UPDATE ip_performance SET
                            total_tests=?, success_count=?, fail_count=?,
                            consecutive_fails=?, avg_latency=?, min_latency=?,
                            max_latency=?, last_test_time=?, last_success_time=?
                        WHERE ip=?
                    """, (total, success_cnt, fail_cnt, consec_fails, new_avg,
                          min_lat, max_lat, now, last_success, ip))
                else:
                    cursor.execute("""
                        INSERT INTO ip_performance
                        (ip, total_tests, success_count, fail_count, consecutive_fails,
                         avg_latency, min_latency, max_latency, last_test_time,
                         last_success_time, first_seen, source)
                        VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (ip, 1 if ok else 0, 0 if ok else 1, 0 if ok else 1,
                          latency if ok else 0, latency if ok else 9999,
                          latency if ok else 0, now, now if ok else None, now, 'browser'))
                saved += 1
            conn.commit()
            return jsonify({
                'code': 200,
                'data': {'saved': saved},
                'msg': 'success'
            })
        except Exception as e:
            logger.error(f"CDN测试结果保存失败: {e}")
            return jsonify({'code': 500, 'data': {}, 'msg': str(e)}), 500
        finally:
            if conn:
                conn.close()

    # ==================== v4.6 CDN故障自愈状态查询 ====================
    _failover_controller = None
    _health_monitor = None

    @app.route('/api/cdn-status', methods=['GET'])
    def cdn_status_api():
        """
        CDN健康状态查询
        返回当前CDN IP的健康状态、冷却池、切换历史
        """
        if DIRECT_MODE_ENABLED:
            return jsonify({'code': 200, 'msg': 'direct mode - CDN features disabled', 'data': {'mode': DEPLOY_MODE}})
        nonlocal _failover_controller, _health_monitor

        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            settings = load_cdn_settings(conn)

            # 获取各协议当前CDN IP
            # v4.14.0: 删除 vless-httpupgrade（HTTPUpgrade 已下线）
            protocols = {
                'vless-ws': 'vless_ws_cdn_ip',
                'trojan-ws': 'trojan_ws_cdn_ip',
            }
            current_ips = {}
            current_protocols = {}
            for name, key in protocols.items():
                ip = settings.get(key)
                current_ips[name] = ip
                current_protocols[name] = {
                    'setting_key': key,
                    'node_name': node_name({
                        'vless-ws': 'VLESS-WS',
                        'trojan-ws': 'Trojan-WS',
                    }[name], cdn=True),
                    'ip': ip,
                    'preferred_static': ip in CDN_PREFERRED_IPS if ip else False,
                    'blacklisted': ip in CDN_IP_BLACKLIST if ip else False,
                    'performance': get_ip_performance_snapshot(cursor, ip),
                }

            # 获取IP池
            pool_details = parse_cdn_pool_details(settings.get('cdn_ips_list', ''))
            pool = [item['ip'] for item in pool_details if item.get('ip')]
            pool_by_ip = {item.get('ip'): item for item in pool_details if item.get('ip')}
            for data in current_protocols.values():
                ip = data.get('ip')
                data['pool_entry'] = pool_by_ip.get(ip, {}) if ip else {}

            # 健康检查每个当前IP
            health_checks = {}
            if _health_monitor is None:
                try:
                    from cdn_quality_filter import CdnHealthMonitor
                    _health_monitor = CdnHealthMonitor(db_path=DB_PATH)
                except Exception:
                    pass

            if _health_monitor:
                for name, ip in current_ips.items():
                    if ip:
                        health_checks[name] = _health_monitor.check_ip(ip)

            # [Trae CN] v4.12.13 启用故障切换控制器状态查询（只读，不触发切换）
            if _failover_controller is None and _health_monitor:
                try:
                    from cdn_quality_filter import CdnFailoverController
                    _failover_controller = CdnFailoverController(
                        db_path=DB_PATH, health_monitor=_health_monitor)
                except Exception:
                    pass

            # 故障切换控制器状态
            failover_status = None
            if _failover_controller:
                try:
                    failover_status = _failover_controller.get_status()
                except Exception:
                    failover_status = None

            # 冷却池IP
            cooldown_ips = [c['ip'] for c in failover_status['cooldown_pool']] if failover_status else []

            return jsonify({
                'code': 200,
                'data': {
                    'cdn_mode': CDN_MODE,
                    'cdn_updated_at': settings.get('cdn_updated_at'),
                    'preferred_static_count': len(CDN_PREFERRED_IPS),
                    'blacklist_size': len(CDN_IP_BLACKLIST),
                    'protocols': current_protocols,
                    'current_ips': current_ips,
                    'health_checks': health_checks,
                    'pool_total': len(pool),
                    'pool_available': len([ip for ip in pool if ip not in cooldown_ips]),
                    'cooldown_ips': cooldown_ips,
                    'failover': failover_status,
                },
                'msg': 'success'
            })
        except Exception as e:
            logger.error(f"CDN状态查询失败: {e}")
            return jsonify({'code': 500, 'data': {}, 'msg': str(e)}), 500
        finally:
            if conn:
                conn.close()

    # ==================== v4.6.1 直连节点配置优化 ====================
    @app.route('/api/direct-optimize', methods=['GET'])
    def direct_optimize_api():
        """
        基于用户网络特征优化REALITY直连节点配置
        测试不同SNI的TLS握手速度，给出最优SNI和TCP调优建议
        """
        try:
            from direct_quality_filter import DirectNodeQualityFilter
            dqf = DirectNodeQualityFilter(db_path=DB_PATH, ddns_domain=USER_DDNS_DOMAIN)

            # 获取用户网络探测结果
            user_probe = None
            try:
                from cdn_quality_filter import CdnQualityFilter
                cqf = CdnQualityFilter(db_path=DB_PATH, ddns_domain=USER_DDNS_DOMAIN)
                user_probe = cqf.probe_user_network()
            except Exception:
                pass

            result = dqf.optimize_reality_config(user_probe)

            return jsonify({
                'code': 200,
                'data': result,
                'msg': 'success'
            })
        except Exception as e:
            logger.error(f"直连优化失败: {e}")
            return jsonify({'code': 500, 'data': {}, 'msg': str(e)}), 500

    return app


if __name__ == '__main__':
    init_db()

    # 初始化iptables流量计数器（sing-box各入站端口）
    try:
        setup_iptables_traffic_counters()
        logger.info("iptables流量计数器初始化完成")
    except Exception as e:
        logger.warning(f"iptables流量计数器初始化失败: {e}，将使用备用统计方式")

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
    logger.info(f"v4.15.0 Starting HTTPS subscription service on 0.0.0.0:{SUB_PORT}")
    logger.info(f"DEPLOY_MODE: {DEPLOY_MODE} | CDN_MODE_ENABLED: {CDN_MODE_ENABLED} | DIRECT_MODE_ENABLED: {DIRECT_MODE_ENABLED}")
    node_count = 5 if DIRECT_MODE_ENABLED else 7
    logger.info(f"节点配置: {node_count} 个节点（{'直连精简' if DIRECT_MODE_ENABLED else 'CDN全量'}模式）")
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
    # [TRAE SOLO CN] v4.10.17 使用gevent WSGI替代Flask开发服务器
    try:
        from gevent.pywsgi import WSGIServer
        http_server = WSGIServer(('0.0.0.0', SUB_PORT), app,
                                 keyfile=cert_key, certfile=cert_chain)
        logger.info(f"gevent WSGI服务器启动: 0.0.0.0:{SUB_PORT}")
        http_server.serve_forever()
    except ImportError:
        logger.warning("gevent未安装，降级使用Flask开发服务器")
        app.run(host='0.0.0.0', port=SUB_PORT, threaded=True,
                ssl_context=(cert_chain, cert_key))
