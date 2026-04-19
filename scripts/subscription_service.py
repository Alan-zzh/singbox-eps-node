#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v1.0.3
Date: 2026-04-20
功能：
  - 提供单个Base64订阅链接（包含所有节点）
  - CDN优选IP自动分配
  - HTTPS协议支持

节点命名规则: ePS-{国家}-{协议}
- ePS-JP-VLESS-Reality (殖民节点，苹果域名伪装)
- ePS-JP-VLESS-WS (CDN节点)
- ePS-JP-Trojan-WS (CDN节点)
- ePS-JP-Hysteria2 (直连节点，端口跳跃)
"""

import os
import sys
import base64
import urllib.parse
import sqlite3
import random
from datetime import datetime
import ssl

from dotenv import load_dotenv
load_dotenv('/root/singbox-manager/.env')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, CF_DOMAIN, DATA_DIR, CERT_DIR, DB_FILE, SUB_PORT,
        VLESS_WS_PORT, TROJAN_WS_PORT, HYSTERIA2_PORT, SOCKS5_PORT,
        HYSTERIA2_UDP_PORTS, REALITY_SHORT_ID, REALITY_DEST, REALITY_SNI
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger('subscription_service')

SERVER_IP = os.getenv('SERVER_IP', '')
CF_DOMAIN = os.getenv('CF_DOMAIN', '')
DATA_DIR = os.getenv('DATA_DIR', '/root/singbox-manager')
CERT_DIR = os.getenv('CERT_DIR', '/root/singbox-manager/cert')
DB_PATH = os.path.join(DATA_DIR, 'singbox.db')
SUB_PORT = int(os.getenv('SUB_PORT', '2096'))
USE_DOMAIN = bool(CF_DOMAIN and CF_DOMAIN.strip() != '')

VLESS_UUID = os.getenv('VLESS_UUID', '')
VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', '')
VLESS_UPGRADE_PORT = int(os.getenv('VLESS_UPGRADE_PORT', '8445'))
TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
HYSTERIA2_PASSWORD = os.getenv('HYSTERIA2_PASSWORD', '')
REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
EXTERNAL_SUBS = os.getenv('EXTERNAL_SUBS', '')

HYSTERIA2_UDP_PORTS = list(range(21000, 21201))

def init_db():
    """初始化数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cdn_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_cdn_ip():
    """获取CDN优选IP（所有CDN协议共用同一个IP）"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_ip'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row and row[0] else SERVER_IP
    except Exception:
        return SERVER_IP

def get_sub_address():
    """获取订阅服务地址（域名或IP）"""
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN
    return SERVER_IP

def get_ws_address():
    """获取WebSocket节点地址（CDN IP或域名）"""
    cdn_ip = get_cdn_ip()
    if cdn_ip and cdn_ip != SERVER_IP:
        return cdn_ip
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN
    return SERVER_IP

def generate_all_links():
    """生成所有节点链接"""
    cdn_ip = get_cdn_ip()
    sub_addr = get_sub_address()
    ws_addr = get_ws_address()
    links = []

    params = {
        'encryption': 'none',
        'flow': 'xtls-rprx-vision',
        'type': 'tcp',
        'security': 'reality',
        'sni': REALITY_SNI,
        'fp': 'chrome',
        'pbk': REALITY_PUBLIC_KEY[-32:] if (REALITY_PUBLIC_KEY and len(REALITY_PUBLIC_KEY) >= 32) else REALITY_PUBLIC_KEY,
        'sid': REALITY_SHORT_ID,
        'spx': '',
        'dest': REALITY_DEST,
        'headerType': 'none'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_UUID}@{SERVER_IP}:443?{param_str}#ePS-JP-VLESS-Reality")

    params = {
        'encryption': 'none',
        'type': 'ws',
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else ws_addr,
        'path': '/vless-ws',
        'host': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else ws_addr,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{ws_addr}:{VLESS_WS_PORT}?{param_str}#ePS-JP-VLESS-WS")

    params = {
        'encryption': 'none',
        'type': 'httpupgrade',
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else ws_addr,
        'path': '/vless-upgrade',
        'host': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else ws_addr,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{ws_addr}:{VLESS_UPGRADE_PORT}?{param_str}#ePS-JP-VLESS-HTTPUpgrade")

    params = {
        'type': 'ws',
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else ws_addr,
        'path': '/trojan-ws',
        'host': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else ws_addr,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"trojan://{TROJAN_PASSWORD}@{ws_addr}:{TROJAN_WS_PORT}?{param_str}#ePS-JP-Trojan-WS")

    params = {
        'sni': REALITY_SNI,
        'insecure': '1',
        'protocol': 'hysteria2',
        'obfs': 'salamander',
        'obfs-password': HYSTERIA2_PASSWORD[:8]
    }
    hysteria2_port = random.choice(HYSTERIA2_UDP_PORTS)
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"hysteria2://{HYSTERIA2_PASSWORD}@{SERVER_IP}:{hysteria2_port}?{param_str}#ePS-JP-Hysteria2")

    return links

def create_app():
    """创建Flask应用"""
    from flask import Flask, Response, jsonify

    app = Flask(__name__)

    @app.route('/')
    def home():
        server_addr = get_sub_address()
        html = """
        <html>
        <head>
            <title>Singbox订阅服务</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
                h1 { color: #333; }
                .sub-box { background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0; }
                .sub-link { font-size: 18px; color: #0066cc; word-break: break-all; }
                .info { color: #666; font-size: 14px; }
            </style>
        </head>
        <body>
            <h1>Singbox 订阅服务</h1>
            <div class="sub-box">
                <p><strong>订阅链接：</strong></p>
                <p class="sub-link">https://%s:%s/sub</p>
                <p class="info">（包含5个节点：ePS-JP-VLESS-Reality、ePS-JP-VLESS-WS、ePS-JP-VLESS-HTTPUpgrade、ePS-JP-Trojan-WS、ePS-JP-Hysteria2）</p>
            </div>
            <div class="info">
                <p>服务器IP: %s</p>
                <p>域名: %s</p>
                <p>使用域名: %s</p>
            </div>
        </body>
        </html>
        """ % (server_addr, SUB_PORT, SERVER_IP, CF_DOMAIN if CF_DOMAIN else '未配置', '是' if USE_DOMAIN else '否')
        return Response(html, mimetype='text/html')

    @app.route('/sub')
    def get_subscription():
        links = generate_all_links()
        if EXTERNAL_SUBS:
            for sub_url in EXTERNAL_SUBS.split('|'):
                sub_url = sub_url.strip()
                if sub_url:
                    try:
                        req = urllib.request.Request(sub_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            raw = resp.read().decode('utf-8').strip()
                            try:
                                padded_raw = raw + '=' * (-len(raw) % 4)
                                decoded = base64.b64decode(padded_raw).decode('utf-8')
                                links.extend([line for line in decoded.split('\n') if line.strip()])
                            except Exception:
                                links.extend([line for line in raw.split('\n') if line.strip()])
                    except Exception as e:
                        logger.warning(f"合并订阅失败 {sub_url}: {e}")
        content = '\n'.join(links)
        sub = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        return Response(sub, mimetype='text/plain')

    @app.route('/health')
    def health():
        return jsonify({
            'status': 'ok',
            'time': datetime.now().isoformat(),
            'server_ip': SERVER_IP,
            'nodes': 4
        })

    return app

if __name__ == '__main__':
    init_db()
    cert_file = os.path.join(CERT_DIR, 'cert.crt')
    key_file = os.path.join(CERT_DIR, 'cert.key')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    app = create_app()
    logger.info(f"订阅服务启动，监听端口 {SUB_PORT}")
    app.run(host='0.0.0.0', port=SUB_PORT, debug=False, ssl_context=context)
