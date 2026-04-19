#!/usr/bin/env python3
"""
统一配置模块
Author: Alan
Version: v1.0.3
Date: 2026-04-20
功能：集中管理所有配置参数
"""

import os

# 路径配置
BASE_DIR = '/root/singbox-manager'
CERT_DIR = os.path.join(BASE_DIR, 'cert')
DATA_DIR = BASE_DIR
GEO_DIR = os.path.join(BASE_DIR, 'geo')
LOG_DIR = '/var/log'
ENV_FILE = os.path.join(BASE_DIR, '.env')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DB_FILE = os.path.join(DATA_DIR, 'singbox.db')

# 服务器配置 - 必须从环境变量读取
SERVER_IP = os.getenv('SERVER_IP', '')
CF_DOMAIN = os.getenv('CF_DOMAIN', '')

# 服务端口配置
SUB_PORT = 2096
SINGBOX_PORT = 443
VLESS_WS_PORT = 8443
VLESS_UPGRADE_PORT = 8445
TROJAN_WS_PORT = 8444
HYSTERIA2_PORT = 4433
SOCKS5_PORT = 1080

# Hysteria2 端口跳跃配置 (直连，不走CDN)
HYSTERIA2_UDP_PORTS = list(range(21000, 21201))

# Reality 配置
REALITY_SHORT_ID = 'abcd1234'
REALITY_DEST = 'www.apple.com:443'
REALITY_SNI = 'www.apple.com'

# CDN 配置
CDN_DB_URL = 'https://api.uouin.com/cloudflare.html'
CDN_MONITOR_INTERVAL = 3600
CDN_TOP_IPS_COUNT = 5

# 证书配置
CERT_VALIDITY_DAYS = 365

# 节点命名规则: ePS-{国家}-{协议}
NODE_PREFIX = 'ePS-JP'

def get_node_name(protocol):
    """生成节点名称"""
    names = {
        'vless-reality': f'{NODE_PREFIX}-VLESS-Reality',
        'vless-ws': f'{NODE_PREFIX}-VLESS-WS',
        'trojan-ws': f'{NODE_PREFIX}-Trojan-WS',
        'hysteria2': f'{NODE_PREFIX}-Hysteria2',
        'socks5': f'{NODE_PREFIX}-SOCKS5'
    }
    return names.get(protocol, f'{NODE_PREFIX}-{protocol}')

def get_env(key, default=''):
    """从环境文件读取配置"""
    try:
        with open(ENV_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    if k == key:
                        return v.strip()
    except Exception:
        pass
    return default

def load_all_config():
    """加载所有配置"""
    config = {
        'server_ip': get_env('SERVER_IP', SERVER_IP),
        'cf_domain': get_env('CF_DOMAIN', CF_DOMAIN),
        'sub_port': int(get_env('SUB_PORT', str(SUB_PORT))),
        'vless_uuid': get_env('VLESS_UUID', ''),
        'vless_ws_uuid': get_env('VLESS_WS_UUID', ''),
        'trojan_password': get_env('TROJAN_PASSWORD', ''),
        'hysteria2_password': get_env('HYSTERIA2_PASSWORD', ''),
        'socks5_user': get_env('SOCKS5_USER', ''),
        'socks5_pass': get_env('SOCKS5_PASS', ''),
        'reality_private_key': get_env('REALITY_PRIVATE_KEY', ''),
        'reality_public_key': get_env('REALITY_PUBLIC_KEY', ''),
        'reality_short_id': get_env('REALITY_SHORT_ID', REALITY_SHORT_ID),
        'reality_dest': get_env('REALITY_DEST', REALITY_DEST),
        'reality_sni': get_env('REALITY_SNI', REALITY_SNI),
    }
    return config
