#!/usr/bin/env python3
"""
Singbox CDN优选IP学习系统
Author: Alan
Version: v4.1.0
Date: 2026-05-07

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
import fcntl
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN, SUB_PORT,
        CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT,
        CDN_PREFERRED_IPS, CDN_IP_BLACKLIST,
        CDN_API_WETEST_CT, CDN_API_IPDB,
        CDN_API_001315_CT, CDN_API_090227_CT, CDN_API_VVHAN,
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT,
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
    CDN_API_090227_CT = 'https://addressesapi.090227.xyz/ct'
    CDN_API_VVHAN = 'https://api.vvhan.com/tool/cf_ip'
    CDN_MONITOR_INTERVAL = 3600
    CDN_TOP_IPS_COUNT = 5

logger = get_logger('cdn_monitor')

DNS_SERVER = '222.246.129.80'
DNS_SERVER_BACKUP = '59.51.78.210'
DOH_SERVERS = [
    'https://dns.alidns.com/resolve',
    'https://doh.pub/dns-query',
]

IPDB_API_URL = CDN_API_IPDB

# v3.0 综合评分权重
SCORE_LATENCY_WEIGHT = 0.40    # 平均延迟占比40%
SCORE_SUCCESS_WEIGHT = 0.30    # 成功率占比30%
SCORE_STABILITY_WEIGHT = 0.20  # 稳定性占比20%
SCORE_FRESHNESS_WEIGHT = 0.10  # 新鲜度占比10%

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
                source TEXT DEFAULT 'unknown'
            )
        """)
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
        conn.commit()
    finally:
        if conn:
            conn.close()
    return db_path


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
            }
        return None
    finally:
        if conn:
            conn.close()


def calculate_composite_score(perf, current_latency=None):
    """
    v3.0 综合评分算法
    评分 = 延迟分(40%) + 成功率分(30%) + 稳定性分(20%) + 新鲜度分(10%)
    分数越低越好（延迟低=分高）
    """
    if perf is None or perf['total_tests'] == 0:
        # 新IP，给中等分数让它有机会表现
        return 50.0

    total = perf['total_tests']
    success = perf['success_count']
    avg_lat = perf['avg_latency']
    consec_fails = perf['consecutive_fails']
    last_success = perf['last_success_time']

    # 1. 延迟分（40%）：延迟越低分越高，0-100ms为满分，>500ms为0分
    if avg_lat > 0:
        latency_score = max(0, 100 * (1 - avg_lat / 500))
    else:
        latency_score = 50  # 无数据时给中等分

    # 2. 成功率分（30%）
    success_rate = success / total if total > 0 else 0
    success_score = success_rate * 100

    # 3. 稳定性分（20%）：连续失败会大幅扣分
    stability_score = max(0, 100 - consec_fails * 20)

    # 4. 新鲜度分（10%）：最近3天有成功记录得满分，否则递减
    freshness_score = 0
    if last_success:
        try:
            last_dt = datetime.fromisoformat(last_success)
            days_since = (datetime.now() - last_dt).days
            freshness_score = max(0, 100 - days_since * 33)
        except Exception:
            freshness_score = 0

    # 加权总分
    total_score = (
        latency_score * SCORE_LATENCY_WEIGHT +
        success_score * SCORE_SUCCESS_WEIGHT +
        stability_score * SCORE_STABILITY_WEIGHT +
        freshness_score * SCORE_FRESHNESS_WEIGHT
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


def http_latency_test(ip, port=443, timeout=5, test_url='/'):
    """
    用HTTPS请求测试IP真实延迟（模拟客户端实际连接）
    返回: (延迟ms, 是否成功) 或 (None, False) 如果失败
    
    【Bug #57修复】：之前只做TCP连接测试，无法反映对中国用户的真实链路质量
    现在发送真实HTTPS请求，测量完整握手+响应时间
    【v3.1.3修复】：异常路径正确关闭socket，防止资源泄漏
    """
    sni_host = CF_DOMAIN if CF_DOMAIN else 'cloudflare.com'
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
        
        request = f"GET {test_url} HTTP/1.1\r\nHost: {sni_host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
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
            if '200' in status_line or '301' in status_line or '302' in status_line or '404' in status_line:
                return elapsed, True
        
        return elapsed, True
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
            ips = [ip.strip() for ip in row[0].split(',') if ip.strip()]
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
    1. 读取数据库现有CDN IP，逐个TCP存活检测
    2. 存活的IP保留，死亡的IP标记为待替换
    3. 收集候选IP（用户投喂+外部API）
    4. 从候选池挑存活IP补上死亡空缺
    5. 只对新增候选IP做HTTP测试记录评分
    """
    db_path = init_db()
    
    # 步骤1：检查现有CDN IP存活情况
    logger.info(">>> 步骤1：检查现有CDN IP存活情况")
    current_ips = get_current_cdn_ips_from_db()
    alive_ips = []
    dead_ips = []
    
    if current_ips:
        for ip in current_ips:
            if ip in CDN_IP_BLACKLIST:
                logger.info(f"  {ip} 在黑名单中，跳过")
                dead_ips.append(ip)
                continue
            if tcp_port_test(ip, 443, timeout=3):
                alive_ips.append(ip)
                logger.info(f"  {ip} ✅ 存活")
            else:
                dead_ips.append(ip)
                logger.info(f"  {ip} ❌ 死亡")
        logger.info(f"  存活: {len(alive_ips)} 个, 死亡: {len(dead_ips)} 个")
    else:
        logger.info("  数据库无现有IP，需要全新优选")
    
    # 如果全部存活，不需要更新
    if current_ips and not dead_ips:
        logger.info("[OK] 所有CDN IP存活正常，不更新")
        return current_ips
    
    # 步骤2：收集候选IP（用于填补死亡空缺）
    logger.info("\n>>> 步骤2：收集候选IP")
    candidate_ips = {}
    source_status = {}
    
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

    logger.info("  2.2 vvhan API")
    vvhan_data = fetch_from_vvhan_ct()
    source_status['vvhan'] = bool(vvhan_data)
    if vvhan_data:
        for item in vvhan_data:
            ip = item['ip']
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['vvhan'], 'speed': item.get('speed')}
            else:
                candidate_ips[ip]['sources'].append('vvhan')

    logger.info("  2.3 090227电信API")
    ips_090227 = fetch_from_090227_ct()
    source_status['090227'] = bool(ips_090227)
    if ips_090227:
        for ip in ips_090227:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['090227'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('090227')

    logger.info("  2.4 001315电信API")
    ips_001315 = fetch_from_001315_ct()
    source_status['001315'] = bool(ips_001315)
    if ips_001315:
        for ip in ips_001315:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['001315'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('001315')

    logger.info("  2.5 WeTest DNS")
    ips_wetest = fetch_from_wetest_ct()
    source_status['wetest'] = bool(ips_wetest)
    if ips_wetest:
        for ip in ips_wetest:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['wetest'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('wetest')

    logger.info("  2.6 IPDB API")
    ips_ipdb = fetch_from_ipdb_api()
    source_status['ipdb'] = bool(ips_ipdb)
    if ips_ipdb:
        for ip in ips_ipdb:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['ipdb'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('ipdb')

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

    # 步骤3：对候选IP做TCP存活测试+评分排序
    logger.info("\n>>> 步骤3：候选IP存活测试+评分排序")
    tested_results = []
    
    for ip, info in candidate_ips.items():
        # 先做TCP存活测试
        if not tcp_port_test(ip, 443, timeout=3):
            continue
        
        # 存活的IP，查历史评分
        perf = get_ip_performance(db_path, ip)
        if perf and perf['total_tests'] >= 3:
            # 有历史数据，直接复用评分
            score = calculate_composite_score(perf)
            tested_results.append({
                'ip': ip,
                'latency': perf.get('avg_latency', 999),
                'speed': info.get('speed'),
                'score': score,
                'sources': info['sources'],
                'perf': perf,
                'is_new': False,
            })
        else:
            # 新IP，做HTTP测试
            latency, success = http_latency_test(ip, port=443, timeout=3)
            if success and latency is not None:
                source_tag = 'local' if 'local' in info['sources'] else 'external'
                record_ip_test(db_path, ip, latency, True, source=source_tag)
                perf = get_ip_performance(db_path, ip)
                score = calculate_composite_score(perf)
                tested_results.append({
                    'ip': ip,
                    'latency': latency,
                    'speed': info.get('speed'),
                    'score': score,
                    'sources': info['sources'],
                    'perf': perf,
                    'is_new': True,
                })

    # 按评分排序（分数越高越好）
    tested_results.sort(key=lambda x: (-x['score'], x['latency']))

    logger.info(f"  存活候选: {len(tested_results)} 个")
    for i, r in enumerate(tested_results[:10]):
        tag = "[本地]" if 'local' in r['sources'] else "[外部]"
        logger.info(f"  {i+1}. {r['ip']} | {tag} 评分={r['score']} 延迟={r['latency']:.1f}ms")

    # 步骤4：只替换死亡的IP
    logger.info(f"\n>>> 步骤4：填补死亡IP空缺（需要{len(dead_ips)}个）")
    
    # 优先保留存活的老IP
    final_ips = list(alive_ips)
    
    # 从候选池挑评分最高的补上
    needed = CDN_TOP_IPS_COUNT - len(final_ips)
    if needed > 0:
        # 过滤掉已经在final_ips里的
        new_candidates = [r for r in tested_results if r['ip'] not in set(final_ips)]
        for r in new_candidates[:needed]:
            final_ips.append(r['ip'])
            logger.info(f"  新增: {r['ip']} (评分={r['score']})")
    
    logger.info(f"\n[数据源状态报告]")
    for source, success in source_status.items():
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {source}: {status}")

    if final_ips:
        logger.info(f"\n[OK] 最终优选 {len(final_ips)} 个IP: {final_ips}")
        return final_ips
    else:
        logger.warning("[WARN] 所有IP测试均失败，使用本地池前5个")
        return CDN_PREFERRED_IPS[:CDN_TOP_IPS_COUNT]


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


def assign_and_save_ips(ips):
    if not ips:
        return

    db_path = os.path.join(DATA_DIR, 'singbox.db')

    selected_ips = ips[:3] if len(ips) >= 3 else ips + [ips[0]] * (3 - len(ips))

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
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ','.join(ips)))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
        conn.commit()
    finally:
        if conn:
            conn.close()
    logger.info(f"\n[OK] CDN优选IP已保存")


def run_once():
    logger.info("\n" + "="*50)
    logger.info(f"CDN监控启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)

    ips = fetch_cdn_ips()
    if ips:
        assign_and_save_ips(ips)

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
    while True:
        try:
            run_once()
            time.sleep(CDN_MONITOR_INTERVAL)
        except KeyboardInterrupt:
            logger.info("CDN监控已停止")
            break
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            time.sleep(60)
