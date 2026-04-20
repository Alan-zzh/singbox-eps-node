#!/usr/bin/env python3
"""
CDN监控脚本
Author: Alan
Version: v1.0.5
Date: 2026-04-21
功能：
  - 使用指定DNS（222.246.129.80 | 59.51.78.210）解析域名获取CDN优选IP
  - 保留固定IP池作为DNS解析失败时的降级方案
  - 每小时自动查询，确保获取到速度最快的IP
  - 自动分配每个协议独立IP

⚠️ CDN IP获取策略（按优先级）：
  1. 指定DNS解析（湖南电信DNS 222.246.129.80 | 59.51.78.210）
     - 这些DNS返回对中国用户延迟最低的Cloudflare IP
     - 严禁使用服务器本地DNS（日本DNS返回的IP对中国延迟高）
  2. 固定优选IP池（用户实测50ms左右的IP，作为降级方案）
  3. 通用DNS（114.114.114.114，最后降级）

历史教训：
  - v1.0.36用日本服务器DNS实时解析，返回的IP对中国延迟150-200ms
  - v1.0.37恢复固定IP池，但IP可能过期失效
  - v1.0.45改用指定DNS解析+固定IP池降级，兼顾实时性和稳定性
"""

import os
import sys
import time
import sqlite3
import random
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN,
        CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT,
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger('cdn_monitor')

CDN_DNS_SERVERS = [
    ('222.246.129.80', '湖南电信DNS-1'),
    ('59.51.78.210', '湖南电信DNS-2'),
]

FALLBACK_DNS_SERVERS = [
    ('114.114.114.114', '114DNS'),
]

PREFERRED_IPS = [
    '172.64.33.166',
    '162.159.45.15',
    '172.64.53.179',
    '108.162.198.145',
    '172.64.52.205',
    '162.159.44.103',
    '162.159.39.190',
    '162.159.38.26',
    '162.159.7.250',
    '104.18.37.65',
    '172.67.178.214',
    '104.21.35.190',
    '104.16.123.96',
    '104.16.124.96',
]

CDN_TOP_IPS_COUNT = 5
MONITOR_INTERVAL = 3600


def init_db():
    """初始化数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(os.path.join(DATA_DIR, 'singbox.db'))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cdn_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()
    return os.path.join(DATA_DIR, 'singbox.db')


def resolve_via_dns(domain, dns_server, timeout=5):
    """通过指定DNS服务器解析域名，返回IP列表"""
    try:
        result = subprocess.run(
            ['dig', '+short', domain, f'@{dns_server}', f'+time={timeout}'],
            capture_output=True, text=True, timeout=timeout + 5
        )
        ips = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line and len(line.split('.')) == 4 and line[0].isdigit():
                ips.append(line)
        return ips
    except Exception as e:
        logger.warning(f"DNS解析失败 {domain}@{dns_server}: {e}")
        return []


def ping_ip(ip, timeout=3):
    """ping测试IP是否可达"""
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', str(timeout), ip],
            capture_output=True, text=True, timeout=timeout + 1
        )
        return result.returncode == 0
    except Exception:
        return False


def fetch_cdn_ips():
    """获取优选IP（优先DNS解析，降级固定IP池）

    获取策略：
    1. 使用指定DNS（222.246.129.80 | 59.51.78.210）解析CF_DOMAIN
       - 这些DNS返回对中国用户延迟最低的Cloudflare IP
    2. 去重合并所有DNS返回的IP
    3. ping验证可达性
    4. 如果DNS解析失败，降级使用固定IP池
    """
    domain = CF_DOMAIN
    if not domain or not domain.strip():
        logger.warning("[WARN] CF_DOMAIN未配置，使用固定IP池")
        return _fallback_to_fixed_pool()

    logger.info(f">>> 使用指定DNS解析 {domain} 获取CDN优选IP")

    all_ips = []
    seen = set()

    for dns_ip, dns_name in CDN_DNS_SERVERS:
        logger.info(f"  查询 {dns_name} ({dns_ip})...")
        ips = resolve_via_dns(domain, dns_ip)
        for ip in ips:
            if ip not in seen:
                seen.add(ip)
                all_ips.append(ip)
        logger.info(f"  {dns_name} 返回: {ips}")

    if not all_ips:
        logger.warning("[WARN] 指定DNS均无响应，尝试降级DNS...")
        for dns_ip, dns_name in FALLBACK_DNS_SERVERS:
            ips = resolve_via_dns(domain, dns_ip)
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    all_ips.append(ip)
            logger.info(f"  {dns_name} 返回: {ips}")

    if not all_ips:
        logger.warning("[WARN] 所有DNS解析失败，降级使用固定IP池")
        return _fallback_to_fixed_pool()

    logger.info(f"  DNS解析合并去重: {all_ips}")

    valid_ips = []
    for ip in all_ips:
        if ping_ip(ip):
            valid_ips.append(ip)
            if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                break

    if valid_ips:
        logger.info(f"[OK] DNS解析+验证通过 {len(valid_ips)} 个IP: {valid_ips}")
        return valid_ips
    else:
        logger.warning("[WARN] DNS解析的IP均不可达，降级使用固定IP池")
        return _fallback_to_fixed_pool()


def _fallback_to_fixed_pool():
    """降级方案：从固定优选IP池随机选择并验证"""
    logger.info(">>> 降级：从固定优选IP池随机选择（中国用户实测最快）")

    shuffled_ips = PREFERRED_IPS.copy()
    random.shuffle(shuffled_ips)

    valid_ips = []
    for ip in shuffled_ips:
        if ping_ip(ip):
            valid_ips.append(ip)
            if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                break

    if valid_ips:
        logger.info(f"[OK] 固定IP池验证通过 {len(valid_ips)} 个IP: {valid_ips}")
        return valid_ips
    else:
        logger.warning("[WARN] 固定IP池也全部不可达，返回前5个IP")
        return PREFERRED_IPS[:CDN_TOP_IPS_COUNT]


def assign_and_save_ips(ips):
    """分配并保存优选IP（每个协议独立IP）"""
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
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_ws_cdn_ip', vless_ws_ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_upgrade_cdn_ip', vless_upgrade_ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('trojan_ws_cdn_ip', trojan_ws_ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ','.join(ips)))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"\n[OK] CDN优选IP已保存")


def run_once():
    """执行一次监控"""
    logger.info("\n" + "="*50)
    logger.info(f"CDN监控启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)

    ips = fetch_cdn_ips()
    if ips:
        assign_and_save_ips(ips)
    else:
        logger.error("[ERROR] 未获取到任何IP，跳过本次更新")

    logger.info(f"\n>>> 等待 {MONITOR_INTERVAL}秒后下次检测...")


if __name__ == '__main__':
    init_db()
    while True:
        try:
            run_once()
            time.sleep(MONITOR_INTERVAL)
        except KeyboardInterrupt:
            logger.info("CDN监控已停止")
            break
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            time.sleep(60)
