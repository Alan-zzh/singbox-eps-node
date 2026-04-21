#!/usr/bin/env python3
"""
CDN监控脚本
Author: Alan
Version: v1.0.55
Date: 2026-04-21
功能：
  - 从优选IP池中TCPing测速，选出可达的IP
  - 每小时自动测速更新，确保始终使用可达IP
  - 自动分配每个协议独立IP

⚠️ CDN优选IP核心原理：
  Cloudflare使用Anycast网络，任何Cloudflare IP都能访问到源站。
  但不同IP段对中国用户的路由质量不同：
  - 域名DNS解析返回的IP（如172.67.x.x、104.21.x.x）对中国延迟高
  - 实测优选IP（如104.16.x.x、162.159.x.x）对中国延迟低
  - 客户端连接优选IP时，SNI和Host仍指向域名，源站正确响应

⚠️ 为什么不从服务器端测速选"最快"IP：
  服务器在日本，TCPing测的是日本→Cloudflare的延迟，不是中国→Cloudflare的延迟。
  从日本测最快的IP，对中国用户可能很慢。所以只验证可达性，不按延迟排序。
  优选IP池中的IP顺序已经按中国用户实测延迟从低到高排列。

获取策略：
  1. 中国DoH解析（腾讯doh.pub / 阿里dns.alidns.com）— 获取域名IP作为备选
  2. 优选IP池（已按中国用户延迟排序）— TCPing验证可达性
  3. 合并去重，优先使用优选IP池中排在前面的可达IP

历史教训：
  - v1.0.36用日本服务器DNS实时解析，返回的IP对中国延迟150-200ms
  - v1.0.37恢复固定IP池，但IP可能过期失效
  - v1.0.45改用指定DNS解析+固定IP池降级，但指定DNS从日本不可达
  - v1.0.55改用中国DoH解析+优选IP池TCPing验证可达性
"""

import os
import sys
import time
import sqlite3
import json
import socket
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

CHINA_DOH_SERVERS = [
    ('https://doh.pub/dns-query', '腾讯DoH', {'accept': 'application/dns-json'}),
    ('https://dns.alidns.com/resolve', '阿里DoH', None),
]

PREFERRED_IPS = [
    '104.16.123.96',
    '104.16.124.96',
    '104.17.136.90',
    '104.17.137.90',
    '104.18.37.65',
    '104.18.38.65',
    '162.159.39.190',
    '162.159.38.26',
    '162.159.7.250',
    '162.159.45.15',
    '162.159.44.103',
    '172.64.33.166',
    '172.64.53.179',
    '172.64.52.205',
    '108.162.198.145',
    '172.67.178.214',
    '104.21.35.190',
]

CDN_TOP_IPS_COUNT = 5
MONITOR_INTERVAL = 3600
TCPING_PORT = 443
TCPING_TIMEOUT = 3


def init_db():
    """初始化数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = os.path.join(DATA_DIR, 'singbox.db')
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cdn_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path


def tcping(ip, port=TCPING_PORT, timeout=TCPING_TIMEOUT):
    """TCPing测试：验证IP端口可达性，返回是否可达
    
    注意：不使用延迟排序，因为服务器在日本，测的延迟不代表中国用户体验。
    优选IP池的顺序已按中国用户实测延迟排列，只需验证可达性即可。
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def resolve_via_doh(domain, doh_url, doh_name, headers=None, timeout=10):
    """通过DoH（DNS over HTTPS）解析域名，返回IP列表"""
    try:
        import urllib.request
        
        url = f"{doh_url}?name={domain}&type=A"
        req = urllib.request.Request(url, headers=headers or {})
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        
        ips = []
        for answer in data.get('Answer', []):
            if answer.get('type') == 1:
                ip = answer.get('data', '').strip()
                if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                    ips.append(ip)
        return ips
    except Exception as e:
        logger.warning(f"  {doh_name} 解析失败: {e}")
        return []


def fetch_cdn_ips():
    """获取优选IP（验证可达性，按池中顺序选择）

    策略：
    1. 从优选IP池中按顺序TCPing验证可达性
       - 池中IP已按中国用户实测延迟排列，排在前面的优先使用
       - 只验证可达性，不按服务器端延迟排序
    2. 中国DoH解析获取域名IP作为备选
    3. 合并去重
    """
    domain = CF_DOMAIN
    valid_ips = []
    seen = set()

    # 步骤1：从优选IP池中验证可达性（按顺序，排在前面的优先）
    logger.info(f">>> 步骤1：优选IP池验证可达性（{len(PREFERRED_IPS)}个候选，按中国延迟排序）")
    for ip in PREFERRED_IPS:
        if tcping(ip):
            if ip not in seen:
                seen.add(ip)
                valid_ips.append(ip)
                logger.info(f"  {ip}: 可达")
            if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                break
        else:
            logger.info(f"  {ip}: 不可达")

    # 步骤2：中国DoH解析获取域名IP（作为补充）
    if domain and domain.strip():
        logger.info(f"\n>>> 步骤2：中国DoH解析 {domain}（补充备选）")
        doh_ips = []
        for doh_url, doh_name, headers in CHINA_DOH_SERVERS:
            logger.info(f"  查询 {doh_name}...")
            ips = resolve_via_doh(domain, doh_url, doh_name, headers)
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    doh_ips.append(ip)
            logger.info(f"  {doh_name} 返回: {ips}")

        # DoH返回的IP如果可达，追加到末尾
        for ip in doh_ips:
            if tcping(ip):
                valid_ips.append(ip)
                logger.info(f"  {ip}(DoH): 可达，追加")

    if valid_ips:
        logger.info(f"\n[OK] 验证通过 {len(valid_ips)} 个IP: {valid_ips[:CDN_TOP_IPS_COUNT]}")
        return valid_ips[:CDN_TOP_IPS_COUNT]
    else:
        logger.warning("[WARN] 所有IP均不可达，使用优选IP池前5个")
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
