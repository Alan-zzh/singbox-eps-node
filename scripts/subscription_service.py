#!/usr/bin/env python3
"""
订阅服务 - Flask应用
Author: Alan
Version: v2.0.0
Date: 2026-04-23
"""

import os
import sys
import base64
import urllib.parse
import urllib.request
import sqlite3
import json
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, CF_DOMAIN, DATA_DIR, CERT_DIR, DB_FILE, SUB_PORT,
        VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, HYSTERIA2_PORT, SOCKS5_PORT,
        REALITY_SHORT_ID, REALITY_DEST, REALITY_SNI,
        AI_SOCKS5_SERVER, AI_SOCKS5_PORT, AI_SOCKS5_USER, AI_SOCKS5_PASS,
        get_sub_domain, BASE_DIR
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)
    SERVER_IP = os.getenv('SERVER_IP', '')
    CF_DOMAIN = os.getenv('CF_DOMAIN', '')
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    CERT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cert')
    DB_FILE = os.path.join(DATA_DIR, 'singbox.db')
    SUB_PORT = int(os.getenv('SUB_PORT', '2087'))
    VLESS_WS_PORT = int(os.getenv('VLESS_WS_PORT', '8443'))
    VLESS_UPGRADE_PORT = int(os.getenv('VLESS_UPGRADE_PORT', '2053'))
    TROJAN_WS_PORT = int(os.getenv('TROJAN_WS_PORT', '2083'))
    HYSTERIA2_PORT = int(os.getenv('HYSTERIA2_PORT', '443'))
    SOCKS5_PORT = int(os.getenv('SOCKS5_PORT', '1080'))
    REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
    REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
    REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
    AI_SOCKS5_SERVER = os.getenv('AI_SOCKS5_SERVER', '')
    AI_SOCKS5_PORT = os.getenv('AI_SOCKS5_PORT', '')
    AI_SOCKS5_USER = os.getenv('AI_SOCKS5_USER', '')
    AI_SOCKS5_PASS = os.getenv('AI_SOCKS5_PASS', '')
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    def get_sub_domain():
        return CF_DOMAIN if CF_DOMAIN else SERVER_IP

logger = get_logger('subscription_service')

SERVER_IP = SERVER_IP if SERVER_IP else os.getenv('SERVER_IP', '')
CF_DOMAIN = CF_DOMAIN if CF_DOMAIN else os.getenv('CF_DOMAIN', '')
DB_PATH = DB_FILE if 'DB_FILE' in dir() else os.path.join(DATA_DIR, 'singbox.db')
COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'US')
USE_DOMAIN = bool(CF_DOMAIN and CF_DOMAIN.strip() != '')

VLESS_UUID = os.getenv('VLESS_UUID', '')
VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', '')
VLESS_UPGRADE_PORT = VLESS_UPGRADE_PORT if 'VLESS_UPGRADE_PORT' in dir() else int(os.getenv('VLESS_UPGRADE_PORT', '2053'))
TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
HYSTERIA2_PASSWORD = os.getenv('HYSTERIA2_PASSWORD', '')
REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
EXTERNAL_SUBS = os.getenv('EXTERNAL_SUBS', '')
SUB_TOKEN = os.getenv('SUB_TOKEN', '')

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS cdn_settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS traffic_stats (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
    finally:
        if conn:
            conn.close()

def update_traffic(bytes_count):
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    today_str = now.strftime('%Y-%m-%d')
    need_reset = False
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM traffic_stats")
        stats = {row[0]: row[1] for row in cursor.fetchall()}
        stored_month = stats.get('current_month', '')
        stored_bytes = int(stats.get('current_bytes', '0'))
        last_reset = stats.get('last_reset', '')
        if stored_month != current_month:
            need_reset = True
        elif now.day == 14 and not last_reset.startswith(current_month):
            need_reset = True
        if need_reset:
            stored_bytes = 0
            cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)", ('current_month', current_month))
            cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)", ('last_reset', today_str))
        new_bytes = stored_bytes + bytes_count
        cursor.execute("INSERT OR REPLACE INTO traffic_stats (key, value) VALUES (?, ?)", ('current_bytes', str(new_bytes)))
        conn.commit()
    except Exception as e:
        logger.error(f"流量统计更新失败: {e}")
    finally:
        if conn:
            conn.close()

def get_traffic_stats():
    now = datetime.now()
    current_month = now.strftime('%Y-%m')
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM traffic_stats")
        stats = {row[0]: row[1] for row in cursor.fetchall()}
        stored_month = stats.get('current_month', '')
        stored_bytes = int(stats.get('current_bytes', '0'))
        last_reset = stats.get('last_reset', '')
        if stored_month != current_month:
            stored_bytes = 0
            last_reset = ''
        return {'month': current_month, 'bytes_used': stored_bytes, 'mb_used': round(stored_bytes / (1024 * 1024), 2), 'gb_used': round(stored_bytes / (1024 * 1024 * 1024), 2), 'reset_day': 14, 'last_reset': last_reset}
    except Exception as e:
        logger.error(f"流量统计读取失败: {e}")
        return {'month': current_month, 'bytes_used': 0, 'mb_used': 0.0, 'gb_used': 0.0, 'reset_day': 14, 'last_reset': ''}
    finally:
        if conn:
            conn.close()

def format_traffic(bytes_count):
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.2f} KB"
    elif bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"

def get_cdn_ip_for_protocol(protocol_key):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (protocol_key,))
        row = cursor.fetchone()
        if row and row[0] and row[0] != SERVER_IP:
            return row[0]
    except Exception:
        pass
    finally:
        if conn:
            conn.close()
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN
    return SERVER_IP

def get_sub_address():
    return get_sub_domain()

def generate_all_links():
    links = []
    vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
    vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
    trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
    use_cdn = (vless_ws_addr != SERVER_IP)
    cdn_suffix = "-CDN" if use_cdn else ""
    cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
    params = {'encryption': 'none', 'flow': 'xtls-rprx-vision', 'type': 'tcp', 'security': 'reality', 'sni': REALITY_SNI, 'fp': 'chrome', 'pbk': REALITY_PUBLIC_KEY, 'sid': REALITY_SHORT_ID, 'spx': '', 'dest': REALITY_DEST, 'headerType': 'none'}
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_UUID}@{SERVER_IP}:443?{param_str}#{COUNTRY_CODE}-VLESS-Reality")
    params = {'encryption': 'none', 'type': 'ws', 'security': 'tls', 'sni': cdn_sni, 'path': '/vless-ws', 'host': cdn_sni, 'allowInsecure': '1'}
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{vless_ws_addr}:{VLESS_WS_PORT}?{param_str}#{COUNTRY_CODE}-VLESS-WS{cdn_suffix}")
    params = {'encryption': 'none', 'type': 'httpupgrade', 'security': 'tls', 'sni': cdn_sni, 'path': '/vless-upgrade', 'host': cdn_sni, 'allowInsecure': '1'}
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
    links.append(f"vless://{VLESS_WS_UUID}@{vless_upgrade_addr}:{VLESS_UPGRADE_PORT}?{param_str}#{COUNTRY_CODE}-VLESS-HTTPUpgrade{cdn_suffix}")
    params = {'type': 'ws', 'security': 'tls', 'sni': cdn_sni, 'insecure': '1', 'allowInsecure': '1', 'path': '/trojan-ws', 'host': cdn_sni}
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in params.items() if v])
    links.append(f"trojan://{TROJAN_PASSWORD}@{trojan_ws_addr}:{TROJAN_WS_PORT}?{param_str}#{COUNTRY_CODE}-Trojan-WS{cdn_suffix}")
    params = {'sni': REALITY_SNI, 'insecure': '1', 'obfs': 'salamander', 'obfs-password': HYSTERIA2_PASSWORD[:8], 'mport': '443,21000-21200'}
    param_str = '&'.join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items() if v])
    links.append(f"hysteria2://{HYSTERIA2_PASSWORD}@{SERVER_IP}:443?{param_str}#{COUNTRY_CODE}-Hysteria2")
    return links

def generate_singbox_config():
    vless_ws_addr = get_cdn_ip_for_protocol('vless_ws_cdn_ip')
    vless_upgrade_addr = get_cdn_ip_for_protocol('vless_upgrade_cdn_ip')
    trojan_ws_addr = get_cdn_ip_for_protocol('trojan_ws_cdn_ip')
    cdn_sni = CF_DOMAIN if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
    config = {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {"tag": "dns_proxy", "address": "tls://8.8.8.8", "detour": "direct"},
                {"tag": "dns_direct", "address": "h3://dns.alidns.com/dns-query", "detour": "direct"},
                {"tag": "dns_block", "address": "rcode://success"},
                {"tag": "dns_fakeip", "address": "fakeip"}
            ],
            "rules": [
                {"outbound": "any", "server": "dns_direct"},
                {"rule_set": "geosite-cn", "server": "dns_direct"},
                {"rule_set": "geosite-geolocation-!cn", "server": "dns_proxy"}
            ],
            "rule_set": [
                {"tag": "geosite-cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs"},
                {"tag": "geosite-geolocation-!cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-!cn.srs"}
            ],
            "final": "dns_proxy",
            "fakeip": {"enabled": True, "inet4_range": "198.18.0.0/15"}
        },
        "inbounds": [
            {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080},
            {"type": "tun", "tag": "tun-in", "inet4_address": "172.19.0.1/30", "auto_route": True, "strict_route": True, "stack": "mixed"}
        ],
        "outbounds": [
            {"type": "selector", "tag": "ePS-Auto", "outbounds": [f"{COUNTRY_CODE}-VLESS-Reality", f"{COUNTRY_CODE}-VLESS-WS", f"{COUNTRY_CODE}-VLESS-HTTPUpgrade", f"{COUNTRY_CODE}-Trojan-WS", f"{COUNTRY_CODE}-Hysteria2", "direct"], "default": f"{COUNTRY_CODE}-VLESS-Reality"},
        ] + ([{"type": "selector", "tag": "ai-residential", "outbounds": ["AI-SOCKS5", "direct"], "default": "AI-SOCKS5"}] if AI_SOCKS5_SERVER and AI_SOCKS5_PORT else []) + [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
            {"type": "dns", "tag": "dns-out"},
            {"type": "vless", "tag": f"{COUNTRY_CODE}-VLESS-Reality", "server": SERVER_IP, "server_port": 443, "uuid": VLESS_UUID, "flow": "xtls-rprx-vision", "packet_encoding": "xudp", "tls": {"enabled": True, "server_name": REALITY_SNI, "utls": {"enabled": True, "fingerprint": "chrome"}, "reality": {"enabled": True, "public_key": REALITY_PUBLIC_KEY, "short_id": REALITY_SHORT_ID}}},
            {"type": "vless", "tag": f"{COUNTRY_CODE}-VLESS-WS", "server": vless_ws_addr, "server_port": VLESS_WS_PORT, "uuid": VLESS_WS_UUID, "packet_encoding": "xudp", "tls": {"enabled": True, "server_name": cdn_sni, "insecure": True, "utls": {"enabled": True, "fingerprint": "chrome"}}, "transport": {"type": "ws", "path": "/vless-ws", "headers": {"Host": cdn_sni}}},
            {"type": "vless", "tag": f"{COUNTRY_CODE}-VLESS-HTTPUpgrade", "server": vless_upgrade_addr, "server_port": VLESS_UPGRADE_PORT, "uuid": VLESS_WS_UUID, "packet_encoding": "xudp", "tls": {"enabled": True, "server_name": cdn_sni, "insecure": True, "utls": {"enabled": True, "fingerprint": "chrome"}}, "transport": {"type": "httpupgrade", "path": "/vless-upgrade", "host": cdn_sni}},
            {"type": "trojan", "tag": f"{COUNTRY_CODE}-Trojan-WS", "server": trojan_ws_addr, "server_port": TROJAN_WS_PORT, "password": TROJAN_PASSWORD, "tls": {"enabled": True, "server_name": cdn_sni, "insecure": True}, "transport": {"type": "ws", "path": "/trojan-ws", "headers": {"Host": cdn_sni}}},
            {"type": "hysteria2", "tag": f"{COUNTRY_CODE}-Hysteria2", "server": SERVER_IP, "server_port": 443, "hop_ports": "21000-21200", "password": HYSTERIA2_PASSWORD, "tls": {"enabled": True, "server_name": REALITY_SNI, "insecure": True}, "obfs": {"type": "salamander", "password": HYSTERIA2_PASSWORD[:8]}, "up_mbps": 100, "down_mbps": 100},
            {"type": "socks", "tag": "AI-SOCKS5", "server": AI_SOCKS5_SERVER, "server_port": AI_SOCKS5_PORT, "version": "5", "username": AI_SOCKS5_USER, "password": AI_SOCKS5_PASS} if AI_SOCKS5_SERVER and AI_SOCKS5_PORT else None
        ],
        "route": {
            "rules": [
                {"protocol": "dns", "outbound": "dns-out"},
                {"ip_is_private": True, "outbound": "direct"},
                {"rule_set": ["geosite-cn", "geoip-cn"], "outbound": "direct"},
                {"domain_suffix": ["x.com", "twitter.com", "twimg.com", "t.co", "x.ai", "grok.com"], "domain_keyword": ["twitter", "grok"], "outbound": "ePS-Auto"},
                {
                    "domain_suffix": [
                        "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
                        "gemini.google.com", "bard.google.com", "ai.google",
                        "aistudio.google.com", "perplexity.ai", "midjourney.com",
                        "stability.ai", "cohere.com", "replicate.com",
                        "kimi.moonshot.cn", "deepseek.com",
                        "cerebras.net", "inflection.ai", "mistral.ai",
                        "meta.ai", "openai.org", "chat.openai.com",
                        "api.openai.com", "platform.openai.com", "playground.openai.com"
                    ],
                    "domain_keyword": ["openai", "anthropic", "claude", "gemini", "perplexity", "aistudio", "chatgpt"],
                    "domain": ["gemini.google.com"],
                    "outbound": "ai-residential"
                }
            ],
            "rule_set": [
                {"tag": "geosite-cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-cn.srs"},
                {"tag": "geoip-cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geoip/rule-set/geoip-cn.srs"},
                {"tag": "geosite-geolocation-!cn", "type": "remote", "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-!cn.srs"}
            ],
            "auto_detect_interface": True,
            "final": "ePS-Auto"
        },
        "experimental": {
            "cache_file": {"enabled": True},
            "clash_api": {"external_controller": "127.0.0.1:9090", "external_ui": "dashboard"}
        }
    }
    config["outbounds"] = [ob for ob in config["outbounds"] if ob is not None]
    return config

def create_app():
    from flask import Flask, Response, jsonify, request
    app = Flask(__name__)
    @app.route('/')
    def home():
        traffic = get_traffic_stats()
        traffic_display = format_traffic(traffic['bytes_used'])
        html = f"""<html><head><title>Singbox订阅服务</title><style>body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}</style></head><body><h1>Singbox 订阅服务</h1><p>当月流量: {traffic_display}</p><p>Base64订阅: https://{CF_DOMAIN or SERVER_IP}:{SUB_PORT}/sub/{COUNTRY_CODE}</p><p>sing-box JSON: https://{CF_DOMAIN or SERVER_IP}:{SUB_PORT}/singbox/{COUNTRY_CODE}</p></body></html>"""
        return Response(html, mimetype='text/html')
    @app.route(f'/sub/{COUNTRY_CODE}')
    @app.route('/sub')
    def get_subscription():
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
        update_traffic(len(sub_b64.encode('utf-8')))
        traffic = get_traffic_stats()
        userinfo = f"upload=0; download={traffic['bytes_used']}; total=-1; expire=0"
        return Response(sub_b64, mimetype='text/plain', headers={'subscription-userinfo': userinfo})
    @app.route(f'/singbox/{COUNTRY_CODE}')
    @app.route('/singbox')
    def get_singbox_config():
        config = generate_singbox_config()
        config_json = json.dumps(config, indent=2, ensure_ascii=False)
        update_traffic(len(config_json.encode('utf-8')))
        traffic = get_traffic_stats()
        userinfo = f"upload=0; download={traffic['bytes_used']}; total=-1; expire=0"
        return Response(config_json, mimetype='application/json', headers={'Content-Disposition': 'attachment; filename=singbox-config.json', 'subscription-userinfo': userinfo})
    @app.route('/api/traffic')
    def traffic_api():
        return jsonify(get_traffic_stats())
    @app.route('/api/cdn', methods=['GET', 'POST'])
    def cdn_api():
        if request.method == 'POST':
            data = request.get_json()
            protocol = data.get('protocol', '').strip()
            new_ip = data.get('ip', '').strip()
            if not protocol or not new_ip:
                return jsonify({'error': 'protocol and ip required'}), 400
            import re
            if not re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$').match(new_ip):
                return jsonify({'error': 'Invalid IP format'}), 400
            valid_keys = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']
            if protocol not in valid_keys:
                return jsonify({'error': 'Invalid protocol key'}), 400
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (protocol, new_ip))
                conn.commit()
                return jsonify({'message': 'OK', 'protocol': protocol, 'ip': new_ip})
            except Exception as e:
                logger.error(f"CDN API错误: {e}")
                return jsonify({'error': 'Internal server error'}), 500
            finally:
                if conn:
                    conn.close()
        else:
            conn = None
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM cdn_settings")
                rows = cursor.fetchall()
                return jsonify({row[0]: row[1] for row in rows})
            except Exception as e:
                logger.error(f"CDN API错误: {e}")
                return jsonify({'error': 'Internal server error'}), 500
            finally:
                if conn:
                    conn.close()
    return app

if __name__ == '__main__':
    init_db()
    try:
        from config import verify_port_integrity, save_port_lock
        is_valid, msg = verify_port_integrity()
        if not is_valid:
            logger.warning(f"端口完整性校验失败: {msg}")
            save_port_lock()
    except Exception as e:
        logger.warning(f"端口校验异常: {e}")
    sub_domain = get_sub_domain()
    app = create_app()
    logger.info(f"Starting HTTPS subscription service on 0.0.0.0:{SUB_PORT}")
    logger.info(f"Base64订阅: https://{sub_domain}:{SUB_PORT}/sub/{COUNTRY_CODE}")
    logger.info(f"sing-box JSON: https://{sub_domain}:{SUB_PORT}/singbox/{COUNTRY_CODE}")
    cert_chain = os.path.join(CERT_DIR, 'fullchain.pem')
    cert_key = os.path.join(CERT_DIR, 'key.pem')
    if not os.path.exists(cert_chain):
        cert_chain = os.path.join(CERT_DIR, 'cert.pem')
    if not os.path.exists(cert_key):
        cert_key = os.path.join(CERT_DIR, 'key.pem')
    if not os.path.exists(cert_chain) or not os.path.exists(cert_key):
        logger.error(f"SSL证书文件不存在: {cert_chain} 或 {cert_key}")
        sys.exit(1)
    logger.info(f"SSL证书: {cert_chain}")
    app.run(host='0.0.0.0', port=SUB_PORT, threaded=True, ssl_context=(cert_chain, cert_key))