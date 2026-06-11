#!/usr/bin/env python3
"""
Singbox CDN优选IP学习系统
Author: Alan
Version: v4.10.18
Date: 2026-06-01

架构设计：用户投喂 + 自动验证 + 历史评分 = 持续优化的CDN优选系统

v4.1.0 存活优先模式（用户反馈驱动）：
  1. 检查数据库现有CDN IP，逐个TCP存活检测
  2. 存活的IP保留，死亡的IP才替换
  3. 收集候选IP（用户投喂+外部API）
  4. 从候选池挑存活IP补上死亡空缺
  5. 只对新增候选IP做HTTP测试记录评分

v4.0 用户反馈驱动版：
  1. 用户投喂=真理来源，外部API仅补充
  2. 只测TCP存活，不测延迟（服务器延迟≠用户体验）
  3. 用户IP优先，外部IP备胎

v3.1.4 性能优化（资源消耗降低90%+）：
  1. 历史评分为主：已有历史数据的IP（>=3次测试）直接复用评分，不再重复测试
  2. 新IP轻量验证：只对历史数据不足的新IP做快速测试（1次TCP+1次HTTP）
  3. 一键安装不影响：安装脚本只启动服务，CDN测试在后台异步运行
  4. 从110个IP全量测试（550次HTTP）→ 只测新IP（通常<20次测试）

v3.1.3 修复清单：
  1. 淘汰IP过滤：被淘汰IP不再入选TOP5（之前只标记不过滤）
  2. http_latency_test() socket泄漏修复：异常路径正确关闭连接
  3. ImportError降级块移除104段IP（违反Bug #35教训）
  4. assign_and_save_ips()数据库连接加try/finally（违反Bug #38铁律）
  5. init_db() ImportError降级时DATA_DIR未定义导致NameError
  6. ip_test_history表自动清理（保留最近7天），防止数据库无限膨胀
  7. should_eliminate_ip()修复last_success_time为None时的逻辑
  8. 清理死代码：tcping()/SOURCE_WEIGHT/parse_speed()
  9. 日志和注释修正：TCP→HTTP

v3.0 核心特性：
  1. IP性能数据库：每个IP独立记录历史延迟/成功率/连续失败次数
  2. 综合评分算法：平均延迟40% + 成功率30% + 稳定性20% + 新鲜度10%
  3. 自动淘汰机制：连续5次失败降权，连续3天不达标移出优选池
  4. 用户投喂通道：config.py的IP作为"候选池"，脚本自动验证后入库
  5. 不依赖IP段前缀：完全基于历史表现数据，越用越准

工作流：
  每小时执行 → 从候选池+外部API收集IP → 历史评分复用+新IP快速测试 → 综合评分 → 选最优5个

历史版本：
  - v2.0.0: 多源聚合+评分排序（理论优选≠实际最优）
  - v2.2.0: TCP连通测试+本地池优先（解决服务器端测试无意义问题）
  - v3.0.0: 学习系统+自动淘汰（持续优化，越用越准）
  - v3.1.2: HTTP真实延迟测试+CDN纠错机制
  - v3.1.3: 全面问题修复与风险排查
  - v3.1.4: 历史评分为主+新IP轻量验证（性能优化90%+）
"""

import os
import sys
import time
import sqlite3
import json
import socket
import ssl
import subprocess
import re
import fcntl
import random
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN, SUB_PORT,
        CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT,
        CDN_PREFERRED_IPS, CDN_IP_BLACKLIST,
        CDN_API_WETEST_CT, CDN_API_IPDB,
        CDN_API_001315_CT, CDN_API_001315_CU, CDN_API_001315_CMCC,
        CDN_API_090227_CT, CDN_API_090227_CU, CDN_API_090227_CMCC,
        CDN_API_VVHAN,
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT,
        CDN_CUSTOM_SOURCE_URLS, CDN_FASTEST_LIMIT, CDN_REGION_FILTER,
        USER_DDNS_DOMAIN, USER_EXPECTED_ISP, USER_PROBE_INTERVAL,
        USER_LATENCY_SPIKE_THRESHOLD, HUNAN_CT_OPTIMAL_PREFIXES,
        CDN_IP_HARD_REJECT, USER_QUALITY_THRESHOLD,
        CDN_MODE, CDN_OPTIMIZED_DOMAINS, CDN_DOMAIN_TEST_URL,
        THREE_ISP_OPTIMAL_PREFIXES,
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)
    SERVER_IP = ''
    CF_DOMAIN = ''
    SUB_PORT = 2087
    VLESS_WS_PORT = 8443
    VLESS_UPGRADE_PORT = 2053
    TROJAN_WS_PORT = 2083
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    CDN_PREFERRED_IPS = [
        '162.159.38.161', '108.162.198.221', '162.159.44.242',
        '172.64.52.35', '172.64.53.231', '172.64.229.110',
        '162.159.39.14', '172.64.41.181', '172.64.34.89',
        '172.64.229.250', '162.159.13.213', '162.159.5.56',
    ]
    CDN_IP_BLACKLIST = []
    CDN_API_WETEST_CT = 'ct.cloudflare.182682.xyz'
    CDN_API_IPDB = 'https://ipdb.api.030101.xyz/?type=bestcf'
    CDN_API_001315_CT = 'https://cf.001315.xyz/ct'
    CDN_API_001315_CU = 'https://cf.001315.xyz/cu'
    CDN_API_001315_CMCC = 'https://cf.001315.xyz/cmcc'
    CDN_API_090227_CT = 'https://addressesapi.090227.xyz/ct'
    CDN_API_090227_CU = 'https://addressesapi.090227.xyz/cu'
    CDN_API_090227_CMCC = 'https://addressesapi.090227.xyz/cmcc'
    CDN_API_VVHAN = 'https://api.vvhan.com/tool/cf_ip'
    CDN_MONITOR_INTERVAL = 3600
    CDN_TOP_IPS_COUNT = 5
    CDN_CUSTOM_SOURCE_URLS = ''
    CDN_FASTEST_LIMIT = 10
    CDN_REGION_FILTER = ''
    USER_DDNS_DOMAIN = ''
    USER_EXPECTED_ISP = '电信'
    USER_PROBE_INTERVAL = 300
    USER_LATENCY_SPIKE_THRESHOLD = 0.5
    HUNAN_CT_OPTIMAL_PREFIXES = ['162.159.', '172.64.', '108.162.', '198.41.', '173.245.', '8.39.', '8.41.', '8.43.']
    CDN_IP_HARD_REJECT = {'latency_ms': 100, 'user_path_latency_ms': 100, 'packet_loss_rate': 0.1, 'download_speed_mbps': 20}
    USER_QUALITY_THRESHOLD = {'latency_ms': 100, 'packet_loss_rate': 0.05, 'download_speed_mbps': 20}
    CDN_MODE = 'ip_optimized'
    CDN_OPTIMIZED_DOMAINS = []
    CDN_DOMAIN_TEST_URL = 'https://speed.cloudflare.com/__down?bytes=10000000'

logger = get_logger('cdn_monitor')

# 随机User-Agent列表（降低被CF识别为自动化爬虫的风险）
RANDOM_USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
]

# 随机请求路径列表
RANDOM_TEST_PATHS = ['/', '/favicon.ico', '/robots.txt', '/sitemap.xml', '/.well-known/security.txt']

DNS_SERVER = '222.246.129.80'
DNS_SERVER_BACKUP = '59.51.78.210'
DOH_SERVERS = [
    'https://dns.alidns.com/resolve',
    'https://doh.pub/dns-query',
]

IPDB_API_URL = CDN_API_IPDB

# [TRAE SOLO CN] v4.10.16 用户路径优先评分权重
SCORE_VPS_CDN_WEIGHT = 0.10
SCORE_VPS_SPEED_WEIGHT = 0.10
SCORE_USER_PATH_LAT_WEIGHT = 0.35
SCORE_USER_PATH_SPEED_WEIGHT = 0.35
SCORE_CROSS_ISP_WEIGHT = 0.05
SCORE_STABILITY_WEIGHT = 0.05
SCORE_VPS_CDN_WEIGHT_FALLBACK = 0.25
SCORE_VPS_SPEED_WEIGHT_FALLBACK = 0.25
SCORE_CROSS_ISP_WEIGHT_FALLBACK = 0.20
SCORE_STABILITY_WEIGHT_FALLBACK = 0.30
CROSS_ISP_TELECOM_WEIGHT = 0.45
CROSS_ISP_UNICOM_WEIGHT = 0.35
CROSS_ISP_MOBILE_WEIGHT = 0.20

# [TRAE SOLO CN] v4.10.6 三网API IP缓存（fetch_cdn_ips时填充）
_three_isp_cache = {}

# 淘汰阈值
ELIMINATE_CONSECUTIVE_FAILS = 5       # 连续失败次数
ELIMINATE_DAYS_NO_SUCCESS = 3         # 连续多少天无成功记录


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = os.path.join(DATA_DIR, 'singbox.db')
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cdn_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # v3.0 新增：IP性能历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ip_performance (
                ip TEXT PRIMARY KEY,
                total_tests INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                consecutive_fails INTEGER DEFAULT 0,
                avg_latency REAL DEFAULT 0,
                min_latency REAL DEFAULT 9999,
                max_latency REAL DEFAULT 0,
                last_test_time TEXT,
                last_success_time TEXT,
                first_seen TEXT,
                source TEXT DEFAULT 'unknown',
                speed_mbps REAL DEFAULT 0.0
            )
        """)
        # v4.4 兼容：为旧表添加 speed_mbps 列
        try:
            cursor.execute("ALTER TABLE ip_performance ADD COLUMN speed_mbps REAL DEFAULT 0.0")
        except Exception:
            pass  # 列已存在，忽略
        # v4.10.20 评分维度精简：只保留 user_isp_match + composite_score_v2
        # google_latency_ms / google_speed_mbps 已废弃（数值永远 0，无评分贡献）
        for col_sql in [
            "ALTER TABLE ip_performance ADD COLUMN user_isp_match REAL DEFAULT 0",
            "ALTER TABLE ip_performance ADD COLUMN composite_score_v2 REAL DEFAULT 0",
        ]:
            try:
                cursor.execute(col_sql)
            except Exception:
                pass
        # v4.10.20 一次性 DROP 废弃列（SQLite 3.35+ 支持）
        for drop_sql in [
            "ALTER TABLE ip_performance DROP COLUMN google_latency_ms",
            "ALTER TABLE ip_performance DROP COLUMN google_speed_mbps",
        ]:
            try:
                cursor.execute(drop_sql)
            except Exception:
                pass  # 列不存在或 SQLite 版本太低，忽略
        # v4.10.20 切换到 WAL 模式（多进程并发零阻塞）
        try:
            cursor.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        # v3.0 新增：每次测试的详细记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ip_test_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                latency REAL,
                success INTEGER,
                test_time TEXT NOT NULL
            )
        """)
        # v4.5 新增：用户网络状态表（DDNS锚点探测结果）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_network_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT (datetime('now', 'localtime')),
                user_ip TEXT,
                user_isp TEXT,
                user_region TEXT,
                latency_ms REAL,
                http_latency_ms REAL,
                download_speed_mbps REAL,
                packet_loss_rate REAL,
                ip_changed INTEGER DEFAULT 0,
                latency_spike INTEGER DEFAULT 0,
                quality_ok INTEGER DEFAULT 1
            )
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()
    return db_path


def probe_user_network(db_path):
    """
    v4.5 用户网络探测：通过DDNS域名实测VPS→用户全链路质量
    解析DDNS域名获取用户IP，测延时/丢包/速度，检测网络波动
    返回: dict 或 None（DDNS未配置时）
    """
    if not USER_DDNS_DOMAIN:
        return None

    logger.info(f">>> 用户网络探测: {USER_DDNS_DOMAIN}")

    # 1. 解析DDNS域名获取用户IP
    user_ips = resolve_dns(USER_DDNS_DOMAIN)
    if not user_ips:
        logger.warning(f"  DDNS域名 {USER_DDNS_DOMAIN} 解析失败")
        return None
    user_ip = user_ips[0]
    logger.info(f"  DDNS解析: {USER_DDNS_DOMAIN} → {user_ip}")

    # 2. IP变更检测
    last_user_ip = None
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT user_ip FROM user_network_state ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            last_user_ip = row[0]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    ip_changed = (last_user_ip is not None and last_user_ip != user_ip)
    if ip_changed:
        logger.info(f"  用户IP变更: {last_user_ip} → {user_ip}")

    # 3. IP归属地查询（IP变更时查询，否则复用上次结果）
    user_isp = ''
    user_region = ''
    if ip_changed or not last_user_ip:
        try:
            api_url = f"http://ip-api.com/json/{user_ip}?lang=zh-CN"
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                geo_data = json.loads(resp.read().decode())
                user_isp = geo_data.get('isp', '')
                user_region = geo_data.get('regionName', '')
                logger.info(f"  归属地: {user_region} / {user_isp}")
        except Exception as e:
            logger.debug(f"  IP归属地查询失败: {e}")
            # 复用上次结果
            conn2 = None
            try:
                conn2 = sqlite3.connect(db_path)
                cursor2 = conn2.cursor()
                cursor2.execute("SELECT user_isp, user_region FROM user_network_state WHERE user_isp != '' ORDER BY id DESC LIMIT 1")
                row2 = cursor2.fetchone()
                if row2:
                    user_isp, user_region = row2[0], row2[1]
            except Exception:
                pass
            finally:
                if conn2:
                    conn2.close()
    else:
        # IP未变，复用上次归属地
        conn3 = None
        try:
            conn3 = sqlite3.connect(db_path)
            cursor3 = conn3.cursor()
            cursor3.execute("SELECT user_isp, user_region FROM user_network_state WHERE user_isp != '' ORDER BY id DESC LIMIT 1")
            row3 = cursor3.fetchone()
            if row3:
                user_isp, user_region = row3[0], row3[1]
        except Exception:
            pass
        finally:
            if conn3:
                conn3.close()

    # 4. 延时探测：TCP 443优先，不通则ICMP ping，都不通则CDN回源
    # [TRAE SOLO CN] v4.10.6 用户IP可ping通但无443服务，用ICMP代替TCP
    latencies = []
    use_icmp = False
    packet_loss_rate = 0.0
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(3)
        start = time.time()
        test_sock.connect((user_ip, 443))
        elapsed = (time.time() - start) * 1000
        test_sock.close()
        latencies.append(elapsed)
        for i in range(2):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                start = time.time()
                sock.connect((user_ip, 443))
                elapsed = (time.time() - start) * 1000
                latencies.append(elapsed)
                sock.close()
            except Exception:
                pass
            time.sleep(0.5)
        avg_latency = sum(latencies) / len(latencies) if latencies else 9999
        logger.info(f"  TCP延时: {avg_latency:.1f}ms (3次平均)")
    except Exception:
        avg_latency = 9999
        # TCP不通，尝试ICMP ping
        try:
            ping_result = subprocess.run(
                ['ping', '-c', '5', '-W', '3', user_ip],
                capture_output=True, text=True, timeout=20
            )
            if ping_result.returncode == 0:
                use_icmp = True
                time_match = re.search(r'rtt min/avg/max/mdev = [\d.]+/([\d.]+)/', ping_result.stdout)
                loss_match = re.search(r'(\d+)% packet loss', ping_result.stdout)
                if time_match:
                    avg_latency = float(time_match.group(1))
                if loss_match:
                    packet_loss_rate = int(loss_match.group(1)) / 100.0
                logger.info(f"  ICMP延时: {avg_latency:.1f}ms, 丢包: {packet_loss_rate*100:.0f}%")
            else:
                logger.info(f"  用户IP {user_ip} TCP和ICMP均不通，使用CDN回源测速代替")
        except Exception:
            logger.info(f"  用户IP {user_ip} 不可达，使用CDN回源测速代替")

    # 5. CDN回源全链路延时
    http_latency = None
    try:
        start = time.time()
        req = urllib.request.Request(
            f"https://{USER_DDNS_DOMAIN}/",
            headers={'User-Agent': random.choice(RANDOM_USER_AGENTS)}
        )
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            resp.read(1)
        http_latency = (time.time() - start) * 1000
        logger.info(f"  CDN回源延时: {http_latency:.1f}ms")
    except Exception as e:
        logger.debug(f"  CDN回源测试失败: {e}")

    # 6. 丢包率检测（TCP不通时用ICMP结果，ICMP也不通则跳过）
    if not use_icmp and avg_latency == 9999:
        packet_loss_rate = 0.0
        logger.info(f"  丢包率: N/A（不可达，跳过丢包检测）")
    elif not use_icmp:
        fail_count = 0
        for i in range(5):
            if not tcp_port_test(user_ip, 443, timeout=3):
                fail_count += 1
            time.sleep(0.3)
        packet_loss_rate = fail_count / 5
        logger.info(f"  丢包率: {packet_loss_rate*100:.0f}% ({fail_count}/5)")

    # 7. 质量达标判断
    quality_ok = True
    check_latency = avg_latency
    if avg_latency == 9999 and http_latency:
        check_latency = http_latency
    if use_icmp and avg_latency < 9999 and avg_latency > USER_QUALITY_THRESHOLD['latency_ms']:
        quality_ok = False
        logger.warning(f"  ⚠️ ICMP链路延时{avg_latency:.0f}ms超过阈值{USER_QUALITY_THRESHOLD['latency_ms']}ms")
    elif not use_icmp and avg_latency < 9999 and avg_latency > USER_QUALITY_THRESHOLD['latency_ms']:
        quality_ok = False
        logger.warning(f"  ⚠️ TCP延时{avg_latency:.0f}ms超过阈值{USER_QUALITY_THRESHOLD['latency_ms']}ms")
    elif avg_latency == 9999 and http_latency and http_latency > USER_QUALITY_THRESHOLD['latency_ms'] * 3:
        quality_ok = False
        logger.warning(f"  ⚠️ CDN回源延时{http_latency:.0f}ms超过阈值{USER_QUALITY_THRESHOLD['latency_ms']*3:.0f}ms")
    if avg_latency < 9999 and packet_loss_rate > USER_QUALITY_THRESHOLD['packet_loss_rate']:
        quality_ok = False
        logger.warning(f"  ⚠️ 丢包率{packet_loss_rate*100:.0f}%超过阈值{USER_QUALITY_THRESHOLD['packet_loss_rate']*100:.0f}%")

    # 8. 延时突增检测
    latency_spike = False
    if last_user_ip:  # 有历史数据才检测突增
        conn4 = None
        try:
            conn4 = sqlite3.connect(db_path)
            cursor4 = conn4.cursor()
            cursor4.execute("SELECT AVG(latency_ms) FROM user_network_state WHERE latency_ms > 0 AND latency_ms < 9999 ORDER BY id DESC LIMIT 10")
            row4 = cursor4.fetchone()
            if row4 and row4[0] and row4[0] > 0:
                hist_avg = row4[0]
                if avg_latency > hist_avg * (1 + USER_LATENCY_SPIKE_THRESHOLD):
                    latency_spike = True
                    logger.warning(f"  ⚠️ 延时突增: {avg_latency:.0f}ms > 历史均值{hist_avg:.0f}ms * {1+USER_LATENCY_SPIKE_THRESHOLD}")
        except Exception:
            pass
        finally:
            if conn4:
                conn4.close()

    # 9. 写入数据库
    result = {
        'ip': user_ip,
        'isp': user_isp,
        'region': user_region,
        'latency_ms': avg_latency,
        'http_latency_ms': http_latency,
        'packet_loss_rate': packet_loss_rate,
        'ip_changed': ip_changed,
        'latency_spike': latency_spike,
        'quality_ok': quality_ok,
    }

    conn5 = None
    try:
        conn5 = sqlite3.connect(db_path)
        cursor5 = conn5.cursor()
        cursor5.execute("""
            INSERT INTO user_network_state
            (user_ip, user_isp, user_region, latency_ms, http_latency_ms,
             packet_loss_rate, ip_changed, latency_spike, quality_ok)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_ip, user_isp, user_region, avg_latency, http_latency,
              packet_loss_rate, 1 if ip_changed else 0,
              1 if latency_spike else 0, 1 if quality_ok else 0))
        conn5.commit()
    except Exception as e:
        logger.debug(f"  保存用户网络状态失败: {e}")
    finally:
        if conn5:
            conn5.close()

    logger.info(f"  探测结果: 延时={avg_latency:.0f}ms 丢包={packet_loss_rate*100:.0f}% 质量={'达标' if quality_ok else '不达标'}")
    return result


def test_cdn_ip_via_user_path(cdn_ip, port=443, timeout=5):
    """
    v4.5 通过CDN IP测试完整链路质量
    VPS → CDN IP → 回源 → 返回，测完整链路延时
    返回: {'latency_ms': float, 'success': bool, 'status_code': str} 或 None
    """
    sni_host = CF_DOMAIN if CF_DOMAIN else 'cloudflare.com'
    sock = None
    ssock = None
    start_time = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((cdn_ip, port))

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssock = ctx.wrap_socket(sock, server_hostname=sni_host)

        request = f"GET / HTTP/1.1\r\nHost: {sni_host}\r\nUser-Agent: {random.choice(RANDOM_USER_AGENTS)}\r\nConnection: close\r\n\r\n"
        ssock.sendall(request.encode())

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            response += chunk

        elapsed = (time.time() - start_time) * 1000
        status_code = '000'
        if response:
            status_line = response.decode('utf-8', errors='ignore').split('\r\n')[0]
            parts = status_line.split()
            if len(parts) >= 2:
                status_code = parts[1]

        # 403/1020/1010 = Cloudflare拦截
        success = status_code not in ('403', '1020', '1010')
        return {'latency_ms': elapsed, 'success': success, 'status_code': status_code}
    except Exception as e:
        logger.debug(f"  CDN链路测试 {cdn_ip} 失败: {e}")
        return None
    finally:
        try:
            if ssock:
                ssock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def calculate_region_fitness(ip, user_isp, user_region):
    """
    v4.5 用户区域适配度评分
    根据用户位置和运营商评估CDN IP的适配度
    """
    if user_isp and '电信' in user_isp and user_region and '湖南' in user_region:
        for prefix in HUNAN_CT_OPTIMAL_PREFIXES:
            if ip.startswith(prefix):
                return 100
        if ip.startswith('104.'):
            return 20
        return 50
    return 50  # 未知用户位置，给中等分


def calculate_user_path_quality(ip, user_probe_result, db_path):
    """
    v4.5 用户链路质量评分
    综合考虑：VPS→用户延时、丢包率、下载速度
    返回 0-100 分
    """
    if not user_probe_result:
        return 50  # 无用户探测数据，给中等分

    latency = user_probe_result.get('latency_ms', 9999)
    packet_loss = user_probe_result.get('packet_loss_rate', 1.0)

    # 延时分
    if latency < 100:
        lat_score = 100
    elif latency < 200:
        lat_score = 80
    elif latency < 300:
        lat_score = 50
    else:
        lat_score = 0

    # 丢包分
    if packet_loss == 0:
        loss_score = 100
    elif packet_loss <= 0.05:
        loss_score = 80
    elif packet_loss <= 0.10:
        loss_score = 50
    elif packet_loss <= 0.20:
        loss_score = 20
    else:
        loss_score = 0

    # 区域适配度也影响链路质量评分
    region_score = calculate_region_fitness(ip, user_probe_result.get('isp', ''), user_probe_result.get('region', ''))

    # 综合 = 延时分*40% + 丢包分*30% + 区域适配*30%
    return round(lat_score * 0.4 + loss_score * 0.3 + region_score * 0.3, 2)


def hard_reject_cdn_ip(ip, user_probe_result, db_path):
    """
    v4.5 CDN IP硬淘汰检查
    不达标的IP直接淘汰，不进评分
    返回: (是否淘汰, 淘汰原因)
    """
    perf = get_ip_performance(db_path, ip)

    # VPS→CF延时检查
    if perf and perf['avg_latency'] > 0 and perf['avg_latency'] > CDN_IP_HARD_REJECT['latency_ms']:
        return True, f"VPS→CF延时{perf['avg_latency']:.0f}ms超过{CDN_IP_HARD_REJECT['latency_ms']}ms"

    # 丢包率检查（基于历史数据）
    if perf and perf['total_tests'] >= 5:
        fail_rate = perf['fail_count'] / perf['total_tests']
        if fail_rate > CDN_IP_HARD_REJECT['packet_loss_rate']:
            return True, f"失败率{fail_rate*100:.0f}%超过{CDN_IP_HARD_REJECT['packet_loss_rate']*100:.0f}%"

    # 速度检查（基于历史数据）
    if perf and perf.get('speed_mbps', 0) > 0 and perf['speed_mbps'] < CDN_IP_HARD_REJECT['download_speed_mbps']:
        return True, f"速度{perf['speed_mbps']:.1f}Mbps低于{CDN_IP_HARD_REJECT['download_speed_mbps']}Mbps"

    return False, ""


def record_ip_test(db_path, ip, latency, success, source='local'):
    """记录IP测试结果到数据库"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute(
            "INSERT INTO ip_test_history (ip, latency, success, test_time) VALUES (?, ?, ?, ?)",
            (ip, latency if success else None, 1 if success else 0, now)
        )

        cursor.execute("SELECT * FROM ip_performance WHERE ip = ?", (ip,))
        row = cursor.fetchone()

        if row:
            total = row[1] + 1
            success_cnt = row[2] + (1 if success else 0)
            fail_cnt = row[3] + (0 if success else 1)
            consec_fails = (row[4] + 1) if not success else 0
            old_avg = row[5]
            old_success_cnt = row[2]
            if success and latency is not None:
                new_avg = (old_avg * old_success_cnt + latency) / (old_success_cnt + 1)
            else:
                new_avg = old_avg
            min_lat = min(row[6], latency) if success and latency is not None else row[6]
            max_lat = max(row[7], latency) if success and latency is not None else row[7]
            last_success = now if success else row[9]

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
            """, (ip, 1 if success else 0, 0 if success else 1, 0 if success else 1,
                  latency if success else 0,
                  latency if success else 9999,
                  latency if success else 0,
                  now, now if success else None, now, source))

        conn.commit()
    finally:
        if conn:
            conn.close()


def get_ip_performance(db_path, ip):
    """获取IP的性能数据"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ip_performance WHERE ip = ?", (ip,))
        row = cursor.fetchone()
        if row:
            return {
                'ip': row[0],
                'total_tests': row[1],
                'success_count': row[2],
                'fail_count': row[3],
                'consecutive_fails': row[4],
                'avg_latency': row[5],
                'min_latency': row[6],
                'max_latency': row[7],
                'last_test_time': row[8],
                'last_success_time': row[9],
                'first_seen': row[10],
                'source': row[11],
                'speed_mbps': row[12] if len(row) > 12 else 0.0,
            }
        return None
    finally:
        if conn:
            conn.close()


def update_speed_mbps(db_path, ip, speed_mbps):
    """更新IP的下载速度到数据库"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE ip_performance SET speed_mbps=? WHERE ip=?", (speed_mbps, ip))
        conn.commit()
    except Exception as e:
        logger.debug(f"  更新速度数据失败 {ip}: {e}")
    finally:
        if conn:
            conn.close()


def calculate_cross_isp_score(ip):
    """
    [TRAE SOLO CN] v4.10.6 三网均衡度评分
    优先使用三网API缓存数据，降级使用前缀表匹配
    三网都优质→100, 两网→80, 单网→60, 都不在→50
    权重：电信0.45+联通0.35+移动0.20
    [TRAE SOLO CN] v4.10.18 增加C段前缀匹配，解决anycast IP精确匹配失败问题
    """
    ip_prefix = '.'.join(ip.split('.')[:3])
    if _three_isp_cache:
        matched_isps = []
        for isp_key, ip_set in _three_isp_cache.items():
            if ip in ip_set:
                matched_isps.append(isp_key)
                continue
            isp_prefixes = set('.'.join(i.split('.')[:3]) for i in ip_set)
            if ip_prefix in isp_prefixes:
                matched_isps.append(isp_key)
        if len(matched_isps) >= 3:
            base_score = 100
        elif len(matched_isps) == 2:
            base_score = 80
        elif len(matched_isps) == 1:
            base_score = 60
        else:
            base_score = 50
        if matched_isps:
            weighted = sum(
                (100 if k in matched_isps else 50) * w
                for k, w in [('telecom', CROSS_ISP_TELECOM_WEIGHT),
                             ('unicom', CROSS_ISP_UNICOM_WEIGHT),
                             ('mobile', CROSS_ISP_MOBILE_WEIGHT)]
            )
            return round(weighted, 2)
        return base_score
    if not THREE_ISP_OPTIMAL_PREFIXES:
        return 50
    scores = {}
    for isp_key, isp_info in THREE_ISP_OPTIMAL_PREFIXES.items():
        matched = any(ip.startswith(prefix) for prefix in isp_info.get('prefixes', []))
        scores[isp_key] = 100 if matched else 50
    return round(
        scores.get('telecom', 50) * CROSS_ISP_TELECOM_WEIGHT +
        scores.get('unicom', 50) * CROSS_ISP_UNICOM_WEIGHT +
        scores.get('mobile', 50) * CROSS_ISP_MOBILE_WEIGHT,
        2
    )


def calculate_composite_score(perf, current_latency=None, user_probe_result=None,
                             google_result=None, isp_type='unknown',
                             user_path_result=None, cross_isp_score=None):
    """
    [TRAE SOLO CN] v4.10.6 用户路径+三网均衡评分
    用户路径可用: VPS延迟(15%) + VPS速度(15%) + 用户路径延迟(25%) + 用户路径速度(25%) + 三网均衡(15%) + 稳定性(5%)
    用户路径不可用: VPS延迟(25%) + VPS速度(25%) + 三网均衡(30%) + 稳定性(20%)
    """
    if perf is None or perf['total_tests'] == 0:
        return 50.0

    total = perf['total_tests']
    success = perf['success_count']
    avg_lat = perf['avg_latency']
    consec_fails = perf['consecutive_fails']
    speed_mbps = perf.get('speed_mbps', 0.0) or 0.0

    # 1. VPS→CDN延迟评分
    if avg_lat > 0:
        vps_cdn_score = max(0, 100 * (1 - avg_lat / 500))
    else:
        vps_cdn_score = 50

    # 2. VPS→CDN速度评分
    if speed_mbps >= 50:
        vps_speed_score = 100
    elif speed_mbps >= 30:
        vps_speed_score = 80
    elif speed_mbps >= 10:
        vps_speed_score = 60
    elif speed_mbps >= 5:
        vps_speed_score = 40
    elif speed_mbps >= 1:
        vps_speed_score = 20
    elif speed_mbps > 0:
        vps_speed_score = 10
    else:
        vps_speed_score = 0

    # 3. 用户路径延迟评分
    user_path_lat_score = 0
    user_path_speed_score = 0
    has_user_path = False
    if user_path_result and isinstance(user_path_result, dict) and user_path_result.get('success'):
        has_user_path = True
        u_lat = user_path_result.get('latency_ms', 0)
        if u_lat > 0:
            if u_lat < 150:
                user_path_lat_score = 100
            elif u_lat < 250:
                user_path_lat_score = 80
            elif u_lat < 400:
                user_path_lat_score = 50
            elif u_lat < 600:
                user_path_lat_score = 20
            else:
                user_path_lat_score = 0
        u_spd = user_path_result.get('speed_mbps', 0) or 0
        if u_spd >= 50:
            user_path_speed_score = 100
        elif u_spd >= 30:
            user_path_speed_score = 80
        elif u_spd >= 10:
            user_path_speed_score = 60
        elif u_spd >= 5:
            user_path_speed_score = 40
        elif u_spd >= 1:
            user_path_speed_score = 20
        elif u_spd > 0:
            user_path_speed_score = 10

    # 4. 三网均衡度评分
    if cross_isp_score is not None:
        isp_balance_score = cross_isp_score
    else:
        isp_balance_score = 50

    # 5. 稳定性评分
    success_rate = success / total if total > 0 else 0
    success_score = success_rate * 100
    stability_score = max(0, 100 - consec_fails * 20)
    stability_total = success_score * 0.67 + stability_score * 0.33

    # 6. 综合评分
    if has_user_path:
        total_score = (
            vps_cdn_score * SCORE_VPS_CDN_WEIGHT +
            vps_speed_score * SCORE_VPS_SPEED_WEIGHT +
            user_path_lat_score * SCORE_USER_PATH_LAT_WEIGHT +
            user_path_speed_score * SCORE_USER_PATH_SPEED_WEIGHT +
            isp_balance_score * SCORE_CROSS_ISP_WEIGHT +
            stability_total * SCORE_STABILITY_WEIGHT
        )
    else:
        total_score = (
            vps_cdn_score * SCORE_VPS_CDN_WEIGHT_FALLBACK +
            vps_speed_score * SCORE_VPS_SPEED_WEIGHT_FALLBACK +
            isp_balance_score * SCORE_CROSS_ISP_WEIGHT_FALLBACK +
            stability_total * SCORE_STABILITY_WEIGHT_FALLBACK
        )

    return round(total_score, 2)


def should_eliminate_ip(perf):
    """判断IP是否应该被淘汰"""
    if perf is None:
        return False, "新IP，保留观察"

    if perf['consecutive_fails'] >= ELIMINATE_CONSECUTIVE_FAILS:
        return True, f"连续失败{perf['consecutive_fails']}次"

    if perf['total_tests'] >= 10:
        success_rate = perf['success_count'] / perf['total_tests']
        if success_rate < 0.2:
            return True, f"成功率仅{success_rate*100:.0f}%"

    if perf['last_success_time']:
        try:
            last_dt = datetime.fromisoformat(perf['last_success_time'])
            days_since = (datetime.now() - last_dt).days
            if days_since >= ELIMINATE_DAYS_NO_SUCCESS and perf['total_tests'] >= 5:
                return True, f"{days_since}天无成功记录"
        except Exception:
            pass
    else:
        if perf['total_tests'] >= 5 and perf['success_count'] == 0:
            return True, f"测试{perf['total_tests']}次从未成功"

    return False, "正常"


def tcp_port_test(ip, port, timeout=1):
    """快速TCP端口连通性测试（0.5-1秒）"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def tls_handshake_test(ip, port=443, timeout=3):
    """测试CDN IP的TLS握手是否成功
    【v4.7修复】[TRAE SOLO CN]：Cloudflare已启用SNI严格验证，TCP通但TLS失败视为不可用
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        ssock = ctx.wrap_socket(sock, server_hostname=CF_DOMAIN if CF_DOMAIN else 'cloudflare.com')
        ssock.close()
        return True
    except ssl.SSLError as e:
        if 'handshake failure' in str(e).lower() or 'sslv3 alert' in str(e).lower():
            logger.warning(f"  TLS握手失败 {ip}:{port} - Cloudflare SNI严格验证拒绝")
        else:
            logger.debug(f"  TLS握手失败 {ip}:{port}: {e}")
        return False
    except Exception as e:
        logger.debug(f"  TLS测试 {ip}:{port} 异常: {e}")
        return False


def test_domain_latency(domain, port=443, timeout=5):
    """测试优选域名的延迟和速度
    [TRAE SOLO CN] v4.8：优选域名模式测速
    返回: (延迟ms, 下载速度Mbps, 是否成功)
    """
    try:
        start = time.time()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((domain, port))
        ssock = ctx.wrap_socket(sock, server_hostname=CF_DOMAIN if CF_DOMAIN else domain)
        connect_time = (time.time() - start) * 1000
        ssock.close()
        speed_mbps = 0.0
        try:
            import urllib.request
            req = urllib.request.Request(CDN_DOMAIN_TEST_URL, headers={'Host': CF_DOMAIN} if CF_DOMAIN else {})
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
            dl_start = time.time()
            resp = opener.open(req, timeout=timeout)
            data = resp.read()
            dl_time = time.time() - dl_start
            if dl_time > 0 and len(data) > 0:
                speed_mbps = (len(data) * 8) / (dl_time * 1000000)
        except Exception:
            pass
        return connect_time, speed_mbps, True
    except Exception as e:
        logger.debug(f"  域名测速 {domain}:{port} 失败: {e}")
        return None, 0.0, False


def select_best_domain(domains, port=443):
    """
    [TRAE SOLO CN] v4.9：综合评分选最优域名
    评分 = 延迟(40%) + 速度(40%) + 可用性(20%)
    """
    results = []
    for domain in domains:
        latency, speed, ok = test_domain_latency(domain, port)
        if ok and latency is not None:
            lat_score = max(0, 100 * (1 - latency / 500))
            if speed >= 50:
                spd_score = 100
            elif speed >= 30:
                spd_score = 80
            elif speed >= 10:
                spd_score = 60
            elif speed >= 5:
                spd_score = 40
            elif speed >= 1:
                spd_score = 20
            elif speed > 0:
                spd_score = 10
            else:
                spd_score = 0
            avail_score = 100
            total_score = lat_score * 0.4 + spd_score * 0.4 + avail_score * 0.2
            results.append((domain, total_score, latency, speed))
            logger.info(f"  优选域名 {domain}: 延迟={latency:.1f}ms 速度={speed:.1f}Mbps 评分={total_score:.1f}")
        else:
            logger.debug(f"  优选域名 {domain}: 不可用")
    if not results:
        return None
    results.sort(key=lambda x: -x[1])
    best = results[0]
    logger.info(f"  最优域名: {best[0]} (评分={best[1]:.1f} 延迟={best[2]:.1f}ms 速度={best[3]:.1f}Mbps)")
    return best[0]


def test_user_path_latency(cdn_ip, port=443, timeout=10):
    """
    [TRAE SOLO CN] v4.10.17：通过CDN IP做完整HTTPS测速（延迟+速度+丢包）
    模拟CDN回源路径: TLS握手(SNI=CF_DOMAIN) + HTTP请求(Host=用户域名) + 下载速度
    返回: {
        'latency_ms': float,       # TLS握手+首字节延迟
        'speed_mbps': float,       # 真实下载速度
        'packet_loss_rate': float, # 丢包率(0-1)
        'success': bool
    } 或 None
    """
    sni_host = CF_DOMAIN if CF_DOMAIN else 'cloudflare.com'
    # [TRAE SOLO CN] v4.10.19 SNI=CF_DOMAIN 仅测TCP+TLS握手延迟，不发HTTP请求（CDN 443端口不提供HTTP服务）
    result = {'latency_ms': 0, 'speed_mbps': 0.0, 'packet_loss_rate': 0.0, 'success': False}

    fail_count = 0
    for i in range(5):
        if not tcp_port_test(cdn_ip, port, timeout=3):
            fail_count += 1
        time.sleep(0.2)
    result['packet_loss_rate'] = fail_count / 5

    sock = None
    ssock = None
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((cdn_ip, port))

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssock = ctx.wrap_socket(sock, server_hostname=sni_host)
        connect_time = (time.time() - start) * 1000
        result['latency_ms'] = connect_time
        result['success'] = True
        logger.debug(f"  CDN测速 {cdn_ip}: SNI={sni_host} TLS握手成功 {connect_time:.1f}ms")
    except ssl.SSLError as e:
        logger.debug(f"  CDN测速 {cdn_ip}: SSL握手失败 SNI={sni_host} 错误={e}")
        result['success'] = False
        return result
    except Exception:
        result['success'] = False
        return result
    finally:
        try:
            if ssock:
                ssock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass

    try:
        speed = tcp_speed_test(cdn_ip, port=port, timeout=timeout)
        result['speed_mbps'] = speed
    except Exception:
        pass

    return result


def test_google_path_latency(cdn_ip=None, port=443, timeout=10):
    """
    [TRAE SOLO CN] v4.9：通过CDN IP访问Google的真实测速
    测试CDN出口到Google的连通性和速度
    返回: {
        'latency_ms': float,
        'speed_mbps': float,
        'success': bool
    } 或 None
    """
    if not cdn_ip:
        return None

    sni_host = CF_DOMAIN if CF_DOMAIN else 'cloudflare.com'
    sock = None
    ssock = None
    result = {'latency_ms': 0, 'speed_mbps': 0.0, 'success': False}

    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((cdn_ip, port))

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssock = ctx.wrap_socket(sock, server_hostname=sni_host)

        request = (
            f"GET /generate_204 HTTP/1.1\r\n"
            f"Host: www.google.com\r\n"
            f"User-Agent: {random.choice(RANDOM_USER_AGENTS)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        ssock.sendall(request.encode())

        response = b""
        while b"\r\n\r\n" not in response:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            response += chunk

        elapsed = (time.time() - start) * 1000
        result['latency_ms'] = elapsed

        if response:
            status_line = response.decode('utf-8', errors='ignore').split('\r\n')[0]
            if '204' in status_line or '200' in status_line or '301' in status_line or '302' in status_line:
                result['success'] = True
            elif '403' in status_line or '1020' in status_line:
                result['success'] = False
            else:
                result['success'] = True
        else:
            result['success'] = False
    except Exception:
        return result
    finally:
        try:
            if ssock:
                ssock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass

    try:
        dl_start = time.time()
        sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock2.settimeout(timeout)
        sock2.connect((cdn_ip, port))
        ctx2 = ssl.create_default_context()
        ctx2.check_hostname = False
        ctx2.verify_mode = ssl.CERT_NONE
        ssock2 = ctx2.wrap_socket(sock2, server_hostname=sni_host)
        request2 = (
            f"GET /__down?bytes=1000000 HTTP/1.1\r\n"
            f"Host: speed.cloudflare.com\r\n"
            f"User-Agent: {random.choice(RANDOM_USER_AGENTS)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        ssock2.sendall(request2.encode())
        data = b""
        while True:
            try:
                chunk = ssock2.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > 1100000:
                    break
            except Exception:
                break
        dl_elapsed = time.time() - dl_start
        if dl_elapsed > 0 and len(data) > 1000:
            body_start = data.find(b'\r\n\r\n')
            body = data[body_start+4:] if body_start > 0 else data
            result['speed_mbps'] = round((len(body) * 8) / (dl_elapsed * 1000000), 2)
        try:
            ssock2.close()
        except Exception:
            pass
        try:
            sock2.close()
        except Exception:
            pass
    except Exception:
        pass

    return result


def http_latency_test(ip, port=443, timeout=5, test_url=None):
    """
    用HTTPS请求测试IP真实延迟（模拟客户端实际连接）
    返回: (延迟ms, 是否成功) 或 (None, False) 如果失败
    
    【Bug #57修复】：之前只做TCP连接测试，无法反映对中国用户的真实链路质量
    现在发送真实HTTPS请求，测量完整握手+响应时间
    【v3.1.3修复】：异常路径正确关闭socket，防止资源泄漏
    【v4.3.8优化】：只记录403状态用于换IP参考，不淘汰被拦截IP
    """
    sni_host = CF_DOMAIN if CF_DOMAIN else 'cloudflare.com'
    if test_url is None:
        test_url = random.choice(RANDOM_TEST_PATHS)
    ua = random.choice(RANDOM_USER_AGENTS)
    sock = None
    ssock = None
    start_time = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        ssock = ctx.wrap_socket(sock, server_hostname=sni_host)
        
        request = f"GET {test_url} HTTP/1.1\r\nHost: {sni_host}\r\nUser-Agent: {ua}\r\nConnection: close\r\n\r\n"
        ssock.sendall(request.encode())
        
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = ssock.recv(4096)
            if not chunk:
                break
            response += chunk
        
        elapsed = (time.time() - start_time) * 1000
        
        if response:
            status_line = response.decode('utf-8', errors='ignore').split('\r\n')[0]
            status_code = status_line.split()[1] if len(status_line.split()) >= 2 else '000'
            
            # 403/1020/1010 说明已经成功连到 Cloudflare 边缘并收到 HTTP 响应。
            # 对当前项目的 CDN 候选探测来说，这种状态不能再被当成“IP 死亡”，
            # 否则会把大量其实可达的候选全部错杀，导致候选池清空、体感上像“CDN 全断”。
            # 这里保留日志，但视为“可连通、可继续参与排序”，把真正的淘汰交给后续
            # 用户路径测速和硬淘汰规则去做，而不是在 HTTP 状态码这一层提前清零。
            if status_code in ('403', '1020', '1010'):
                logger.warning(f"  HTTP测试 {ip} 返回{status_code}，Cloudflare受限响应，保留为可达候选")
                return elapsed, True
        
        if response:
            status_line = response.decode('utf-8', errors='ignore').split('\r\n')[0]
            if '200' in status_line or '301' in status_line or '302' in status_line or '404' in status_line:
                return elapsed, True
        
        return elapsed, True
    except ssl.SSLError as e:
        if 'handshake failure' in str(e).lower() or 'sslv3 alert' in str(e).lower():
            logger.warning(f"  HTTP测试 {ip} TLS握手失败 - Cloudflare SNI严格验证拒绝")
        else:
            logger.debug(f"  HTTP测试 {ip} TLS错误: {e}")
        return None, False
    except Exception as e:
        logger.debug(f"  HTTP测试 {ip} 失败: {e}")
        return None, False
    finally:
        try:
            if ssock:
                ssock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def tcp_speed_test(ip, port=443, timeout=15):
    """TCP下载速度测试 - 通过CDN IP下载Cloudflare测速文件，返回速度(Mbps)
    [TRAE SOLO CN] v4.10：下载文件改为5MB，超时拉长到15秒，确保数据准确
    """
    sock = None
    ssock = None
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssock = ctx.wrap_socket(sock, server_hostname='speed.cloudflare.com')

        request = (
            f"GET /__down?bytes=5000000 HTTP/1.1\r\n"
            f"Host: speed.cloudflare.com\r\n"
            f"User-Agent: Mozilla/5.0\r\n"
            f"Connection: close\r\n\r\n"
        )
        ssock.sendall(request.encode())

        downloaded = 0
        in_body = False
        while True:
            try:
                chunk = ssock.recv(65536)
                if not chunk:
                    break
                if not in_body:
                    header_end = chunk.find(b'\r\n\r\n')
                    if header_end >= 0:
                        chunk = chunk[header_end+4:]
                        in_body = True
                    else:
                        continue
                downloaded += len(chunk)
                if downloaded >= 5000000:
                    break
            except Exception:
                break

        elapsed = time.time() - start_time
        if elapsed <= 0 or downloaded < 1000:
            return 0.0

        speed_mbps = (downloaded * 8) / (elapsed * 1000000)
        return round(speed_mbps, 2)
    except Exception:
        return 0.0
    finally:
        try:
            if ssock:
                ssock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def resolve_dns(dns_name, dns_server=DNS_SERVER, timeout=10):
    ips = []

    for doh_url in DOH_SERVERS:
        try:
            url = f"{doh_url}?name={dns_name}&type=A"
            req = urllib.request.Request(url, headers={
                'Accept': 'application/dns-json',
                'User-Agent': 'Mozilla/5.0'
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
                for answer in data.get('Answer', []):
                    ip = answer.get('data', '')
                    if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                        ips.append(ip)
            if ips:
                logger.info(f"  DoH解析 {dns_name} @ {doh_url}: {ips}")
                return ips
        except Exception as e:
            logger.debug(f"  DoH {doh_url} 失败: {e}")
            continue

    try:
        result = subprocess.run(
            ['dig', '+short', dns_name, f'@{dns_server}', '+time=5'],
            capture_output=True, text=True, timeout=timeout
        )
        for line in result.stdout.strip().split('\n'):
            ip = line.strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        return ips
    except Exception as e:
        logger.warning(f"  DNS解析 {dns_name} 失败: {e}")
        return []


def fetch_from_vvhan_ct():
    try:
        import urllib.request
        req = urllib.request.Request(CDN_API_VVHAN)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        if not data.get('success'):
            logger.warning("  vvhan API返回success=false")
            return []

        v4_data = data.get('data', {}).get('v4', {})
        ct_ips = v4_data.get('CT', [])

        if not ct_ips:
            logger.warning("  vvhan API电信列表为空")
            return []

        ips = []
        for item in ct_ips:
            ip = item.get('ip', '')
            latency = item.get('latency', 0)
            speed = item.get('speed', '0')
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append({
                    'ip': ip,
                    'latency': latency,
                    'speed': speed,
                })

        if ips:
            logger.info(f"  vvhan电信API返回 {len(ips)} 个IP(含延迟数据): {[i['ip'] for i in ips[:5]]}")
        else:
            logger.warning("  vvhan API解析后无有效IP")
        return ips
    except Exception as e:
        logger.warning(f"  vvhan电信API获取失败: {e}")
        return []


def fetch_from_090227_ct():
    try:
        import urllib.request
        req = urllib.request.Request(CDN_API_090227_CT)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()

        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  090227电信API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  090227电信API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  090227电信API获取失败: {e}")
        return []


def fetch_from_090227_cu():
    """[TRAE SOLO CN] v4.9：获取联通专属优选IP"""
    try:
        req = urllib.request.Request(CDN_API_090227_CU)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()
        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  090227联通API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  090227联通API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  090227联通API获取失败: {e}")
        return []


def fetch_from_090227_cmcc():
    """[TRAE SOLO CN] v4.9：获取移动专属优选IP"""
    try:
        req = urllib.request.Request(CDN_API_090227_CMCC)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()
        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  090227移动API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  090227移动API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  090227移动API获取失败: {e}")
        return []


def fetch_from_001315_ct():
    try:
        import urllib.request
        req = urllib.request.Request(CDN_API_001315_CT)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()

        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  001315电信API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  001315电信API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  001315电信API获取失败: {e}")
        return []


def fetch_from_001315_cu():
    """[TRAE SOLO CN] v4.9：获取联通专属优选IP"""
    try:
        req = urllib.request.Request(CDN_API_001315_CU)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()
        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  001315联通API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  001315联通API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  001315联通API获取失败: {e}")
        return []


def fetch_from_001315_cmcc():
    """[TRAE SOLO CN] v4.9：获取移动专属优选IP"""
    try:
        req = urllib.request.Request(CDN_API_001315_CMCC)
        req.add_header('User-Agent', 'Mozilla/5.0')
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()
        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  001315移动API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  001315移动API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  001315移动API获取失败: {e}")
        return []


def fetch_from_wetest_ct():
    logger.info(f"  查询WeTest.vip电信优选: {CDN_API_WETEST_CT} @ {DNS_SERVER}")
    ips = resolve_dns(CDN_API_WETEST_CT, dns_server=DNS_SERVER)
    if not ips:
        logger.info(f"  主DNS无响应，尝试备用: {DNS_SERVER_BACKUP}")
        ips = resolve_dns(CDN_API_WETEST_CT, dns_server=DNS_SERVER_BACKUP)
    if ips:
        logger.info(f"  WeTest电信返回 {len(ips)} 个IP: {ips}")
    else:
        logger.warning("  WeTest电信DNS无响应")
    return ips




def fetch_from_custom_source_urls():
    urls = [item.strip() for item in (CDN_CUSTOM_SOURCE_URLS or '').split(',') if item.strip()]
    if not urls:
        return []
    aggregated = []
    for url in urls:
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode('utf-8', errors='ignore').strip()
            local_count = 0
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                ip = line.split('#')[0].strip().split(':')[0].strip()
                if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                    aggregated.append(ip)
                    local_count += 1
            logger.info(f"  自定义优选源 {url} 返回 {local_count} 个IP")
        except Exception as e:
            logger.warning(f"  自定义优选源获取失败 {url}: {e}")
    return aggregated


def detect_user_isp(db_path=None):
    """
    [TRAE SOLO CN] v4.9：通过DDNS域名识别用户运营商
    返回: 'telecom'/'unicom'/'mobile'/'unknown'
    """
    if not USER_DDNS_DOMAIN:
        logger.info("  DDNS域名未配置，使用默认运营商匹配")
        isp_lower = USER_EXPECTED_ISP.lower()
        if '联通' in isp_lower or 'unicom' in isp_lower:
            return 'unicom'
        if '移动' in isp_lower or 'cmcc' in isp_lower or '铁通' in isp_lower:
            return 'mobile'
        return 'telecom'

    user_ips = resolve_dns(USER_DDNS_DOMAIN)
    if not user_ips:
        logger.warning(f"  DDNS域名 {USER_DDNS_DOMAIN} 解析失败，使用预期运营商")
        isp_lower = USER_EXPECTED_ISP.lower()
        if '联通' in isp_lower:
            return 'unicom'
        if '移动' in isp_lower:
            return 'mobile'
        return 'telecom'

    user_ip = user_ips[0]
    logger.info(f"  DDNS解析用户IP: {USER_DDNS_DOMAIN} → {user_ip}")

    try:
        api_url = f"http://ip-api.com/json/{user_ip}?lang=zh-CN"
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode())
            isp_name = geo_data.get('isp', '')
            logger.info(f"  用户运营商: {isp_name}")
            if '电信' in isp_name or 'telecom' in isp_name.lower() or 'chinanet' in isp_name.lower() or 'chinatel' in isp_name.lower():
                return 'telecom'
            if '联通' in isp_name or 'unicom' in isp_name.lower() or 'china unicom' in isp_name.lower() or '网通' in isp_name:
                return 'unicom'
            if '移动' in isp_name or 'mobile' in isp_name.lower() or 'cmcc' in isp_name.lower() or '铁通' in isp_name or 'tietong' in isp_name.lower():
                return 'mobile'
    except Exception as e:
        logger.debug(f"  IP归属地查询失败: {e}")

    if db_path:
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT user_isp FROM user_network_state WHERE user_isp != '' ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row and row[0]:
                isp_name = row[0]
                if '电信' in isp_name:
                    return 'telecom'
                if '联通' in isp_name:
                    return 'unicom'
                if '移动' in isp_name:
                    return 'mobile'
        except Exception:
            pass
        finally:
            if conn:
                conn.close()

    isp_lower = USER_EXPECTED_ISP.lower()
    if '联通' in isp_lower:
        return 'unicom'
    if '移动' in isp_lower:
        return 'mobile'
    return 'telecom'


def fetch_isp_matched_ips(isp_type):
    """
    [TRAE SOLO CN] v4.9：根据用户运营商自动匹配三网API获取专属IP池
    isp_type: 'telecom'/'unicom'/'mobile'/'unknown'
    返回: 去重后的IP列表
    """
    all_ips = []

    if isp_type == 'telecom':
        logger.info("  三网匹配: 电信用户，获取电信专属IP池")
        all_ips += fetch_from_090227_ct()
        all_ips += fetch_from_001315_ct()
        all_ips += [item['ip'] for item in fetch_from_vvhan_ct() if isinstance(item, dict) and 'ip' in item]
        all_ips += fetch_from_wetest_ct()
    elif isp_type == 'unicom':
        logger.info("  三网匹配: 联通用户，获取联通专属IP池")
        all_ips += fetch_from_090227_cu()
        all_ips += fetch_from_001315_cu()
        all_ips += fetch_from_090227_ct()
        all_ips += fetch_from_001315_ct()
    elif isp_type == 'mobile':
        logger.info("  三网匹配: 移动用户，获取移动专属IP池")
        all_ips += fetch_from_090227_cmcc()
        all_ips += fetch_from_001315_cmcc()
        all_ips += fetch_from_090227_ct()
        all_ips += fetch_from_001315_ct()
    else:
        logger.info("  三网匹配: 未知运营商，获取全量IP池")
        all_ips += fetch_from_090227_ct()
        all_ips += fetch_from_090227_cu()
        all_ips += fetch_from_090227_cmcc()
        all_ips += fetch_from_001315_ct()
        all_ips += fetch_from_001315_cu()
        all_ips += fetch_from_001315_cmcc()

    all_ips += fetch_from_ipdb_api()
    all_ips += fetch_from_custom_source_urls()

    seen = set()
    unique_ips = []
    for ip in all_ips:
        if ip not in seen and ip and len(ip.split('.')) == 4 and ip[0].isdigit():
            seen.add(ip)
            unique_ips.append(ip)

    logger.info(f"  三网匹配获取 {len(unique_ips)} 个去重IP (运营商={isp_type})")
    return unique_ips


def calculate_isp_match_score(ip, isp_type):
    """
    [TRAE SOLO CN] v4.9：计算IP与用户运营商的匹配度
    返回 0-100 分
    """
    if isp_type == 'unknown':
        return 50

    isp_key = {'telecom': 'telecom', 'unicom': 'unicom', 'mobile': 'mobile'}.get(isp_type, '')
    if not isp_key:
        return 50

    isp_info = THREE_ISP_OPTIMAL_PREFIXES.get(isp_key, {})
    prefixes = isp_info.get('prefixes', [])

    for prefix in prefixes:
        if ip.startswith(prefix):
            return 100

    for other_key, other_info in THREE_ISP_OPTIMAL_PREFIXES.items():
        if other_key == isp_key:
            continue
        for prefix in other_info.get('prefixes', []):
            if ip.startswith(prefix):
                return 30

    return 50


def match_region_filter(source_name):
    filters = [item.strip().upper() for item in (CDN_REGION_FILTER or '').split(',') if item.strip()]
    if not filters:
        return True
    upper_name = (source_name or '').upper()
    return any(region in upper_name for region in filters)


def apply_fastest_limit(results):
    if not CDN_FASTEST_LIMIT or CDN_FASTEST_LIMIT <= 0:
        return results
    return results[:CDN_FASTEST_LIMIT]

def fetch_from_ipdb_api():
    try:
        import urllib.request
        req = urllib.request.Request(IPDB_API_URL)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()

        ips = []
        for line in content.split('\n'):
            ip = line.strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  IPDB返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  IPDB API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  IPDB API获取失败: {e}")
        return []


def get_current_cdn_ips_from_db():
    """从数据库读取当前正在使用的CDN优选IP"""
    db_path = os.path.join(DATA_DIR, 'singbox.db')
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
        row = cursor.fetchone()
        if row and row[0]:
            raw = row[0].strip()
            if raw.startswith('['):
                try:
                    ips = [item['ip'] for item in json.loads(raw) if isinstance(item, dict) and 'ip' in item]
                except (json.JSONDecodeError, TypeError):
                    ips = [ip.strip() for ip in raw.split(',') if ip.strip()]
            else:
                ips = [ip.strip() for ip in raw.split(',') if ip.strip()]
            logger.info(f"  数据库现有CDN IP: {ips}")
            return ips
        return []
    except Exception as e:
        logger.debug(f"  读取现有CDN IP失败: {e}")
        return []
    finally:
        if conn:
            conn.close()


def fetch_cdn_ips():
    """
    v4.1 存活优先模式：
    1. 读取数据库现有CDN IP，逐个TCP存活检测+HTTP 403检测
    2. 存活的IP保留，死亡/被拦截的IP标记为待替换
    3. 收集候选IP（用户投喂+外部API）
    4. 从候选池挑存活IP补上死亡空缺
    5. 只对新增候选IP做HTTP测试记录评分
    
    【v4.3.8优化】：
    - 增加 HTTP 403 检测，被 Cloudflare 拦截的 IP 也标记为待替换
    - 当池中可用 IP < 3 时，自动从外部 API 补全 IP 池
    - 用户无需手动添加 IP，系统自动维护池子健康
    """
    db_path = init_db()
    user_probe_result = None
    
    # 【v4.8重构】[TRAE SOLO CN]：CDN_MODE三模式替代CDN_PREFER_IP_OVER_DOMAIN
    if CDN_MODE == 'domain_default':
        logger.info("[默认域名模式] CDN_MODE=domain_default，跳过所有优选，CDN节点使用CF域名")
        current_ips = get_current_cdn_ips_from_db()
        return (current_ips if current_ips else []), None, 'unknown'
    
    if CDN_MODE == 'domain_optimized':
        logger.info("[优选域名模式] CDN_MODE=domain_optimized，执行优选域名测速")
        best_domain = select_best_domain(CDN_OPTIMIZED_DOMAINS, VLESS_WS_PORT)
        if best_domain:
            db_path_save = init_db()
            if db_path_save:
                try:
                    conn = sqlite3.connect(db_path_save)
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('cdn_optimized_domain', ?)", (best_domain,))
                    conn.commit()
                    conn.close()
                    logger.info(f"  优选域名已保存: {best_domain}")
                except Exception as e:
                    logger.error(f"  保存优选域名失败: {e}")
        current_ips = get_current_cdn_ips_from_db()
        return (current_ips if current_ips else []), None, 'unknown'
    
    # 步骤1：检查现有CDN IP存活情况（TCP + HTTP 403检测）
    logger.info(">>> 步骤1：检查现有CDN IP存活情况")
    current_ips = get_current_cdn_ips_from_db()
    alive_ips = []
    dead_ips = []
    blocked_ips = []  # 被Cloudflare拦截的IP（403）
    
    if current_ips:
        for ip in current_ips:
            if ip in CDN_IP_BLACKLIST:
                logger.info(f"  {ip} 在黑名单中，跳过")
                dead_ips.append(ip)
                continue
            
            # TCP测试
            if not tcp_port_test(ip, 443, timeout=3):
                dead_ips.append(ip)
                logger.info(f"  {ip}  TCP死亡")
                continue
            
            # TLS握手验证 [TRAE SOLO CN] v4.7：Cloudflare SNI严格验证
            if not tls_handshake_test(ip, 443, timeout=3):
                blocked_ips.append(ip)
                logger.info(f"  {ip}  TLS握手失败(SNI验证)")
                continue
            
            # HTTP 403检测（Cloudflare拦截检测），加随机间隔避免被识别为爬虫
            if current_ips.index(ip) > 0:
                time.sleep(random.uniform(1, 3))
            latency, success = http_latency_test(ip, port=443, timeout=3)
            if not success:
                blocked_ips.append(ip)
                logger.info(f"  {ip}  被Cloudflare拦截(403)")
            else:
                alive_ips.append(ip)
                logger.info(f"  {ip} ✅ 存活")
        
        logger.info(f"  存活: {len(alive_ips)} 个, 死亡: {len(dead_ips)} 个, 被拦截: {len(blocked_ips)} 个")
        if len(blocked_ips) > 0 and len(alive_ips) == 0:
            logger.warning("[TRAE SOLO CN] 所有CDN IP的TLS握手均失败！Cloudflare SNI严格验证已启用，建议设置 CDN_MODE=domain_optimized 或 domain_default 使用域名模式")
    else:
        logger.info("  数据库无现有IP，需要全新优选")
    
    # v4.5 全部存活但质量差也触发更新
    # [TRAE SOLO CN] v4.9修复：即使全部存活也要收集候选IP做对比
    if current_ips and not dead_ips and not blocked_ips:
        # v4.5 用户网络探测
        user_probe_result = probe_user_network(db_path)
        # v4.9 运营商识别
        isp_type = detect_user_isp(db_path)
        # 检查平均评分
        total_score = 0
        scored_count = 0
        for ip in alive_ips:
            perf = get_ip_performance(db_path, ip)
            if perf and perf['total_tests'] > 0:
                total_score += calculate_composite_score(perf, user_probe_result=user_probe_result,
                                                        isp_type=isp_type)
                scored_count += 1
        avg_score = total_score / scored_count if scored_count > 0 else 0
        if avg_score < 60:
            logger.warning(f"所有IP存活但平均评分仅{avg_score:.1f}（偏低），触发质量驱动刷新")
            # 不return，继续执行候选收集和评分
        else:
            logger.info(f"[OK] 所有CDN IP存活正常，平均评分{avg_score:.1f}，但仍收集候选IP做对比")
            # 不return！继续收集候选IP做对比，如果有更好的就替换
    
    # 步骤2：收集候选IP（三网匹配+用户投喂）
    logger.info("\n>>> 步骤2：收集候选IP（三网匹配）")
    candidate_ips = {}
    source_status = {}

    # 2.0 识别用户运营商
    isp_type = detect_user_isp(db_path)
    logger.info(f"  用户运营商类型: {isp_type}")

    # 2.1 用户投喂候选池（优先级最高）
    logger.info("  2.1 用户投喂候选池")
    if CDN_IP_BLACKLIST:
        logger.info(f"  黑名单过滤: {len(CDN_IP_BLACKLIST)} 个IP将被跳过")
    for ip in CDN_PREFERRED_IPS:
        if ip in CDN_IP_BLACKLIST:
            logger.debug(f"  跳过黑名单IP: {ip}")
            continue
        if ip not in candidate_ips:
            candidate_ips[ip] = {'sources': ['local'], 'speed': None}
        else:
            candidate_ips[ip]['sources'].append('local')
    source_status['local'] = len(CDN_PREFERRED_IPS) > 0

    # 2.2 三网API匹配获取（根据用户运营商自动选择API）
    logger.info(f"  2.2 三网API匹配 (运营商={isp_type})")
    # [TRAE SOLO CN] v4.10.6 同时获取三网各自IP列表用于均衡度评分
    global _three_isp_cache
    _three_isp_cache = {}
    try:
        ct_ips = fetch_from_090227_ct() + fetch_from_001315_ct()
        _three_isp_cache['telecom'] = set(ct_ips)
        logger.info(f"  电信API缓存: {len(_three_isp_cache['telecom'])} 个IP")
    except Exception as e:
        logger.debug(f"  电信API缓存失败: {e}")
        _three_isp_cache['telecom'] = set()
    try:
        cu_ips = fetch_from_090227_cu() + fetch_from_001315_cu()
        _three_isp_cache['unicom'] = set(cu_ips)
        logger.info(f"  联通API缓存: {len(_three_isp_cache['unicom'])} 个IP")
    except Exception as e:
        logger.debug(f"  联通API缓存失败: {e}")
        _three_isp_cache['unicom'] = set()
    try:
        cmcc_ips = fetch_from_090227_cmcc() + fetch_from_001315_cmcc()
        _three_isp_cache['mobile'] = set(cmcc_ips)
        logger.info(f"  移动API缓存: {len(_three_isp_cache['mobile'])} 个IP")
    except Exception as e:
        logger.debug(f"  移动API缓存失败: {e}")
        _three_isp_cache['mobile'] = set()
    isp_ips = fetch_isp_matched_ips(isp_type)
    source_status['isp_matched'] = bool(isp_ips)
    for ip in isp_ips:
        if ip not in candidate_ips:
            candidate_ips[ip] = {'sources': ['isp_matched'], 'speed': None}
        else:
            candidate_ips[ip]['sources'].append('isp_matched')

    # v4.1 黑名单全局过滤（所有来源都要过滤）
    if CDN_IP_BLACKLIST:
        before_count = len(candidate_ips)
        for bl_ip in CDN_IP_BLACKLIST:
            if bl_ip in candidate_ips:
                del candidate_ips[bl_ip]
        after_count = len(candidate_ips)
        if before_count > after_count:
            logger.info(f"  黑名单过滤: 移除了 {before_count - after_count} 个黑名单IP: {CDN_IP_BLACKLIST}")

    logger.info(f"\n  共收集 {len(candidate_ips)} 个候选IP")

    # 步骤3：阶段化测速（先测连通+延迟，只对前30个测速度）
    logger.info("\n>>> 步骤3：候选IP阶段化测速")
    # v4.5 用户网络探测
    user_probe_result = probe_user_network(db_path)
    if user_probe_result:
        if user_probe_result['ip_changed']:
            logger.warning(f"  用户IP变更({user_probe_result['ip']})，触发全量重新评分")
        if user_probe_result['latency_spike']:
            logger.warning(f"  用户网络延时突增，触发CDN刷新")
        if not user_probe_result['quality_ok']:
            logger.warning(f"  用户网络质量不达标，触发CDN刷新")
    
    # 阶段1：所有候选IP测TCP+TLS+HTTP延迟
    logger.info("  阶段1：所有候选IP测连通+延迟")
    first_stage = []
    for ip, info in candidate_ips.items():
        # v4.5 硬淘汰检查
        rejected, reject_reason = hard_reject_cdn_ip(ip, user_probe_result, db_path)
        if rejected:
            logger.info(f"  {ip} 硬淘汰: {reject_reason}")
            continue
        # 先做TCP存活测试
        if not tcp_port_test(ip, 443, timeout=5):
            continue

        # TLS握手验证
        if not tls_handshake_test(ip, 443, timeout=5):
            logger.debug(f"  候选IP {ip} TLS握手失败，跳过")
            continue
        
        # HTTP延迟测试
        latency, success = http_latency_test(ip, port=443, timeout=8)
        if not success or latency is None:
            continue
        
        first_stage.append({
            'ip': ip,
            'latency': latency,
            'sources': info['sources'],
            'info': info
        })
        
        # 测试间隔
        time.sleep(random.uniform(1, 2))
    
    # 按延迟排序
    first_stage.sort(key=lambda x: x['latency'])
    
    # 阶段2：只对前30个测速度（节省时间和流量）
    logger.info(f"\n  阶段2：对前30个IP测速度（共{len(first_stage)}个存活IP）")
    tested_results = []
    for i, item in enumerate(first_stage):
        ip = item['ip']
        latency = item['latency']
        info = item['info']
        user_path_result = None
        cross_isp = None
        
        if i < 30:
            if i > 0:
                time.sleep(random.uniform(2, 3))
            
            speed_mbps = tcp_speed_test(ip, port=443, timeout=15)
            if speed_mbps > 0:
                update_speed_mbps(db_path, ip, speed_mbps)
                logger.info(f"  {ip} 速度测试: {speed_mbps} Mbps")
            
            # [TRAE SOLO CN] v4.10.6 用户路径测速
            if USER_DDNS_DOMAIN:
                user_path_result = test_user_path_latency(cdn_ip=ip, port=443, timeout=15)
                if user_path_result and user_path_result.get('success'):
                    u_lat = user_path_result.get('latency_ms', 0)
                    u_spd = user_path_result.get('speed_mbps', 0)
                    logger.info(f"  {ip} 用户路径: 延迟={u_lat:.1f}ms 速度={u_spd:.1f}Mbps")
                    if u_lat > CDN_IP_HARD_REJECT['user_path_latency_ms']:
                        logger.info(f"  {ip} 硬淘汰: 用户路径延时{u_lat:.1f}ms超过{CDN_IP_HARD_REJECT['user_path_latency_ms']}ms")
                        continue
                    if user_path_result.get('packet_loss_rate', 0) > CDN_IP_HARD_REJECT['packet_loss_rate']:
                        logger.info(
                            f"  {ip} 硬淘汰: 用户路径丢包{user_path_result.get('packet_loss_rate', 0)*100:.0f}%超过"
                            f"{CDN_IP_HARD_REJECT['packet_loss_rate']*100:.0f}%"
                        )
                        continue
                    if u_spd > 0 and u_spd < CDN_IP_HARD_REJECT['download_speed_mbps']:
                        logger.info(
                            f"  {ip} 硬淘汰: 用户路径速度{u_spd:.1f}Mbps低于"
                            f"{CDN_IP_HARD_REJECT['download_speed_mbps']}Mbps"
                        )
                        continue
            
            # [TRAE SOLO CN] v4.10.6 三网均衡度
            cross_isp = calculate_cross_isp_score(ip)
            
            source_tag = 'local' if 'local' in info['sources'] else 'external'
            record_ip_test(db_path, ip, latency, True, source=source_tag)
        else:
            cross_isp = calculate_cross_isp_score(ip)
            source_tag = 'local' if 'local' in info['sources'] else 'external'
            record_ip_test(db_path, ip, latency, True, source=source_tag)
        
        perf = get_ip_performance(db_path, ip)
        if perf:
            score = calculate_composite_score(perf, user_probe_result=user_probe_result,
                                             isp_type=isp_type,
                                             user_path_result=user_path_result,
                                             cross_isp_score=cross_isp)
            tested_results.append({
                'ip': ip,
                'latency': latency,
                'speed': perf.get('speed_mbps', 0),
                'score': score,
                'sources': info['sources'],
                'perf': perf,
                'is_new': perf['total_tests'] < 3,
                'cross_isp_score': cross_isp or 0,
            })

    # 按优先级排序：
    # 1. 你投喂的本地IP优先
    # 2. 评分越高越好
    # 3. 延迟越低越好
    tested_results.sort(key=lambda x: (
        0 if 'local' in x['sources'] else 1,
        -x['score'],
        x['latency']
    ))
    tested_results = [r for r in tested_results if match_region_filter(','.join(r['sources']))]
    tested_results = apply_fastest_limit(tested_results)

    # C段分散筛选：优先选择与已选IP不在同一C段的候选IP
    def get_c_segment(ip):
        """获取IP的C段（前3个八位）"""
        parts = ip.split('.')
        return '.'.join(parts[:3]) if len(parts) == 4 else ip

    selected_segments = set()
    diversified_results = []
    remaining_results = []

    for r in tested_results:
        seg = get_c_segment(r['ip'])
        if seg not in selected_segments:
            diversified_results.append(r)
            selected_segments.add(seg)
        else:
            remaining_results.append(r)

    # 先放不同C段的，再用同C段的补满
    tested_results = diversified_results + remaining_results

    # 检查C段覆盖情况
    covered_segments = set(get_c_segment(r['ip']) for r in tested_results[:15])
    logger.info(f"  C段覆盖: {len(covered_segments)} 个不同C段 ({', '.join(sorted(covered_segments)[:8])}...)")

    logger.info(f"  存活候选: {len(tested_results)} 个")
    for i, r in enumerate(tested_results[:10]):
        tag = "[本地]" if 'local' in r['sources'] else "[外部]"
        logger.info(f"  {i+1}. {r['ip']} | {tag} 评分={r['score']} 延迟={r['latency']:.1f}ms")

    # 步骤4：[TRAE SOLO CN] v4.10.2 从评分排序结果中选Top N，不再无脑保留所有存活IP
    # 之前final_ips=list(alive_ips)导致高延迟IP只要"活着"就永远留在池子里
    # 现在改为：从tested_results（已评分排序）中选Top CDN_TOP_IPS_COUNT个
    logger.info(f"\n>>> 步骤4：从评分排序结果中选Top {CDN_TOP_IPS_COUNT}个IP")

    # 先把死亡/被拦截的IP从tested_results中排除
    dead_or_blocked = set(dead_ips + blocked_ips)
    quality_results = [r for r in tested_results if r['ip'] not in dead_or_blocked]

    # 取评分最高的Top N
    final_ips = [r['ip'] for r in quality_results[:CDN_TOP_IPS_COUNT]]

    # 如果评分结果不够，用存活IP补
    if len(final_ips) < CDN_TOP_IPS_COUNT:
        for ip in alive_ips:
            if ip not in final_ips and ip not in dead_or_blocked:
                final_ips.append(ip)
                if len(final_ips) >= CDN_TOP_IPS_COUNT:
                    break
    
    # 【v4.3.8新增】IP池自动补全：当池中可用IP < 3时，从外部API补全
    if len(final_ips) < 3 and tested_results:
        logger.info(f"\n>>> IP池健康检查：池中只有{len(final_ips)}个可用IP，需要补全")
        # 从候选池中挑选更多IP加入池子（最多补到10个）
        pool_target = 10
        pool_needed = pool_target - len(final_ips)
        if pool_needed > 0:
            new_candidates = [r for r in tested_results if r['ip'] not in set(final_ips)]
            for r in new_candidates[:pool_needed]:
                final_ips.append(r['ip'])
                logger.info(f"  池子补全: {r['ip']} (评分={r['score']})")
    
    logger.info(f"\n[数据源状态报告]")
    for source, success in source_status.items():
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {source}: {status}")

    if final_ips:
        logger.info(f"\n[OK] 最终优选 {len(final_ips)} 个IP: {final_ips}")
        return final_ips, user_probe_result, isp_type
    else:
        logger.warning("[WARN] 所有IP测试均失败，使用本地池前5个")
        return CDN_PREFERRED_IPS[:CDN_TOP_IPS_COUNT], user_probe_result, isp_type


def cleanup_old_history(db_path, days=7):
    """清理ip_test_history表中超过指定天数的历史记录，防止数据库无限膨胀"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        cursor.execute("DELETE FROM ip_test_history WHERE test_time < ?", (cutoff_str,))
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"  清理 {deleted} 条过期测试记录（>{days}天）")
        conn.commit()
    except Exception as e:
        logger.debug(f"  清理历史记录失败: {e}")
    finally:
        if conn:
            conn.close()


def assign_and_save_ips(ips, user_probe_result=None, isp_type='unknown'):
    if not ips:
        return

    db_path = os.path.join(DATA_DIR, 'singbox.db')

    # 这里必须信任 fetch_cdn_ips() 已经产出的顺序。
    # 上游排序已经综合了用户路径测速、跨运营商和稳定性，不能在这里再用弱化信息重排一次，
    # 否则会把阶段化测速选出的最优IP换成次优甚至更差的IP。
    if len(ips) >= 3:
        selected_ips = list(ips[:3])
        scored_ips = []
        for ip in ips:
            perf = get_ip_performance(db_path, ip)
            score = calculate_composite_score(
                perf,
                user_probe_result=user_probe_result,
                isp_type=isp_type
            ) if perf else 50.0
            scored_ips.append((ip, score))
        logger.info(f"  使用上游排序前3名分配: {', '.join(selected_ips)}")
    else:
        selected_ips = list(ips)
        scored_ips = []
        for ip in ips:
            perf = get_ip_performance(db_path, ip)
            score = calculate_composite_score(
                perf,
                user_probe_result=user_probe_result,
                isp_type=isp_type
            ) if perf else 50.0
            scored_ips.append((ip, score))
        while len(selected_ips) < 3:
            selected_ips.append(ips[len(selected_ips) % len(ips)] if ips else '0.0.0.0')
    vless_ws_ip = selected_ips[0]
    vless_upgrade_ip = selected_ips[1]
    trojan_ws_ip = selected_ips[2]

    logger.info(f"\n>>> CDN优选IP（每个协议独立IP）:")
    logger.info(f"  VLESS-WS IP: {vless_ws_ip}")
    logger.info(f"  VLESS-HTTPUpgrade IP: {vless_upgrade_ip}")
    logger.info(f"  Trojan-WS IP: {trojan_ws_ip}")

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_ws_cdn_ip', vless_ws_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_upgrade_cdn_ip', vless_upgrade_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('trojan_ws_cdn_ip', trojan_ws_ip))
        # [TRAE SOLO CN] v4.10.2 cdn_ips_list存JSON格式（含评分+延迟），订阅服务换IP时按评分选
        ips_json = json.dumps([{
            'ip': ip, 'score': score,
            'latency': (lambda p: p['avg_latency'] if p and p.get('avg_latency', 0) > 0 else 0)(get_ip_performance(db_path, ip)),
            'speed_mbps': (lambda p: p.get('speed_mbps', 0) or 0)(get_ip_performance(db_path, ip)),
            'cross_isp_score': (lambda p: p.get('user_isp_match', 0) or 0)(get_ip_performance(db_path, ip))
        } for ip, score in scored_ips], ensure_ascii=False)
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ips_json))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
        conn.commit()
    finally:
        if conn:
            conn.close()
    # C段覆盖检查
    all_segments = set('.'.join(ip.split('.')[:3]) for ip in ips if len(ip.split('.')) == 4)
    logger.info(f"  IP池C段覆盖: {len(all_segments)} 个 ({', '.join(sorted(all_segments)[:6])})")

    logger.info(f"\n[OK] CDN优选IP已保存")

    # [TRAE SOLO CN] v4.10.2 CDN测速完成日志：打印新池大小和最快IP
    best_ip = ips[0] if ips else '无'
    best_score_val = scored_ips[0][1] if scored_ips else 0
    print(f"[CDN测速] CDN测速完成，新池大小: {len(ips)}，最快IP: {best_ip} (评分: {best_score_val:.1f})")

    # [TRAE SOLO CN] v4.10.1 通知订阅服务刷新CDN IP缓存
    signal_file = os.path.join(DATA_DIR, '.cdn_ip_updated')
    try:
        with open(signal_file, 'w') as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass


# 健康评估间隔（秒）
HEALTH_CHECK_INTERVAL = 43200  # 12小时


def health_check(db_path):
    """
    v4.4 定期健康评估：
    对所有存活IP执行完整评估（延迟+速度+成功率），
    如果最优IP评分比上次健康评估时下降超过30%，触发IP池刷新
    """
    logger.info("\n>>> 定期健康评估开始")

    # [TRAE SOLO CN] v4.10.16 健康评估前刷新三网缓存
    global _three_isp_cache
    if not _three_isp_cache:
        try:
            ct_ips = fetch_from_090227_ct() + fetch_from_001315_ct()
            _three_isp_cache['telecom'] = set(ct_ips)
            cu_ips = fetch_from_090227_cu() + fetch_from_001315_cu()
            _three_isp_cache['unicom'] = set(cu_ips)
            cmcc_ips = fetch_from_090227_cmcc() + fetch_from_001315_cmcc()
            _three_isp_cache['mobile'] = set(cmcc_ips)
            logger.info(f"  三网缓存已刷新: 电信{len(_three_isp_cache['telecom'])} 联通{len(_three_isp_cache['unicom'])} 移动{len(_three_isp_cache['mobile'])}")
        except Exception as e:
            logger.debug(f"  三网缓存刷新失败: {e}")

    # v4.9 用户运营商识别
    isp_type = detect_user_isp(db_path)
    logger.info(f"  用户运营商类型: {isp_type}")

    # v4.5 用户网络探测
    user_probe_result = probe_user_network(db_path)

    # 获取当前所有存活IP
    current_ips = get_current_cdn_ips_from_db()
    if not current_ips:
        logger.info("  无存活IP，跳过健康评估")
        return None

    best_score = 0
    best_ip = None
    evaluated_count = 0
    hard_reject_hits = []

    for ip in current_ips:
        # 完整评估：延迟测试，超时拉长到8秒确保准确
        latency, success = http_latency_test(ip, port=443, timeout=8)
        if success and latency is not None:
            record_ip_test(db_path, ip, latency, True, source='health_check')
        else:
            record_ip_test(db_path, ip, 0, False, source='health_check')

        # 速度测试
        speed_mbps = tcp_speed_test(ip, port=443, timeout=15)
        if speed_mbps > 0:
            update_speed_mbps(db_path, ip, speed_mbps)

        # v4.10 用户路径真实测速（如果配置了USER_DDNS_DOMAIN）
        user_path_result = None
        if USER_DDNS_DOMAIN:
            user_path_result = test_user_path_latency(cdn_ip=ip, port=443, timeout=15)

        reject_reason = ""
        if user_path_result and user_path_result.get('success'):
            user_latency = user_path_result.get('latency_ms', 0) or 0
            user_speed = user_path_result.get('speed_mbps', 0) or 0
            user_loss = user_path_result.get('packet_loss_rate', 0) or 0
            if user_latency > CDN_IP_HARD_REJECT['user_path_latency_ms']:
                reject_reason = f"用户路径延时{user_latency:.1f}ms超过{CDN_IP_HARD_REJECT['user_path_latency_ms']}ms"
            elif user_loss > CDN_IP_HARD_REJECT['packet_loss_rate']:
                reject_reason = (
                    f"用户路径丢包{user_loss*100:.0f}%超过"
                    f"{CDN_IP_HARD_REJECT['packet_loss_rate']*100:.0f}%"
                )
            elif user_speed > 0 and user_speed < CDN_IP_HARD_REJECT['download_speed_mbps']:
                reject_reason = (
                    f"用户路径速度{user_speed:.1f}Mbps低于"
                    f"{CDN_IP_HARD_REJECT['download_speed_mbps']}Mbps"
                )

        if reject_reason:
            hard_reject_hits.append((ip, reject_reason))
            logger.warning(f"  ⚠️ 健康评估发现当前CDN IP不达标: {ip} {reject_reason}")

        # 计算当前评分
        perf = get_ip_performance(db_path, ip)
        if perf:
            cross_isp = calculate_cross_isp_score(ip)
            score = calculate_composite_score(perf, user_probe_result=user_probe_result,
                                             isp_type=isp_type,
                                             user_path_result=user_path_result,
                                             cross_isp_score=cross_isp)
            conn_s = None
            try:
                conn_s = sqlite3.connect(db_path)
                cursor_s = conn_s.cursor()
                cursor_s.execute("UPDATE ip_performance SET composite_score_v2=?, user_isp_match=? WHERE ip=?",
                                (score, cross_isp, ip))
                conn_s.commit()
            except Exception:
                pass
            finally:
                if conn_s:
                    conn_s.close()
            evaluated_count += 1
            u_lat = user_path_result.get('latency_ms', 0) if user_path_result and user_path_result.get('success') else '-'
            u_spd = user_path_result.get('speed_mbps', 0) if user_path_result and user_path_result.get('success') else '-'
            logger.info(f"  {ip}: 评分={score} VPS延迟={latency:.1f}ms 速度={speed_mbps}Mbps 用户路径={u_lat}ms/{u_spd}Mbps")
            if score > best_score:
                best_score = score
                best_ip = ip

        # 测试间隔，避免被识别为爬虫
        time.sleep(random.uniform(2, 4))

    logger.info(f"  健康评估完成: 评估{evaluated_count}个IP, 最优={best_ip} 评分={best_score}")

    # v4.10 用户路径报告（如果配置了USER_DDNS_DOMAIN）
    if USER_DDNS_DOMAIN and best_ip:
        user_path = test_user_path_latency(cdn_ip=best_ip, port=443, timeout=10)
        if user_path and user_path.get('success'):
            logger.info(f"  最优IP用户路径: 延迟={user_path.get('latency_ms', 0):.1f}ms 速度={user_path.get('speed_mbps', 0):.1f}Mbps 丢包={user_path.get('packet_loss_rate', 0)*100:.0f}%")

    # 读取上次健康评估的最优评分
    last_best_score = 0
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key='last_health_best_score'")
        row = cursor.fetchone()
        if row and row[0]:
            try:
                last_best_score = float(row[0])
            except ValueError:
                last_best_score = 0
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    # 判断是否需要刷新IP池
    need_refresh = False
    if hard_reject_hits:
        need_refresh = True
        logger.warning(
            "  ⚠️ 当前CDN IP中存在用户路径不达标节点，触发IP池刷新: "
            + "; ".join(f"{ip}({reason})" for ip, reason in hard_reject_hits[:5])
        )
    if last_best_score > 0 and best_score > 0:
        decline_ratio = (last_best_score - best_score) / last_best_score
        if decline_ratio > 0.3:
            logger.warning(f"  ⚠️ 最优IP评分下降{decline_ratio*100:.0f}% ({last_best_score:.1f} → {best_score:.1f})，触发IP池刷新")
            need_refresh = True
        else:
            logger.info(f"  评分变化: {last_best_score:.1f} → {best_score:.1f} (下降{decline_ratio*100:.0f}%)，无需刷新")

    # 保存本次最优评分
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)",
                       ('last_health_best_score', str(best_score)))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)",
                       ('last_health_check_time', datetime.now().isoformat()))
        conn.commit()
    except Exception as e:
        logger.debug(f"  保存健康评估结果失败: {e}")
    finally:
        if conn:
            conn.close()

    if need_refresh:
        logger.info("  执行IP池刷新...")
        new_ips, _, refresh_isp_type = fetch_cdn_ips()
        if new_ips:
            assign_and_save_ips(new_ips, isp_type=refresh_isp_type)
            logger.info(f"  IP池刷新完成: {new_ips}")

    # [TRAE SOLO CN] v4.10.18 清理死亡IP记录+VACUUM压缩
    conn_clean = None
    try:
        conn_clean = sqlite3.connect(db_path)
        cursor_clean = conn_clean.cursor()
        cursor_clean.execute("SELECT COUNT(*) FROM ip_performance WHERE consecutive_fails > 5 AND composite_score_v2 < 10")
        dead_count = cursor_clean.fetchone()[0]
        if dead_count > 0:
            cursor_clean.execute("DELETE FROM ip_performance WHERE consecutive_fails > 5 AND composite_score_v2 < 10")
            conn_clean.commit()
            logger.info(f"  清理死亡IP记录: 删除{dead_count}条 (连续失败>5且评分<10)")
            cursor_clean.execute("VACUUM")
            logger.info(f"  数据库VACUUM压缩完成")
        else:
            logger.info(f"  无需清理死亡IP记录")
    except Exception as e:
        logger.debug(f"  数据库清理失败: {e}")
    finally:
        if conn_clean:
            conn_clean.close()

    return best_score


def run_once():
    logger.info("\n" + "="*50)
    logger.info(f"CDN监控启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)

    # [TRAE SOLO CN] v4.10.2 CDN测速开始日志：打印当前IP池大小
    try:
        old_pool = get_current_cdn_ips_from_db()
        print(f"[CDN测速] CDN测速开始，当前池大小: {len(old_pool)}")
    except Exception as e:
        print(f"[CDN测速] CDN测速开始（无法获取当前池大小: {e}）")

    ips, user_probe_result, isp_type = fetch_cdn_ips()
    if ips:
        assign_and_save_ips(ips, user_probe_result=user_probe_result, isp_type=isp_type)
    else:
        print(f"[CDN测速] CDN测速完成，无可用IP")

    db_path = os.path.join(DATA_DIR, 'singbox.db')
    cleanup_old_history(db_path)

    logger.info(f"\n>>> 等待 {CDN_MONITOR_INTERVAL}秒后下次检测...")


if __name__ == '__main__':
    LOCK_FILE = '/tmp/cdn_monitor.lock'
    lock_fd = open(LOCK_FILE, 'w')
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print(f"cdn_monitor已在运行，退出 (lock: {LOCK_FILE})")
        sys.exit(0)

    init_db()
    last_health_check = 0
    while True:
        try:
            run_once()

            # v4.4 定期健康评估：每6小时执行一次
            now = time.time()
            if now - last_health_check > HEALTH_CHECK_INTERVAL:
                db_path = os.path.join(DATA_DIR, 'singbox.db')
                health_check(db_path)
                last_health_check = now

            time.sleep(CDN_MONITOR_INTERVAL)
        except KeyboardInterrupt:
            logger.info("CDN监控已停止")
            break
        except Exception as e:
            logger.error(f"[ERROR] CDN测速出错: {e}")
            print(f"[CDN测速] CDN测速出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            time.sleep(60)
