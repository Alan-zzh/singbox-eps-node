#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v3.1.3
Date: 2026-05-01
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

# ============================================================
# SOCKS5 代理池 + 健康检测 + 自动容错切换
# 每次生成订阅时检测所有代理，自动剔除不可用的
# 如果全部不可用，AI路由降级为普通代理（ePS-Auto）
# ============================================================
SOCKS5_POOL = []  # 可用代理列表，每个元素为dict: {server, port, user, pass}

def parse_socks5_pool():
    """解析代理池配置，返回代理列表"""
    pool_str = os.getenv('AI_SOCKS5_POOL', '')
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

def setup_iptables_traffic_counters():
    """配置iptables流量计数器（sing-box各入站端口）
    这是S-UI和机场面板的标准做法：
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

def test_cdn_ip_connectivity(ip, port=443, timeout=3):
    """测试CDN IP连通性（快速TCP测试）
    【Bug #57修复】：增加纠错机制，CDN IP连不上时自动回退到域名
    """
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        return result == 0
    except Exception:
        return False
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

def get_cdn_ip_for_protocol(protocol_key):
    """获取指定协议的CDN优选IP（带连通性检测兜底）
    
    【Bug #57修复】：
    1. 从数据库读取CDN IP
    2. 快速测试连通性（3秒超时）
    3. 连不上就清空数据库记录，自动回退到域名兜底
    4. 用户更新订阅即可恢复连接
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (protocol_key,))
        row = cursor.fetchone()
        if row and row[0] and row[0] != SERVER_IP:
            cdn_ip = row[0]
            # 快速连通性检测
            if test_cdn_ip_connectivity(cdn_ip):
                return cdn_ip
            else:
                # CDN IP连不上，清空数据库记录，触发兜底
                logger.warning(f"CDN IP {cdn_ip} 连通性检测失败，清空记录回退到域名")
                cursor.execute("DELETE FROM cdn_settings WHERE key=?", (protocol_key,))
                conn.commit()
    except Exception as e:
        logger.debug(f"获取CDN IP失败: {e}")
    finally:
        if conn:
            conn.close()
    # 兜底：使用域名
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
                # 故障转移：所有SOCKS5不可用时自动fallback到direct
                "type": "selector",
                "tag": "ai-residential",
                "outbounds": [f"AI-SOCKS5-{i+1}" for i in range(len(SOCKS5_POOL))] + ["direct"],
                "default": "AI-SOCKS5-1"
            }] if SOCKS5_POOL else []) + [
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
            } for i, proxy in enumerate(SOCKS5_POOL)]) + [
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
        traffic = get_traffic_stats()
        userinfo = f"upload=0; download={traffic['bytes_used']}; total=-1; expire=0"
        return Response(sub_b64, mimetype='text/plain',
                        headers={'subscription-userinfo': userinfo})

    @app.route(f'/singbox/{COUNTRY_CODE}')
    @app.route('/singbox')
    def get_singbox_config():
        """完整sing-box JSON配置（含自动路由规则）
        ⚠️ 禁止加token认证！同/sub路由，直接访问。
        """
        config = generate_singbox_config()
        config_json = json.dumps(config, indent=2, ensure_ascii=False)
        traffic = get_traffic_stats()
        userinfo = f"upload=0; download={traffic['bytes_used']}; total=-1; expire=0"
        return Response(
            config_json,
            mimetype='application/json',
            headers={
                'Content-Disposition': 'attachment; filename=singbox-config.json',
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
    app.run(host='0.0.0.0', port=SUB_PORT, threaded=True,
            ssl_context=(cert_chain, cert_key))