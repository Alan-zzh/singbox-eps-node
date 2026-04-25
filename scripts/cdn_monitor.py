#!/usr/bin/env python3
"""
Singbox CDN优选IP学习系统
Author: Alan
Version: v3.0.0
Date: 2026-04-25

架构设计：用户投喂 + 自动验证 + 历史评分 = 持续优化的CDN优选系统

v3.0 核心特性：
  1. IP性能数据库：每个IP独立记录历史延迟/成功率/连续失败次数
  2. 综合评分算法：平均延迟40% + 成功率30% + 稳定性20% + 新鲜度10%
  3. 自动淘汰机制：连续5次失败降权，连续3天不达标移出优选池
  4. 用户投喂通道：config.py的IP作为"候选池"，脚本自动验证后入库
  5. 不依赖IP段前缀：完全基于历史表现数据，越用越准

工作流：
  每小时执行 → 从候选池+外部API收集IP → TCP测试 → 记录性能 → 综合评分 → 选最优5个

历史版本：
  - v2.0.0: 多源聚合+评分排序（理论优选≠实际最优）
  - v2.2.0: TCP连通测试+本地池优先（解决服务器端测试无意义问题）
  - v3.0.0: 学习系统+自动淘汰（持续优化，越用越准）
"""

import os
import sys
import time
import sqlite3
import json
import socket
import subprocess
import re
import fcntl
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN,
        CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT,
        CDN_PREFERRED_IPS, CDN_IP_BLACKLIST,
        CDN_API_WETEST_CT, CDN_API_IPDB,
        CDN_API_001315_CT, CDN_API_090227_CT, CDN_API_VVHAN,
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)
    CDN_PREFERRED_IPS = [
        '162.159.38.161', '108.162.198.221', '162.159.44.242',
        '172.64.52.35', '172.64.53.231', '172.64.229.110',
        '162.159.39.14', '172.64.41.181', '172.64.34.89',
        '104.18.41.58', '104.18.32.206', '172.64.229.250',
        '104.18.42.36', '162.159.13.213', '162.159.5.56',
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

TCPING_PORT = 443
TCPING_TIMEOUT = 3

SOURCE_WEIGHT = {
    'vvhan': 5,
    '090227': 5,
    '001315': 5,
    'wetest': 5,
    'ipdb': 5,
    'local': 5,
}

# v3.0 综合评分权重
SCORE_LATENCY_WEIGHT = 0.40    # 平均延迟占比40%
SCORE_SUCCESS_WEIGHT = 0.30    # 成功率占比30%
SCORE_STABILITY_WEIGHT = 0.20  # 稳定性占比20%
SCORE_FRESHNESS_WEIGHT = 0.10  # 新鲜度占比10%

# 淘汰阈值
ELIMINATE_CONSECUTIVE_FAILS = 5       # 连续失败次数
ELIMINATE_DAYS_NO_SUCCESS = 3         # 连续多少天无成功记录
MAX_PERFORMANCE_HISTORY = 100         # 每个IP最多保留多少条历史记录


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
            last_success = row[9] if not success else now

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

    # 连续失败次数过多
    if perf['consecutive_fails'] >= ELIMINATE_CONSECUTIVE_FAILS:
        return True, f"连续失败{perf['consecutive_fails']}次"

    # 成功率太低（测试超过10次后）
    if perf['total_tests'] >= 10:
        success_rate = perf['success_count'] / perf['total_tests']
        if success_rate < 0.2:
            return True, f"成功率仅{success_rate*100:.0f}%"

    # 最近多天无成功记录
    if perf['last_success_time']:
        try:
            last_dt = datetime.fromisoformat(perf['last_success_time'])
            days_since = (datetime.now() - last_dt).days
            if days_since >= ELIMINATE_DAYS_NO_SUCCESS and perf['total_tests'] >= 5:
                return True, f"{days_since}天无成功记录"
        except Exception:
            pass

    return False, "正常"


def tcping(ip, port=TCPING_PORT, timeout=TCPING_TIMEOUT):
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
    用TCP连接测试IP可达性（不依赖HTTPS/SNI，兼容所有Cloudflare IP）
    返回: (延迟ms, 是否成功) 或 (None, False) 如果失败
    """
    import socket
    sni_host = CF_DOMAIN if CF_DOMAIN else 'cloudflare.com'

    start_time = time.time()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        elapsed = (time.time() - start_time) * 1000
        sock.close()
        if result == 0:
            return elapsed, True
        return None, False
    except Exception as e:
        logger.debug(f"  TCP测试 {ip} 失败: {e}")
        return None, False


def resolve_dns(dns_name, dns_server=DNS_SERVER, timeout=10):
    ips = []

    for doh_url in DOH_SERVERS:
        try:
            import urllib.request
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


def fetch_cdn_ips():
    db_path = init_db()
    candidate_ips = {}
    source_status = {}

    logger.info(">>> 步骤1：收集所有候选IP")

    logger.info("  1.1 用户投喂候选池")
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

    logger.info("  1.2 vvhan API")
    vvhan_data = fetch_from_vvhan_ct()
    source_status['vvhan'] = bool(vvhan_data)
    if vvhan_data:
        for item in vvhan_data:
            ip = item['ip']
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['vvhan'], 'speed': item.get('speed')}
            else:
                candidate_ips[ip]['sources'].append('vvhan')

    logger.info("  1.3 090227电信API")
    ips_090227 = fetch_from_090227_ct()
    source_status['090227'] = bool(ips_090227)
    if ips_090227:
        for ip in ips_090227:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['090227'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('090227')

    logger.info("  1.4 001315电信API")
    ips_001315 = fetch_from_001315_ct()
    source_status['001315'] = bool(ips_001315)
    if ips_001315:
        for ip in ips_001315:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['001315'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('001315')

    logger.info("  1.5 WeTest DNS")
    ips_wetest = fetch_from_wetest_ct()
    source_status['wetest'] = bool(ips_wetest)
    if ips_wetest:
        for ip in ips_wetest:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['wetest'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('wetest')

    logger.info("  1.6 IPDB API")
    ips_ipdb = fetch_from_ipdb_api()
    source_status['ipdb'] = bool(ips_ipdb)
    if ips_ipdb:
        for ip in ips_ipdb:
            if ip not in candidate_ips:
                candidate_ips[ip] = {'sources': ['ipdb'], 'speed': None}
            else:
                candidate_ips[ip]['sources'].append('ipdb')

    # v3.0 黑名单全局过滤（所有来源都要过滤）
    if CDN_IP_BLACKLIST:
        before_count = len(candidate_ips)
        for bl_ip in CDN_IP_BLACKLIST:
            if bl_ip in candidate_ips:
                del candidate_ips[bl_ip]
        after_count = len(candidate_ips)
        if before_count > after_count:
            logger.info(f"  黑名单过滤: 移除了 {before_count - after_count} 个黑名单IP: {CDN_IP_BLACKLIST}")

    logger.info(f"\n  共收集 {len(candidate_ips)} 个候选IP")

    logger.info("\n>>> 步骤2：TCP连通测试 + 记录性能数据")
    tested_results = []
    for ip, info in candidate_ips.items():
        latency, success = http_latency_test(ip)
        source_tag = 'local' if 'local' in info['sources'] else 'external'
        record_ip_test(db_path, ip, latency, success, source=source_tag)

        if success and latency is not None:
            perf = get_ip_performance(db_path, ip)
            score = calculate_composite_score(perf)
            tested_results.append({
                'ip': ip,
                'latency': latency,
                'speed': info.get('speed'),
                'score': score,
                'sources': info['sources'],
                'perf': perf,
            })
        else:
            logger.debug(f"  ✗ {ip} | TCP测试失败")

    logger.info(f"\n>>> 步骤3：综合评分排序（v3.0学习算法）")
    tested_results.sort(key=lambda x: (-x['score'], x['latency']))

    local_count = sum(1 for r in tested_results if 'local' in r['sources'])
    external_count = len(tested_results) - local_count
    logger.info(f"  本地池可达 {local_count} 个，外部API可达 {external_count} 个")

    for i, r in enumerate(tested_results[:15]):
        perf = r['perf']
        speed_str = f" 速度={r['speed']}" if r['speed'] else ""
        tag = "[本地]" if 'local' in r['sources'] else "[外部]"
        test_info = ""
        if perf:
            test_info = f" 测试{perf['total_tests']}次 成功率{perf['success_count']}/{perf['total_tests']}"
        logger.info(f"  {i+1}. {r['ip']} | {tag} 评分={r['score']} 延迟={r['latency']:.1f}ms{speed_str}{test_info}")

    # v3.0 淘汰机制：标记不达标的IP
    eliminated = []
    for r in tested_results:
        elim, reason = should_eliminate_ip(r['perf'])
        if elim:
            eliminated.append((r['ip'], reason))

    if eliminated:
        logger.info(f"\n  淘汰 {len(eliminated)} 个不达标IP:")
        for ip, reason in eliminated[:5]:
            logger.info(f"    ✗ {ip} - {reason}")

    valid_ips = [r['ip'] for r in tested_results[:CDN_TOP_IPS_COUNT]]

    logger.info(f"\n[数据源状态报告]")
    for source, success in source_status.items():
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {source}: {status}")

    if valid_ips:
        logger.info(f"\n[OK] 最终优选 {len(valid_ips)} 个IP: {valid_ips}")
        return valid_ips
    else:
        logger.warning("[WARN] 所有IP测试均失败，使用本地池前5个")
        return CDN_PREFERRED_IPS[:CDN_TOP_IPS_COUNT]


def parse_speed(speed_str):
    """解析速度字符串为数字（mb/s）"""
    if not speed_str:
        return 0
    try:
        return float(str(speed_str).replace('mb/s', '').strip())
    except Exception:
        return 0


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

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_ws_cdn_ip', vless_ws_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_upgrade_cdn_ip', vless_upgrade_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('trojan_ws_cdn_ip', trojan_ws_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ','.join(ips)))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()
    logger.info(f"\n[OK] CDN优选IP已保存")


def run_once():
    logger.info("\n" + "="*50)
    logger.info(f"CDN监控启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)

    ips = fetch_cdn_ips()
    if ips:
        assign_and_save_ips(ips)
    else:
        logger.error("[ERROR] 未获取到任何IP，跳过本次更新")

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
