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
import re
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

# 动态网站源（带国内身份伪装）
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
    """精确扒取测速网页，支持湖南电信专属IP池容灾轮询"""
    target_url = 'https://api.uouin.com/cloudflare.html'
    
    # 定义伪装 IP 矩阵池（严格按照你要求的优先级排布）
    spoof_ips = [
        '222.246.129.80',   # 优先级一：你指定的湖南电信最优 DNS
        '59.51.78.210',     # 优先级二：备用湖南电信 DNS
        '114.114.114.114'   # 优先级三：全国通用 DNS（终极兜底，防止目标网站封锁湖南号段）
    ]

    for current_ip in spoof_ips:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'X-Forwarded-For': current_ip,
            'X-Real-IP': current_ip,
            'Client-IP': current_ip
        }

        try:
            logger.info(f">>> 尝试使用面具 IP ({current_ip}) 扒取优选节点...")
            response = requests.get(target_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                found_ips = re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', response.text)
                
                valid_ips = []
                for ip in found_ips:
                    if ip.startswith(('104.', '172.', '162.', '108.', '141.', '198.')):
                        valid_ips.append(ip)

                if valid_ips:
                    unique_ips = list(dict.fromkeys(valid_ips))
                    top_5_ips = unique_ips[:5]
                    logger.info(f"[OK] 成功使用 {current_ip} 扒取到 5 个极速 IP: {top_5_ips}")
                    return top_5_ips # 一旦成功获取，立刻退出循环并返回
                else:
                    logger.warning(f"[WARN] IP {current_ip} 未能扒取到有效数据，自动切换下一个...")
        except Exception as e:
            logger.warning(f"[WARN] 使用 IP {current_ip} 扒取失败: {e}，自动切换下一个...")
            continue
    
    # 如果所有的伪装 IP 都被网站拉黑了，使用内置的兜底 IP 保证不断网
    logger.error("[ERROR] 所有伪装 IP 扒取均失败，下发官方兜底节点")
    return CDN_FALLBACK_IPS[:5]

def assign_and_save_ips(ips):
    """分配并保存优选IP（前10个随机选3个，每个协议独立IP）"""
    if not ips:
        return

    db_path = os.path.join(DATA_DIR, 'singbox.db')

    # 从前10个IP中随机选3个不同的IP
    top_10_ips = ips[:10]
    if len(top_10_ips) >= 3:
        selected_ips = random.sample(top_10_ips, 3)
    else:
        # IP不足3个时，循环使用已有的IP
        selected_ips = []
        for i in range(3):
            selected_ips.append(top_10_ips[i % len(top_10_ips)])

    vless_ws_ip = selected_ips[0]
    vless_upgrade_ip = selected_ips[1]
    trojan_ws_ip = selected_ips[2]

    logger.info(f"\n>>> CDN优选IP（前10随机选3，每个协议独立IP）:")
    logger.info(f"  候选IP: {top_10_ips}")
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
