#!/usr/bin/env python3
"""
CDN监控脚本
Author: Alan
Version: v2.0.0
Date: 2026-04-25
功能：
  - 从多个中国实测CDN优选API聚合IP，综合评分排序
  - 多源交叉验证：同一IP被多个数据源推荐则大幅加分
  - 评分维度：数据源可信度 + 排名位置 + 交叉验证 + IP段参考
  - TCPing仅验证可达性，不用于排序（日本服务器TCPing所有CF IP都是1-2ms）
  - 每小时自动更新，确保始终使用最优IP
  - 自动分配每个协议独立IP

⚠️ CDN优选IP获取策略（v2.0.0重构 - 多源聚合+评分排序）：

  核心原则：不再按IP段前缀硬过滤，改为多源聚合+综合评分排序

  数据源（按可信度排序）：
  1. vvhan API — 中国实测，含延迟/速度/数据中心，每15分钟更新
  2. 090227电信API — 中国电信实测，纯162.159段
  3. 001315电信API — 中国电信实测，混合段
  4. WeTest DNS — DoH解析，质量不稳定
  5. IPDB API — 通用优选，大量104段
  6. 本地实测IP池 — 兜底

  评分公式：
  总分 = 数据源可信度分 + 排名加分 + 交叉验证加分 + IP段参考分

历史教训：
  - v1.0.36: 日本DNS解析返回104段，中国延迟150-200ms
  - v1.0.55: DoH解析+TCPing验证，但TCPing从日本测都是1-2ms无法区分
  - v1.0.85: 发现090227 API返回纯162.159段，但硬过滤导致001315的8.39段被丢弃
  - v2.0.0: 彻底重构为多源聚合+评分排序，不再硬过滤IP段
"""

import os
import sys
import time
import sqlite3
import json
import socket
import subprocess
import re
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN,
        CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT,
        CDN_PREFERRED_IPS, CDN_API_WETEST_CT, CDN_API_IPDB,
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
    'vvhan': 30,
    '090227': 25,
    '001315': 15,
    'wetest': 10,
    'ipdb': 5,
    'local': 0,
}

RANK_BASE_SCORE = 20
RANK_DECAY = 2

CROSS_VERIFY_BONUS = 15

IP_PREFIX_SCORE = {
    '162.159.': 10,
    '108.162.': 10,
    '172.64.': 8,
    '173.245.': 8,
    '198.41.': 8,
    '104.16.': -10,
    '104.17.': -10,
    '104.18.': -10,
    '104.19.': -10,
    '104.20.': -10,
    '104.21.': -10,
    '8.39.': -5,
    '8.35.': -5,
}


def get_ip_prefix_score(ip):
    prefix_score = 0
    for prefix, score in IP_PREFIX_SCORE.items():
        if ip.startswith(prefix):
            prefix_score = score
            break
    return prefix_score


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
        conn.commit()
    finally:
        if conn:
            conn.close()
    return db_path


def tcping(ip, port=TCPING_PORT, timeout=TCPING_TIMEOUT):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


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
    ip_scores = defaultdict(lambda: {
        'total_score': 0,
        'sources': [],
        'rank_scores': {},
        'source_scores': {},
        'cross_bonus': 0,
        'prefix_score': 0,
        'latency': None,
        'speed': None,
    })

    source_status = {}

    logger.info(">>> 步骤1：vvhan API（中国实测，含延迟/速度/数据中心）")
    vvhan_data = fetch_from_vvhan_ct()
    source_status['vvhan'] = bool(vvhan_data)
    if vvhan_data:
        for rank, item in enumerate(vvhan_data):
            ip = item['ip']
            ip_scores[ip]['sources'].append('vvhan')
            ip_scores[ip]['source_scores']['vvhan'] = SOURCE_WEIGHT['vvhan']
            ip_scores[ip]['rank_scores']['vvhan'] = max(0, RANK_BASE_SCORE - rank * RANK_DECAY)
            if item.get('latency') is not None:
                try:
                    ip_scores[ip]['latency'] = float(item['latency'])
                except (ValueError, TypeError):
                    pass
            if item.get('speed'):
                ip_scores[ip]['speed'] = item['speed']

    logger.info("\n>>> 步骤2：090227电信API（中国电信实测，纯162.159段）")
    ips_090227 = fetch_from_090227_ct()
    source_status['090227'] = bool(ips_090227)
    if ips_090227:
        for rank, ip in enumerate(ips_090227):
            ip_scores[ip]['sources'].append('090227')
            ip_scores[ip]['source_scores']['090227'] = SOURCE_WEIGHT['090227']
            ip_scores[ip]['rank_scores']['090227'] = max(0, RANK_BASE_SCORE - rank * RANK_DECAY)

    logger.info("\n>>> 步骤3：001315电信API（中国电信实测，混合段）")
    ips_001315 = fetch_from_001315_ct()
    source_status['001315'] = bool(ips_001315)
    if ips_001315:
        for rank, ip in enumerate(ips_001315):
            ip_scores[ip]['sources'].append('001315')
            ip_scores[ip]['source_scores']['001315'] = SOURCE_WEIGHT['001315']
            ip_scores[ip]['rank_scores']['001315'] = max(0, RANK_BASE_SCORE - rank * RANK_DECAY)

    logger.info("\n>>> 步骤4：WeTest DNS（DoH解析）")
    ips_wetest = fetch_from_wetest_ct()
    source_status['wetest'] = bool(ips_wetest)
    if ips_wetest:
        for rank, ip in enumerate(ips_wetest):
            ip_scores[ip]['sources'].append('wetest')
            ip_scores[ip]['source_scores']['wetest'] = SOURCE_WEIGHT['wetest']
            ip_scores[ip]['rank_scores']['wetest'] = max(0, RANK_BASE_SCORE - rank * RANK_DECAY)

    logger.info("\n>>> 步骤5：IPDB API（通用优选）")
    ips_ipdb = fetch_from_ipdb_api()
    source_status['ipdb'] = bool(ips_ipdb)
    if ips_ipdb:
        for rank, ip in enumerate(ips_ipdb):
            ip_scores[ip]['sources'].append('ipdb')
            ip_scores[ip]['source_scores']['ipdb'] = SOURCE_WEIGHT['ipdb']
            ip_scores[ip]['rank_scores']['ipdb'] = max(0, RANK_BASE_SCORE - rank * RANK_DECAY)

    logger.info("\n>>> 步骤6：本地实测IP池（兜底）")
    local_count = 0
    for rank, ip in enumerate(CDN_PREFERRED_IPS):
        if ip not in ip_scores:
            ip_scores[ip]['sources'].append('local')
            ip_scores[ip]['source_scores']['local'] = SOURCE_WEIGHT['local']
            ip_scores[ip]['rank_scores']['local'] = max(0, RANK_BASE_SCORE - rank * RANK_DECAY)
            local_count += 1
    source_status['local'] = local_count > 0

    for ip, info in ip_scores.items():
        info['prefix_score'] = get_ip_prefix_score(ip)

        unique_sources = set(info['sources'])
        cross_count = len(unique_sources)
        if cross_count >= 2:
            info['cross_bonus'] = (cross_count - 1) * CROSS_VERIFY_BONUS

        source_total = sum(info['source_scores'].values())
        rank_total = sum(info['rank_scores'].values())
        info['total_score'] = (
            source_total
            + rank_total
            + info['cross_bonus']
            + info['prefix_score']
        )

    sorted_ips = sorted(
        ip_scores.items(),
        key=lambda x: x[1]['total_score'],
        reverse=True
    )

    logger.info(f"\n{'='*60}")
    logger.info(f"[评分排序] 共 {len(sorted_ips)} 个候选IP，开始TCPing验证")
    logger.info(f"{'='*60}")

    valid_ips = []
    for ip, info in sorted_ips:
        if tcping(ip):
            sources_str = '+'.join(set(info['sources']))
            cross_str = f"×{len(set(info['sources']))}" if len(set(info['sources'])) >= 2 else ""
            latency_str = f" 延迟={info['latency']}ms" if info['latency'] is not None else ""
            logger.info(
                f"  ✓ {ip} | 评分={info['total_score']} "
                f"(源={source_total_sum(info)} 排名={rank_total_sum(info)} "
                f"交叉={info['cross_bonus']} 段={info['prefix_score']}) "
                f"| 来源={sources_str}{cross_str}{latency_str}"
            )
            valid_ips.append(ip)
            if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                break
        else:
            logger.debug(f"  ✗ {ip} | 评分={info['total_score']} | TCPing不可达，跳过")

    logger.info(f"\n[数据源状态报告]")
    for source, success in source_status.items():
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {source}: {status}")

    if valid_ips:
        logger.info(f"\n[OK] 最终优选 {len(valid_ips)} 个IP: {valid_ips}")
        return valid_ips
    else:
        logger.warning("[WARN] 所有IP均不可达，使用降级IP池前5个")
        return CDN_PREFERRED_IPS[:CDN_TOP_IPS_COUNT]


def source_total_sum(info):
    return sum(info['source_scores'].values())


def rank_total_sum(info):
    return sum(info['rank_scores'].values())


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
