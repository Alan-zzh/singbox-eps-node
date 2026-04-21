#!/usr/bin/env python3
"""
CDN监控脚本
Author: Alan
Version: v1.0.57
Date: 2026-04-21
功能：
  - 从WeTest.vip电信优选DNS获取实时Cloudflare优选IP
  - TCPing验证可达性
  - 每小时自动更新，确保始终使用最优IP
  - 自动分配每个协议独立IP

⚠️ CDN优选IP获取策略（按优先级）：
  1. WeTest.vip电信优选DNS（ct.cloudflare.182682.xyz）
     - 通过DNS解析获取电信线路最优IP
     - 每15分钟更新，按运营商分类
     - 从日本服务器用Google DNS(8.8.8.8)解析即可获取
  2. cf.001315.xyz电信API（降级方案1）
     - 返回电信专用IP列表
  3. IPDB API bestcf（降级方案2）
     - 返回通用优选IP，不按运营商分类
  4. 本地降级IP池（最后降级）
     - 池中IP按中国电信用户实测延迟排列

历史教训：
  - v1.0.36用日本服务器DNS实时解析，返回的IP对中国延迟150-200ms
  - v1.0.37恢复固定IP池，但IP可能过期失效
  - v1.0.45改用指定DNS解析+固定IP池降级，但指定DNS从日本不可达
  - v1.0.55改用中国DoH解析+优选IP池TCPing验证可达性
  - v1.0.56改用IPDB API获取实时优选IP，但不按运营商分类
  - v1.0.57改用WeTest.vip电信优选DNS，按运营商分类获取最优IP
"""

import os
import sys
import time
import sqlite3
import json
import socket
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

WETEST_CT_DNS = 'ct.cloudflare.182682.xyz'
WETEST_CM_DNS = 'cm.cloudflare.182682.xyz'
WETEST_CU_DNS = 'cu.cloudflare.182682.xyz'
DNS_SERVER = '8.8.8.8'

CF_001315_CT_URL = 'https://cf.001315.xyz/ct'

IPDB_API_URL = 'https://ipdb.api.030101.xyz/?type=bestcf'

FALLBACK_IPS = [
    '162.159.38.180',
    '108.162.198.116',
    '172.64.53.134',
    '162.159.39.89',
    '162.159.45.244',
    '162.159.44.128',
    '172.64.52.173',
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
    """TCPing测试：验证IP端口可达性"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def resolve_dns(dns_name, dns_server=DNS_SERVER, timeout=10):
    """通过指定DNS服务器解析域名，返回IP列表
    
    使用dig命令解析，从日本服务器用Google DNS(8.8.8.8)解析
    WeTest.vip的电信优选域名，获取电信线路最优IP。
    """
    try:
        result = subprocess.run(
            ['dig', '+short', dns_name, f'@{dns_server}', '+time=5'],
            capture_output=True, text=True, timeout=timeout
        )
        ips = []
        for line in result.stdout.strip().split('\n'):
            ip = line.strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        return ips
    except Exception as e:
        logger.warning(f"  DNS解析 {dns_name} 失败: {e}")
        return []


def fetch_from_wetest_ct():
    """从WeTest.vip电信优选DNS获取IP
    
    WeTest.vip提供按运营商分类的Cloudflare优选IP：
    - ct.cloudflare.182682.xyz — 电信优选
    - cm.cloudflare.182682.xyz — 移动优选
    - cu.cloudflare.182682.xyz — 联通优选
    
    每15分钟更新，从Google DNS(8.8.8.8)解析即可获取。
    返回的IP已按电信用户延迟排序。
    """
    logger.info(f"  查询WeTest.vip电信优选: {WETEST_CT_DNS}")
    ips = resolve_dns(WETEST_CT_DNS)
    if ips:
        logger.info(f"  WeTest电信返回 {len(ips)} 个IP: {ips}")
    else:
        logger.warning("  WeTest电信DNS无响应")
    return ips


def fetch_from_001315_ct():
    """从cf.001315.xyz电信API获取IP（降级方案1）"""
    try:
        import urllib.request
        req = urllib.request.Request(CF_001315_CT_URL)
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()
        
        ips = []
        for line in content.split('\n'):
            parts = line.strip().split('#')
            ip = parts[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        return ips
    except Exception as e:
        logger.warning(f"  cf.001315.xyz电信API失败: {e}")
        return []


def fetch_from_ipdb_api():
    """从IPDB API获取通用优选IP（降级方案2，不按运营商分类）"""
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
        return ips
    except Exception as e:
        logger.warning(f"  IPDB API获取失败: {e}")
        return []


def fetch_cdn_ips():
    """获取优选IP

    策略（按优先级）：
    1. WeTest.vip电信优选DNS — 按运营商分类，电信线路最优
    2. cf.001315.xyz电信API — 电信专用IP
    3. IPDB API bestcf — 通用优选IP
    4. 本地降级IP池 — 最后降级
    """
    valid_ips = []
    seen = set()

    # 步骤1：WeTest.vip电信优选DNS
    logger.info(f">>> 步骤1：WeTest.vip电信优选DNS")
    ct_ips = fetch_from_wetest_ct()
    if ct_ips:
        for ip in ct_ips:
            if ip not in seen:
                seen.add(ip)
                if tcping(ip):
                    valid_ips.append(ip)
                    logger.info(f"  {ip}(电信DNS): 可达")
                else:
                    logger.info(f"  {ip}(电信DNS): 不可达")
                if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                    break

    # 步骤2：cf.001315.xyz电信API
    if len(valid_ips) < CDN_TOP_IPS_COUNT:
        logger.info(f"\n>>> 步骤2：cf.001315.xyz电信API（还需{CDN_TOP_IPS_COUNT - len(valid_ips)}个）")
        api_ips = fetch_from_001315_ct()
        if api_ips:
            logger.info(f"  返回 {len(api_ips)} 个电信IP: {api_ips[:5]}...")
            for ip in api_ips:
                if ip not in seen:
                    seen.add(ip)
                    if tcping(ip):
                        valid_ips.append(ip)
                        logger.info(f"  {ip}(001315): 可达")
                    if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                        break
        else:
            logger.warning("  cf.001315.xyz无响应")

    # 步骤3：IPDB API bestcf
    if len(valid_ips) < CDN_TOP_IPS_COUNT:
        logger.info(f"\n>>> 步骤3：IPDB API bestcf（还需{CDN_TOP_IPS_COUNT - len(valid_ips)}个）")
        ipdb_ips = fetch_from_ipdb_api()
        if ipdb_ips:
            logger.info(f"  返回 {len(ipdb_ips)} 个IP: {ipdb_ips[:5]}...")
            for ip in ipdb_ips:
                if ip not in seen:
                    seen.add(ip)
                    if tcping(ip):
                        valid_ips.append(ip)
                        logger.info(f"  {ip}(IPDB): 可达")
                    if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                        break
        else:
            logger.warning("  IPDB API无响应")

    # 步骤4：本地降级IP池
    if len(valid_ips) < CDN_TOP_IPS_COUNT:
        logger.info(f"\n>>> 步骤4：本地降级IP池（还需{CDN_TOP_IPS_COUNT - len(valid_ips)}个）")
        for ip in FALLBACK_IPS:
            if ip not in seen:
                seen.add(ip)
                if tcping(ip):
                    valid_ips.append(ip)
                    logger.info(f"  {ip}(降级池): 可达")
                if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                    break

    if valid_ips:
        logger.info(f"\n[OK] 验证通过 {len(valid_ips)} 个IP: {valid_ips[:CDN_TOP_IPS_COUNT]}")
        return valid_ips[:CDN_TOP_IPS_COUNT]
    else:
        logger.warning("[WARN] 所有IP均不可达，使用降级IP池前5个")
        return FALLBACK_IPS[:CDN_TOP_IPS_COUNT]


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
