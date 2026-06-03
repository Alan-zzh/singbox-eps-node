#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v4.10.18
Date: 2026-06-01
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
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, HYSTERIA2_PORT, SOCKS5_PORT,
        HYSTERIA2_UDP_PORTS, REALITY_SHORT_ID, REALITY_DEST, REALITY_SNI,
        AI_SOCKS5_SERVER, AI_SOCKS5_PORT, AI_SOCKS5_USER, AI_SOCKS5_PASS,
        AI_SOCKS5_ROUTING, AI_SOCKS5_POOL, COUNTRY_CODE, SUB_TOKEN, get_sub_domain, BASE_DIR,
        CDN_PREFERRED_IPS, CDN_IP_BLACKLIST, CDN_IP_HARD_REJECT, CDN_MODE, CDN_OPTIMIZED_DOMAINS
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
    def get_sub_domain():
        """降级：config.py导入失败时，用CF_DOMAIN或SERVER_IP作为订阅地址"""
        return CF_DOMAIN if CF_DOMAIN else SERVER_IP

logger = get_logger('subscription_service')

IP_REGEX = re.compile(r'^\d{1,3}(?:\.\d{1,3}){3}$')
CDN_PROTOCOL_KEYS = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']


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
    if not raw_value:
        return []
    raw = raw_value.strip()
    if raw.startswith('['):
        try:
            items = json.loads(raw)
            if isinstance(items, list) and items and isinstance(items[0], dict):
                return [item['ip'] for item in items if isinstance(item, dict) and item.get('ip')]
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return [ip.strip() for ip in raw.split(',') if ip.strip()]


def get_cdn_pool_state(conn):
    settings = load_cdn_settings(conn)
    current = {key: settings.get(key, '') for key in CDN_PROTOCOL_KEYS}
    pool_raw = settings.get('cdn_ips_list', '')
    pool = parse_cdn_ips_list(pool_raw)
    return settings, current, pool


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
HYSTERIA2_PASSWORD = os.getenv('HYSTERIA2_PASSWORD', '')
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

def setup_iptables_traffic_counters():
    """配置iptables流量计数器（sing-box各入站端口）
    机场面板标准做法：
    - 在INPUT链中添加针对sing-box各入站端口的统计规则
    - iptables计数器是内核级别的，持久化、重启不丢失
    - 端口：443(VLESS-Reality/HY2), 8443(VLESS-WS), 2053(VLESS-HTTPUpgrade), 2083(Trojan-WS)
    幂等操作：重复调用不会添加重复规则
    """
    singbox_ports = [443, 8443, 2053, 2083]

    for port in singbox_ports:
        # 先检查规则是否已存在（幂等）
        check_cmd = f'iptables -L INPUT -v -n -x | grep -c "dpt:{port}"'
        ret, out, err = _run_cmd(check_cmd)
        if ret == 0 and int(out.strip()) > 0:
            continue  # 规则已存在，跳过

        # 添加TCP统计规则
        add_cmd = f'iptables -I INPUT 1 -p tcp --dport {port} -j ACCEPT'
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
    原理：iptables -L INPUT -v -n -x 返回每条规则的packet/byte计数器
    取所有sing-box端口规则的bytes总和
    """
    singbox_ports = [443, 8443, 2053, 2083]
    total_bytes = 0

    cmd = 'iptables -L INPUT -v -n -x'
    ret, out, err = _run_cmd(cmd)
    if ret != 0:
        logger.warning(f"iptables命令执行失败: {err}")
        return -1

    for line in out.split('\n'):
        if 'dpt:' not in line:
            continue
        for port in singbox_ports:
            if f'dpt:{port}' in line:
                # 行格式: pkts bytes target prot opt in out source destination
                # 例: 12345 6789012345 ACCEPT tcp -- * * 0.0.0.0/0 0.0.0.0/0 tcp dpt:443
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
                               ('iptables_baseline', str(iptables_bytes)))
                logger.info(f"iptables基准值初始化: {iptables_bytes} bytes")
                # 同时清除旧的current_bytes（旧版本update_traffic写入的订阅文件大小）
                cursor.execute("DELETE FROM traffic_stats WHERE key='current_bytes'")
                conn.commit()
                return  # 初始化完成，不需要重置月份
            else:
                # iptables不可用，创建空基准值
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
            logger.info(f"从{len(scored_available)}个候选IP中按评分选择: {new_ip} (score={scored_available[0].get('score',0):.1f})")
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
        return new_ip

    except Exception as e:
        logger.debug(f"获取CDN IP失败: {e}")
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
    """
    try:
        db_path = init_db()
        if not db_path:
            return None
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key='cdn_optimized_domain'")
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return row[0].strip()
    except Exception:
        pass
    if CDN_OPTIMIZED_DOMAINS:
        return CDN_OPTIMIZED_DOMAINS[0]
    return None

def generate_all_links():
    """生成所有节点链接"""
    links = []

    # CDN节点地址：根据CDN_MODE选择 [TRAE SOLO CN] v4.8
    if CDN_MODE == 'domain_default':
        vless_ws_addr = CF_DOMAIN
        vless_upgrade_addr = CF_DOMAIN
        trojan_ws_addr = CF_DOMAIN
        cdn_suffix = "-CDN-D"
        use_cdn = bool(CF_DOMAIN and CF_DOMAIN.strip())
    elif CDN_MODE == 'domain_optimized':
        optimized_domain = get_cdn_optimized_domain()
        vless_ws_addr = optimized_domain or CF_DOMAIN
        vless_upgrade_addr = optimized_domain or CF_DOMAIN
        trojan_ws_addr = optimized_domain or CF_DOMAIN
        cdn_suffix = "-CDN-O"
        use_cdn = bool(optimized_domain or (CF_DOMAIN and CF_DOMAIN.strip()))
    else:
        vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
        vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
        trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
        use_cdn = (vless_ws_addr is not None and vless_ws_addr != SERVER_IP)
        cdn_suffix = "-CDN"
        if not vless_ws_addr or vless_ws_addr == SERVER_IP:
            vless_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not vless_upgrade_addr or vless_upgrade_addr == SERVER_IP:
            vless_upgrade_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not trojan_ws_addr or trojan_ws_addr == SERVER_IP:
            trojan_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP

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
    # 注意：obfs已移除，因为Shadowrocket对salamander支持有限
    params = {
        'sni': REALITY_SNI,
        'insecure': '1',
        'mport': '443,21000-21200'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"hysteria2://{HYSTERIA2_PASSWORD}@{SERVER_IP}:443?{param_str}#{COUNTRY_CODE}-Hysteria2")

    return links

def generate_singbox_config():
    """生成完整sing-box JSON配置（含自动路由规则）"""
    if CDN_MODE == 'domain_default':
        vless_ws_addr = CF_DOMAIN
        vless_upgrade_addr = CF_DOMAIN
        trojan_ws_addr = CF_DOMAIN
    elif CDN_MODE == 'domain_optimized':
        optimized_domain = get_cdn_optimized_domain()
        vless_ws_addr = optimized_domain or CF_DOMAIN
        vless_upgrade_addr = optimized_domain or CF_DOMAIN
        trojan_ws_addr = optimized_domain or CF_DOMAIN
    else:
        vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
        vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
        trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
        if not vless_ws_addr or vless_ws_addr == SERVER_IP:
            vless_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not vless_upgrade_addr or vless_upgrade_addr == SERVER_IP:
            vless_upgrade_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not trojan_ws_addr or trojan_ws_addr == SERVER_IP:
            trojan_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP

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
                    "ePS-Auto-Test",
                    "direct"
                ],
                "default": "ePS-Auto-Test"
            },
            # ePS-Auto-Test: 自动测速选优节点（urltest类型，每60秒测速一次）
            {
                "type": "urltest",
                "tag": "ePS-Auto-Test",
                "outbounds": [
                    f"{COUNTRY_CODE}-VLESS-WS",
                    f"{COUNTRY_CODE}-VLESS-HTTPUpgrade",
                    f"{COUNTRY_CODE}-Trojan-WS",
                ],
                "interval": "60s",
                "tolerance": 150,
                "url": "http://cp.cloudflare.com/generate_204"
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
                "tag": f"{COUNTRY_CODE}-VLESS-Reality",
                "server": SERVER_IP,
                "server_port": 443,
                "uuid": VLESS_UUID,
                "flow": "xtls-rprx-vision",
                "packet_encoding": "xudp",
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
                        "short_id": list(dict.fromkeys([REALITY_SHORT_ID, 'abcd1234']))
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
                "connect_timeout": "5s",
                "up_mbps": 200,
                "down_mbps": 200
            },
            # AI-SOCKS5代理池 - 多代理自动容错切换
            # 从SOCKS5_POOL生成多个SOCKS5出站，ai-residential selector自动包含所有可用代理
        ] + ([{
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


def generate_clash_config():
    """生成Clash Meta (mihomo) 订阅配置（含url-test自动故障转移）
    
    ⚠️ Clash Meta v1.18.0+ 支持 VLESS-Reality 协议
    Clash Verge Rev 内置 mihomo 内核，完全支持所有协议
    配置自带url-test节点组，每60秒自动测速，断线3秒内自动切换
    """
    if CDN_MODE == 'domain_default':
        vless_ws_addr = CF_DOMAIN
        vless_upgrade_addr = CF_DOMAIN
        trojan_ws_addr = CF_DOMAIN
        use_cdn = bool(CF_DOMAIN and CF_DOMAIN.strip())
    elif CDN_MODE == 'domain_optimized':
        optimized_domain = get_cdn_optimized_domain()
        vless_ws_addr = optimized_domain or CF_DOMAIN
        vless_upgrade_addr = optimized_domain or CF_DOMAIN
        trojan_ws_addr = optimized_domain or CF_DOMAIN
        use_cdn = bool(optimized_domain or (CF_DOMAIN and CF_DOMAIN.strip()))
    else:
        vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
        vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
        trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
        use_cdn = (vless_ws_addr is not None and vless_ws_addr != SERVER_IP)
        if not vless_ws_addr or vless_ws_addr == SERVER_IP:
            vless_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not vless_upgrade_addr or vless_upgrade_addr == SERVER_IP:
            vless_upgrade_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP
        if not trojan_ws_addr or trojan_ws_addr == SERVER_IP:
            trojan_ws_addr = CF_DOMAIN if CF_DOMAIN else SERVER_IP

    cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP

    proxies = []
    
    # 1. VLESS-Reality (直连) - Clash Meta v1.18.0+ 支持
    proxies.append({
        "name": f"{COUNTRY_CODE}-VLESS-Reality",
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
    
    # 2. VLESS-WS (CDN) - Clash Meta支持
    proxies.append({
        "name": f"{COUNTRY_CODE}-VLESS-WS",
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
        "servername": cdn_sni,
        "ws-opts": {
            "path": "/vless-ws",
            "headers": {"Host": cdn_sni},
            "ping-interval": 90
        },
        "client-fingerprint": "chrome",
        "skip-cert-verify": True
    })
    
    # 3. VLESS-HTTPUpgrade (CDN) - Clash Meta通过ws-opts.v2ray-http-upgrade启用
    proxies.append({
        "name": f"{COUNTRY_CODE}-VLESS-HTTPUpgrade",
        "type": "vless",
        "server": vless_upgrade_addr,
        "port": VLESS_UPGRADE_PORT,
        "uuid": VLESS_WS_UUID,
        "tls": True,
        "udp": True,
        "network": "ws",
        "multiplex": {
            "enabled": False
        },
        "servername": cdn_sni,
        "ws-opts": {
            "path": "/vless-upgrade",
            "headers": {"Host": cdn_sni},
            "ping-interval": 90,
            "v2ray-http-upgrade": True
        },
        "client-fingerprint": "chrome",
        "skip-cert-verify": True
    })
    
    # 4. Trojan-WS (CDN) - Clash Meta支持
    proxies.append({
        "name": f"{COUNTRY_CODE}-Trojan-WS",
        "type": "trojan",
        "server": trojan_ws_addr,
        "port": TROJAN_WS_PORT,
        "password": TROJAN_PASSWORD,
        "udp": True,
        "network": "ws",
        "multiplex": {
            "enabled": False
        },
        "sni": cdn_sni,
        "ws-opts": {
            "path": "/trojan-ws",
            "headers": {"Host": cdn_sni},
            "ping-interval": 90
        },
        "client-fingerprint": "chrome",
        "skip-cert-verify": True,
        "alpn": ["h2", "http/1.1"]
    })
    
    # 5. Hysteria2 (直连) - Clash Meta支持
    proxies.append({
        "name": f"{COUNTRY_CODE}-Hysteria2",
        "type": "hysteria2",
        "server": SERVER_IP,
        "port": 443,
        "password": HYSTERIA2_PASSWORD,
        "udp": True,
        "sni": REALITY_SNI,
        "skip-cert-verify": True,
        "ports": "443,21000-21200",
        "up": 200,
        "down": 200
    })
    
    proxy_names = [p["name"] for p in proxies]
    auto_proxy_names = [
        f"{COUNTRY_CODE}-VLESS-WS",
        f"{COUNTRY_CODE}-VLESS-HTTPUpgrade",
        f"{COUNTRY_CODE}-Trojan-WS",
    ]
    
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
            <div class="sub-box" id="cdn-test-section">
                <p><strong>CDN延时测试：</strong></p>
                <button onclick="runCdnTest()" style="padding:10px 20px;font-size:16px;background:#0066cc;color:white;border:none;border-radius:5px;cursor:pointer;">开始测速</button>
                <div id="cdn-test-result" style="margin-top:15px;"></div>
            </div>
            <script>
            async function runCdnTest() {{
                const resultDiv = document.getElementById('cdn-test-result');
                const btn = event.target;
                btn.disabled = true;
                btn.textContent = '测试中...';
                resultDiv.innerHTML = '<p style="color:#666;">正在获取CDN IP列表...</p>';
                try {{
                    const resp = await fetch('/api/cdn-test');
                    const data = await resp.json();
                    if (data.code !== 200 || !data.data.ips.length) {{
                        resultDiv.innerHTML = '<p style="color:red;">无可用CDN IP</p>';
                        btn.disabled = false;
                        btn.textContent = '开始测速';
                        return;
                    }}
                    const ips = data.data.ips;
                    resultDiv.innerHTML = '<p style="color:#666;">正在测试 ' + ips.length + ' 个CDN IP...</p>';
                    const results = [];
                    for (const ip of ips) {{
                        const start = performance.now();
                        let ok = false;
                        try {{
                            await fetch('https://' + ip + '/', {{
                                method: 'HEAD', mode: 'no-cors',
                                signal: AbortSignal.timeout(5000)
                            }});
                            ok = true;
                        }} catch(e) {{ ok = false; }}
                        const latency = Math.round(performance.now() - start);
                        results.push({{ip: ip, latency: latency, ok: ok}});
                    }}
                    results.sort((a, b) => a.latency - b.latency);
                    let html = '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
                    html += '<tr style="background:#e8f4fd;"><th style="padding:6px;border:1px solid #ddd;">IP</th><th style="padding:6px;border:1px solid #ddd;">延时</th><th style="padding:6px;border:1px solid #ddd;">状态</th></tr>';
                    for (const r of results) {{
                        const color = r.ok ? (r.latency < 200 ? 'green' : 'orange') : 'red';
                        html += '<tr><td style="padding:4px;border:1px solid #ddd;">' + r.ip + '</td>';
                        html += '<td style="padding:4px;border:1px solid #ddd;color:' + color + ';">' + (r.ok ? r.latency + 'ms' : '超时') + '</td>';
                        html += '<td style="padding:4px;border:1px solid #ddd;color:' + color + ';">' + (r.ok ? '可用' : '不可用') + '</td></tr>';
                    }}
                    html += '</table>';
                    // 回传结果到服务器
                    try {{
                        await fetch('/api/cdn-test', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify(results)
                        }});
                    }} catch(e) {{}}
                    resultDiv.innerHTML = html;
                }} catch(e) {{
                    resultDiv.innerHTML = '<p style="color:red;">测试失败: ' + e.message + '</p>';
                }}
                btn.disabled = false;
                btn.textContent = '开始测速';
            }}
            </script>
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
    @app.route(f'/sub/{COUNTRY_CODE.lower()}')
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
        traffic = get_traffic_stats()
        total_bytes = 900 * 1024 * 1024 * 1024  # 900GB 月流量套餐
        userinfo = f"upload=0; download={traffic['bytes_used']}; total={total_bytes}; expire=0"
        return Response(sub_b64, mimetype='text/plain',
                        headers={'subscription-userinfo': userinfo})

    @app.route(f'/singbox/{COUNTRY_CODE}')
    @app.route(f'/singbox/{COUNTRY_CODE.lower()}')
    @app.route('/singbox')
    def get_singbox_config():
        """完整sing-box JSON配置（含自动路由规则）
        ⚠️ 禁止加token认证！同/sub路由，直接访问。
        """
        config = generate_singbox_config()
        config_json = json.dumps(config, indent=2, ensure_ascii=False)
        traffic = get_traffic_stats()
        total_bytes = 900 * 1024 * 1024 * 1024  # 900GB 月流量套餐
        userinfo = f"upload=0; download={traffic['bytes_used']}; total={total_bytes}; expire=0"
        return Response(
            config_json,
            mimetype='application/json; charset=utf-8',
            headers={
                'Content-Disposition': 'attachment; filename=singbox-config.json',
                'subscription-userinfo': userinfo
            }
        )

    @app.route(f'/clash/{COUNTRY_CODE}')
    @app.route(f'/clash/{COUNTRY_CODE.lower()}')
    @app.route('/clash')
    def get_clash_config():
        """Clash Meta (mihomo) 订阅配置（含url-test自动故障转移）
        ⚠️ 禁止加token认证！同/sub路由，直接访问。
        ⚠️ Clash Meta v1.18.0+ 支持 Reality 协议
        """
        import yaml
        config = generate_clash_config()
        config_yaml = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
        traffic = get_traffic_stats()
        bytes_used = traffic['bytes_used']
        total_bytes = 900 * 1024 * 1024 * 1024  # 900GB 月流量套餐
        userinfo = f"upload=0; download={bytes_used}; total={total_bytes}; expire=0"
        sub_name = f"{get_country_name()}订阅.yaml"
        return Response(
            config_yaml,
            mimetype='text/plain; charset=utf-8',
            headers={
                'subscription-userinfo': userinfo
            }
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
        nonlocal _failover_controller, _health_monitor

        conn = None
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # 获取各协议当前CDN IP
            protocols = {
                'vless-ws': 'vless_ws_cdn_ip',
                'vless-httpupgrade': 'vless_upgrade_cdn_ip',
                'trojan-ws': 'trojan_ws_cdn_ip',
            }
            current_ips = {}
            for name, key in protocols.items():
                cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (key,))
                row = cursor.fetchone()
                current_ips[name] = row[0] if row else None

            # 获取IP池
            cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
            row = cursor.fetchone()
            pool = parse_cdn_ips_list(row[0]) if row and row[0] else []

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

            # 故障切换控制器状态
            failover_status = None
            if _failover_controller:
                failover_status = _failover_controller.get_status()

            # 冷却池IP
            cooldown_ips = [c['ip'] for c in failover_status['cooldown_pool']] if failover_status else []

            return jsonify({
                'code': 200,
                'data': {
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
