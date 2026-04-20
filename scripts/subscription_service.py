#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v1.0.4
Date: 2026-04-20
功能：
  - 提供单个Base64订阅链接（包含所有节点）
  - CDN优选IP自动分配（每个协议独立IP）
  - HTTPS协议支持

节点命名规则: ePS-{国家}-{协议}
- ePS-JP-VLESS-Reality (直连节点，苹果域名伪装)
- ePS-JP-VLESS-WS (CDN节点，独立优选IP)
- ePS-JP-VLESS-HTTPUpgrade (CDN节点，独立优选IP)
- ePS-JP-Trojan-WS (CDN节点，独立优选IP)
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
load_dotenv('/root/singbox-eps-node/.env')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, CF_DOMAIN, DATA_DIR, CERT_DIR, DB_FILE, SUB_PORT,
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, HYSTERIA2_PORT, SOCKS5_PORT,
        HYSTERIA2_UDP_PORTS, REALITY_SHORT_ID, REALITY_DEST, REALITY_SNI,
        AI_SOCKS5_SERVER, AI_SOCKS5_PORT, AI_SOCKS5_USER, AI_SOCKS5_PASS,
        SUB_TOKEN
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
# DATA_DIR 从 config.py 统一读取，不再硬编码
DB_PATH = DB_FILE if 'DB_FILE' in dir() else os.path.join(DATA_DIR, 'singbox.db')
SUB_PORT = int(os.getenv('SUB_PORT', '6969'))
SUB_TOKEN = os.getenv('SUB_TOKEN', '')
COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'JP')
USE_DOMAIN = bool(CF_DOMAIN and CF_DOMAIN.strip() != '')

VLESS_UUID = os.getenv('VLESS_UUID', '')
VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', '')
VLESS_UPGRADE_PORT = int(os.getenv('VLESS_UPGRADE_PORT', '2053'))
TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
HYSTERIA2_PASSWORD = os.getenv('HYSTERIA2_PASSWORD', '')
REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
EXTERNAL_SUBS = os.getenv('EXTERNAL_SUBS', '')

HYSTERIA2_UDP_PORTS = list(range(21000, 21201))

def init_db():
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

def get_cdn_ip_for_protocol(protocol_key):
    """获取指定协议的CDN优选IP"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (protocol_key,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0] and row[0] != SERVER_IP:
            return row[0]
    except Exception:
        pass
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN
    return SERVER_IP

def get_sub_address():
    """获取订阅服务地址（域名或IP）"""
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN
    return SERVER_IP

def generate_all_links():
    """生成所有节点链接"""
    links = []

    vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
    vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
    trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')

    use_cdn = (vless_ws_addr != SERVER_IP)
    cdn_suffix = "-CDN" if use_cdn else ""

    # 1. VLESS-Reality (直连)
    params = {
        'encryption': 'none',
        'flow': 'xtls-rprx-vision',
        'type': 'tcp',
        'security': 'reality',
        'sni': REALITY_SNI,
        'fp': 'chrome',
        'pbk': REALITY_PUBLIC_KEY,
        'sid': REALITY_SHORT_ID,
        'spx': '',
        'dest': REALITY_DEST,
        'headerType': 'none'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_UUID}@{SERVER_IP}:443?{param_str}#{COUNTRY_CODE}-VLESS-Reality")

    # 2. VLESS-WS (CDN)
    params = {
        'encryption': 'none',
        'type': 'ws',
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else vless_ws_addr,
        'path': '/vless-ws',
        'host': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else vless_ws_addr,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{vless_ws_addr}:{VLESS_WS_PORT}?{param_str}#{COUNTRY_CODE}-VLESS-WS{cdn_suffix}")

    # 3. VLESS-HTTPUpgrade (CDN)
    params = {
        'encryption': 'none',
        'type': 'httpupgrade',
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else vless_upgrade_addr,
        'path': '/vless-upgrade',
        'host': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else vless_upgrade_addr,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{vless_upgrade_addr}:{VLESS_UPGRADE_PORT}?{param_str}#{COUNTRY_CODE}-VLESS-HTTPUpgrade{cdn_suffix}")

    # 4. Trojan-WS (CDN)
    params = {
        'type': 'ws',
        'security': 'tls',
        'sni': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else trojan_ws_addr,
        'path': '/trojan-ws',
        'host': CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else trojan_ws_addr,
        'allowInsecure': '1'
    }
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"trojan://{TROJAN_PASSWORD}@{trojan_ws_addr}:{TROJAN_WS_PORT}?{param_str}#{COUNTRY_CODE}-Trojan-WS{cdn_suffix}")

    # 5. Hysteria2 (直连)
    params = {
        'sni': REALITY_SNI,
        'insecure': '1',
        'protocol': 'hysteria2',
        'obfs': 'salamander',
        'obfs-password': HYSTERIA2_PASSWORD[:8]
    }
    hysteria2_port = random.choice(HYSTERIA2_UDP_PORTS)
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"hysteria2://{HYSTERIA2_PASSWORD}@{SERVER_IP}:{hysteria2_port}?{param_str}#{COUNTRY_CODE}-Hysteria2")

    # 6. SOCKS5 (AI协议牵制节点)
    # 服务器: 206.163.4.241, 端口: 36753, 用户名: 4KKsLB7F, 密码: KgEKVmVgxJ
    socks5_link = f"socks5://4KKsLB7F:KgEKVmVgxJ@206.163.4.241:36753#AI-SOCKS5"
    links.append(socks5_link)

    return links

def create_app():
    """创建Flask应用"""
    from flask import Flask, Response, jsonify, request

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
                <p class="sub-link">https://%s:%s/%s</p>
                <p class="info">（包含6个节点：ePS-%s-VLESS-Reality、ePS-%s-VLESS-WS、ePS-%s-VLESS-HTTPUpgrade、ePS-%s-Trojan-WS、ePS-%s-Hysteria2、AI-SOCKS5）</p>
            </div>
            <div class="info">
                <p>服务器IP: %s</p>
                <p>域名: %s</p>
                <p>使用域名: %s</p>
            </div>
        </body>
        </html>
        """ % (server_addr, SUB_PORT, SUB_TOKEN, COUNTRY_CODE, COUNTRY_CODE, COUNTRY_CODE, COUNTRY_CODE, COUNTRY_CODE, SERVER_IP, CF_DOMAIN if CF_DOMAIN else '未配置', '是' if USE_DOMAIN else '否')
        return Response(html, mimetype='text/html')

    @app.route(f'/sub/{COUNTRY_CODE}')
    @app.route(f'/{SUB_TOKEN}')
    @app.route('/sub')
    def get_subscription():
        user_agent = request.headers.get('User-Agent', '').lower()
        if 'clash' in user_agent or 'stash' in user_agent or 'shadowrocket' in user_agent:
            return get_clash_subscription()
        links = generate_all_links()
        if EXTERNAL_SUBS and EXTERNAL_SUBS.strip():
            for sub_url in EXTERNAL_SUBS.split('|'):
                sub_url = sub_url.strip()
                if sub_url:
                    try:
                        req = urllib.request.Request(sub_url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            raw = resp.read().decode('utf-8').strip()
                            try:
                                padded_raw = raw + '=' * (-len(raw) % 4)
                                decoded = base64.b64decode(padded_raw).decode('utf-8')
                                links.extend([line for line in decoded.split('\n') if line.strip()])
                            except Exception:
                                links.append(raw)
                    except Exception as e:
                        logger.warning(f"Failed to fetch external sub {sub_url}: {e}")
        sub_text = '\n'.join(links)
        sub_b64 = base64.b64encode(sub_text.encode('utf-8')).decode('utf-8')
        return Response(sub_b64, mimetype='text/plain')

    def get_clash_subscription():
        links = generate_all_links()
        proxies = []
        for link in links:
            try:
                if link.startswith('vless://'):
                    proxy = parse_vless_link(link)
                    if proxy:
                        proxies.append(proxy)
                elif link.startswith('trojan://'):
                    proxy = parse_trojan_link(link)
                    if proxy:
                        proxies.append(proxy)
                elif link.startswith('hysteria2://'):
                    proxy = parse_hysteria2_link(link)
                    if proxy:
                        proxies.append(proxy)
                elif link.startswith('socks5://'):
                    proxy = parse_socks5_link(link)
                    if proxy:
                        proxies.append(proxy)
            except Exception as e:
                logger.warning(f"Failed to parse link: {e}")
        yaml_content = generate_clash_yaml(proxies)
        return Response(yaml_content, mimetype='text/yaml')

    def parse_socks5_link(link):
        try:
            parsed = urllib.parse.urlparse(link)
            username = parsed.username
            password = parsed.password
            host = parsed.hostname
            port = parsed.port
            tag = urllib.parse.unquote(parsed.fragment)
            
            proxy = {
                'name': tag,
                'type': 'socks5',
                'server': host,
                'port': port,
                'username': username,
                'password': password
            }
            return proxy
        except Exception as e:
            logger.warning(f"Failed to parse socks5: {e}")
            return None
        try:
            parsed = urllib.parse.urlparse(link)
            uuid = parsed.username
            host = parsed.hostname
            port = parsed.port
            tag = urllib.parse.unquote(parsed.fragment)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            proxy = {
                'name': tag,
                'type': 'vless',
                'server': host,
                'port': port,
                'uuid': uuid,
                'network': query.get('type', 'tcp'),
                'tls': query.get('security') == 'tls',
                'udp': True,
            }
            if query.get('type') == 'ws':
                proxy['ws-opts'] = {
                    'path': query.get('path', '/'),
                    'headers': {'Host': query.get('host', host)}
                }
            elif query.get('type') == 'httpupgrade':
                proxy['ws-opts'] = {
                    'path': query.get('path', '/'),
                    'headers': {'Host': query.get('host', host)},
                    'v2ray-http-upgrade': True,
                }
            if query.get('security') == 'reality':
                proxy['reality-opts'] = {
                    'public-key': query.get('pbk', ''),
                    'short-id': query.get('sid', ''),
                }
                proxy['server-name'] = query.get('sni', host)
                proxy['client-fingerprint'] = query.get('fp', 'chrome')
            elif query.get('security') == 'tls':
                proxy['servername'] = query.get('sni', host)
                proxy['skip-cert-verify'] = query.get('allowInsecure') == '1'
            return proxy
        except Exception as e:
            logger.warning(f"Failed to parse vless: {e}")
            return None

    def parse_trojan_link(link):
        try:
            parsed = urllib.parse.urlparse(link)
            password = parsed.username
            host = parsed.hostname
            port = parsed.port
            tag = urllib.parse.unquote(parsed.fragment)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            proxy = {
                'name': tag,
                'type': 'trojan',
                'server': host,
                'port': port,
                'password': password,
                'network': query.get('type', 'tcp'),
                'udp': True,
            }
            if query.get('type') == 'ws':
                proxy['ws-opts'] = {
                    'path': query.get('path', '/'),
                    'headers': {'Host': query.get('host', host)}
                }
            proxy['sni'] = query.get('sni', host)
            proxy['skip-cert-verify'] = query.get('allowInsecure') == '1'
            return proxy
        except Exception as e:
            logger.warning(f"Failed to parse trojan: {e}")
            return None

    def parse_hysteria2_link(link):
        try:
            parsed = urllib.parse.urlparse(link)
            password = parsed.username
            host = parsed.hostname
            port = parsed.port
            tag = urllib.parse.unquote(parsed.fragment)
            query = dict(urllib.parse.parse_qsl(parsed.query))
            proxy = {
                'name': tag,
                'type': 'hysteria2',
                'server': host,
                'port': port,
                'password': password,
                'udp': True,
            }
            if query.get('obfs'):
                proxy['obfs'] = query.get('obfs')
                proxy['obfs-password'] = query.get('obfs-password', '')
            proxy['sni'] = query.get('sni', host)
            proxy['skip-cert-verify'] = query.get('insecure') == '1'
            return proxy
        except Exception as e:
            logger.warning(f"Failed to parse hysteria2: {e}")
            return None

    def generate_clash_yaml(proxies):
        yaml = "mixed-port: 7890\nallow-lan: true\nmode: Rule\nlog-level: info\nproxies:\n"
        for p in proxies:
            yaml += f"  - name: \"{p['name']}\"\n"
            yaml += f"    type: {p['type']}\n"
            yaml += f"    server: {p['server']}\n"
            yaml += f"    port: {p['port']}\n"
            if p['type'] == 'vless':
                yaml += f"    uuid: {p['uuid']}\n"
                yaml += f"    network: {p['network']}\n"
                yaml += f"    tls: {str(p['tls']).lower()}\n"
                yaml += f"    udp: {str(p['udp']).lower()}\n"
                if 'ws-opts' in p:
                    yaml += f"    ws-opts:\n"
                    yaml += f"      path: \"{p['ws-opts']['path']}\"\n"
                    yaml += f"      headers:\n"
                    yaml += f"        Host: \"{p['ws-opts']['headers']['Host']}\"\n"
                    if p['ws-opts'].get('v2ray-http-upgrade'):
                        yaml += f"      v2ray-http-upgrade: true\n"
                if 'reality-opts' in p:
                    yaml += f"    reality-opts:\n"
                    yaml += f"      public-key: \"{p['reality-opts']['public-key']}\"\n"
                    yaml += f"      short-id: \"{p['reality-opts']['short-id']}\"\n"
                    yaml += f"    server-name: \"{p.get('server-name', p['server'])}\"\n"
                    yaml += f"    client-fingerprint: \"{p.get('client-fingerprint', 'chrome')}\"\n"
                elif 'servername' in p:
                    yaml += f"    servername: \"{p['servername']}\"\n"
                    yaml += f"    skip-cert-verify: {str(p.get('skip-cert-verify', False)).lower()}\n"
            elif p['type'] == 'trojan':
                yaml += f"    password: \"{p['password']}\"\n"
                yaml += f"    network: {p['network']}\n"
                yaml += f"    udp: {str(p['udp']).lower()}\n"
                if 'ws-opts' in p:
                    yaml += f"    ws-opts:\n"
                    yaml += f"      path: \"{p['ws-opts']['path']}\"\n"
                    yaml += f"      headers:\n"
                    yaml += f"        Host: \"{p['ws-opts']['headers']['Host']}\"\n"
                yaml += f"    sni: \"{p.get('sni', p['server'])}\"\n"
                yaml += f"    skip-cert-verify: {str(p.get('skip-cert-verify', False)).lower()}\n"
            elif p['type'] == 'socks5':
                yaml += f"    username: \"{p['username']}\"\n"
                yaml += f"    password: \"{p['password']}\"\n"
            elif p['type'] == 'hysteria2':
                yaml += f"    password: \"{p['password']}\"\n"
                yaml += f"    udp: {str(p['udp']).lower()}\n"
                if 'obfs' in p:
                    yaml += f"    obfs: \"{p['obfs']}\"\n"
                    yaml += f"    obfs-password: \"{p['obfs-password']}\"\n"
                yaml += f"    sni: \"{p.get('sni', p['server'])}\"\n"
                yaml += f"    skip-cert-verify: {str(p.get('skip-cert-verify', False)).lower()}\n"
        yaml += "proxy-groups:\n"
        yaml += "  - name: \"ePS-Auto\"\n"
        yaml += "    type: url-test\n"
        yaml += "    proxies:\n"
        for p in proxies:
            yaml += f"      - \"{p['name']}\"\n"
        yaml += "    url: http://www.gstatic.com/generate_204\n"
        yaml += "    interval: 300\n"
        yaml += "rules:\n"
        yaml += "  - MATCH,ePS-Auto\n"
        return yaml

    @app.route('/api/cdn', methods=['GET', 'POST'])
    def cdn_api():
        if request.method == 'POST':
            data = request.get_json()
            protocol = data.get('protocol', '').strip()
            new_ip = data.get('ip', '').strip()
            if not protocol or not new_ip:
                return jsonify({'error': 'protocol and ip required'}), 400
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (protocol, new_ip))
                conn.commit()
                conn.close()
                return jsonify({'message': 'OK', 'protocol': protocol, 'ip': new_ip})
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        else:
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM cdn_settings")
                rows = cursor.fetchall()
                conn.close()
                result = {row[0]: row[1] for row in rows}
                return jsonify(result)
            except Exception as e:
                return jsonify({'error': str(e)}), 500

    return app

if __name__ == '__main__':
    init_db()
    app = create_app()
    
    # 尝试多个可能的证书路径
    cert_paths = [
        os.path.join(CERT_DIR, 'cert.pem'),
        os.path.join(os.path.dirname(CERT_DIR), 'certs', 'cert.pem'),
        '/root/singbox-eps-node/cert/cert.pem',
        '/root/singbox-eps-node/certs/cert.pem',
        '/root/singbox-manager/cert/cert.pem',
    ]
    
    key_paths = [
        os.path.join(CERT_DIR, 'key.pem'),
        os.path.join(os.path.dirname(CERT_DIR), 'certs', 'key.pem'),
        '/root/singbox-eps-node/cert/key.pem',
        '/root/singbox-eps-node/certs/key.pem',
        '/root/singbox-manager/cert/key.pem',
    ]
    
    cert_found = False
    for cert_path, key_path in zip(cert_paths, key_paths):
        if os.path.exists(cert_path) and os.path.exists(key_path):
            logger.info(f"SSL certificate found at: {cert_path}")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert_path, key_path)
            logger.info(f"Starting HTTPS subscription service on 0.0.0.0:{SUB_PORT}")
            app.run(host='0.0.0.0', port=SUB_PORT, ssl_context=context, threaded=True)
            cert_found = True
            break
    
    if not cert_found:
        logger.warning("SSL cert not found in any location, running HTTP subscription service")
        logger.warning("Subscription URL: http://SERVER_IP:{SUB_PORT}/sub")
        logger.warning("Subscription URL: http://SERVER_IP:{SUB_PORT}/sub/{COUNTRY_CODE}")
        logger.warning("Subscription URL: http://SERVER_IP:{SUB_PORT}/{SUB_TOKEN}")
        app.run(host='0.0.0.0', port=SUB_PORT, threaded=True)
