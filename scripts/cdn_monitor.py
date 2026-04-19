#!/usr/bin/env python3
"""
CDN监控脚本
Author: Alan
Version: v1.0.3
Date: 2026-04-20
功能：自动获取Cloudflare优选IP并保存到数据库
"""

import os
import sys
import time
import sqlite3
import random
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN,
        CDN_DB_URL, CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger('cdn_monitor')

CDN_DB_URL = 'https://api.uouin.com/cloudflare.html'
CDN_BACKUP_URLS = [
    'https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt',
    'https://cf.090227.xyz/',
]
CDN_FALLBACK_IPS = ['104.16.1.1', '104.16.132.229', '104.17.1.1']
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

def fetch_cdn_ips():
    """从CDN数据库获取优选IP，支持多源备用和降级"""
    urls = [CDN_DB_URL] + CDN_BACKUP_URLS

    for url in urls:
        try:
            logger.info(f">>> 尝试获取优选IP: {url}")
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                ips = [ip.strip() for ip in response.text.split('\n') if ip.strip() and '.' in ip]
                if ips:
                    unique_ips = list(dict.fromkeys(ips))
                    top_ips = unique_ips[:CDN_TOP_IPS_COUNT]
                    logger.info(f"[OK] 从 {url} 获取到 {len(unique_ips)} 个优选IP")
                    logger.info(f"[INFO] 前{CDN_TOP_IPS_COUNT}个IP: {top_ips}")
                    return top_ips
        except Exception as e:
            logger.warning(f"[WARN] {url} 获取失败: {e}")
            continue

    logger.warning("[WARN] 所有CDN IP源均失败，使用官方兜底IP")
    return CDN_FALLBACK_IPS[:CDN_TOP_IPS_COUNT]

def assign_and_save_ips(ips):
    """分配并保存优选IP（前5个随机选1个分配给所有CDN协议）"""
    if not ips:
        return

    db_path = os.path.join(DATA_DIR, 'singbox.db')

    top_5_ips = ips[:5]
    selected_ip = random.choice(top_5_ips)

    logger.info(f"\n>>> CDN优选IP（前5随机选1）:")
    logger.info(f"  候选IP: {top_5_ips}")
    logger.info(f"  选中IP: {selected_ip}")
    logger.info(f"  分配给: ePS-JP-VLESS-WS, ePS-JP-Trojan-WS")
    logger.info(f"  Hysteria2: 直连，不走CDN")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ip', selected_ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_cdn_ip', selected_ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('trojan_cdn_ip', selected_ip))
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

def run_daemon():
    """守护进程模式"""
    logger.info("CDN监控守护进程模式")
    logger.info(f"监控间隔: {MONITOR_INTERVAL}秒")

    while True:
        try:
            run_once()
            logger.info(f"\n>>> 等待 {MONITOR_INTERVAL}秒后下次检测...")
            time.sleep(MONITOR_INTERVAL)
        except KeyboardInterrupt:
            logger.info("\n监控已停止")
            break
        except Exception as e:
            logger.error(f"\n[ERROR] 监控错误: {e}")
            time.sleep(60)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon":
        run_daemon()
    else:
        run_once()
