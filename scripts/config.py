#!/usr/bin/env python3
"""
统一配置模块
Author: Alan
Version: v1.0.60
Date: 2026-04-21
功能：集中管理所有配置参数

【⚠️ 端口锁定声明 - 严禁修改】
以下端口号已硬编码锁定，任何AI或程序不得擅自修改：
  SUB_PORT = 2087  （订阅服务端口，已固定，走CDN）
  SINGBOX_PORT = 443
  VLESS_WS_PORT = 8443
  VLESS_UPGRADE_PORT = 2053
  TROJAN_WS_PORT = 2083
  HYSTERIA2_PORT = 443
修改端口号必须由用户明确指令，否则视为违规操作。
历史教训：
  - v1.0.42之前默认端口6969导致防火墙不匹配、服务不可达
  - v1.0.43使用9443端口，但SSL证书颁发给域名，
    用IP访问时证书域名不匹配，V2rayN等客户端拒绝连接。
    9443不在Cloudflare CDN代理端口列表中，无法通过域名走CDN。
  - v1.0.44改用2087端口（CDN支持），通过域名访问解决证书匹配问题。
"""

import os
import json
import hashlib
import subprocess

# 自动检测当前脚本所在目录作为BASE_DIR
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT_DIR = os.path.join(BASE_DIR, 'cert')
DATA_DIR = os.path.join(BASE_DIR, 'data')
GEO_DIR = os.path.join(BASE_DIR, 'geo')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
ENV_FILE = os.path.join(BASE_DIR, '.env')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DB_FILE = os.path.join(DATA_DIR, 'singbox.db')
PORT_LOCK_FILE = os.path.join(DATA_DIR, '.port_lock')


def _detect_server_ip():
    """自动检测服务器公网IP"""
    for url in ['https://api.ipify.org', 'https://ifconfig.me/ip', 'https://icanhazip.com']:
        try:
            result = subprocess.run(
                ['curl', '-s', '--connect-timeout', '5', url],
                capture_output=True, text=True, timeout=10
            )
            ip = result.stdout.strip()
            if ip and len(ip.split('.')) == 4:
                return ip
        except Exception:
            continue
    return ''


def _load_env_value(key, default=''):
    """从.env文件读取指定key的值"""
    try:
        with open(ENV_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    if k.strip() == key:
                        return v.strip()
    except Exception:
        pass
    return default


SERVER_IP = os.getenv('SERVER_IP', '') or _load_env_value('SERVER_IP', '') or _detect_server_ip()
CF_DOMAIN = os.getenv('CF_DOMAIN', '') or _load_env_value('CF_DOMAIN', '')

# ============================================================
# 【硬编码端口 - 严禁修改】锁定值，不从环境变量读取
# 历史教训：
#   v1.0.42前默认值6969导致防火墙不匹配
#   v1.0.43用9443但CDN不支持，证书域名不匹配
#   v1.0.44改用2087（CDN支持端口），域名访问证书匹配
# 修改这些值必须同步更新：1.iptables  2..env  3.port_lock  4.CDN源站规则
# ============================================================
SUB_PORT = 2087
SINGBOX_PORT = 443
VLESS_WS_PORT = 8443
VLESS_UPGRADE_PORT = 2053
TROJAN_WS_PORT = 2083
HYSTERIA2_PORT = 443
SOCKS5_PORT = 1080

LOCKED_PORTS = {
    'SUB_PORT': SUB_PORT,
    'SINGBOX_PORT': SINGBOX_PORT,
    'VLESS_WS_PORT': VLESS_WS_PORT,
    'VLESS_UPGRADE_PORT': VLESS_UPGRADE_PORT,
    'TROJAN_WS_PORT': TROJAN_WS_PORT,
    'HYSTERIA2_PORT': HYSTERIA2_PORT,
    'SOCKS5_PORT': SOCKS5_PORT,
}

SUB_TOKEN = os.getenv('SUB_TOKEN', '')
COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'US')

HYSTERIA2_UDP_PORTS = list(range(21000, 21201))

# ⚠️ HY2规避配置说明（必须完整保留，禁止删减任何一项）：
# 1. obfs=salamander：规避QUIC/UDP流量特征检测
# 2. obfs-password：取HY2密码前8位，必须与singbox配置一致
# 3. 端口跳跃21000-21200：iptables DNAT转发到443，扩大端口范围规避封锁
# 4. mport参数：客户端使用的多端口范围，必须与iptables规则一致
# 5. alpn=["h3"]：HY2使用QUIC协议，必须设置h3
# 6. ⚠️ 端口跳跃必须同时设置UDP和TCP规则（双协议保障）：
#    - UDP：HY2核心协议(QUIC)，主要流量走UDP
#    - TCP：降级兜底，UDP被封或不稳定时HY2可降级使用TCP
#    - 禁止只设UDP或只设TCP，必须双协议，否则一种被封则HY2完全不可用
#    - 历史教训：v1.0.45曾错误移除TCP规则，导致UDP被封时HY2无兜底

REALITY_SHORT_ID = 'abcd1234'
REALITY_DEST = 'www.apple.com:443'
REALITY_SNI = 'www.apple.com'

CDN_DB_URL = 'https://api.uouin.com/cloudflare.html'
CDN_MONITOR_INTERVAL = 3600
CDN_TOP_IPS_COUNT = 5

# 湖南电信实测最优Cloudflare优选IP池（唯一真相源）
# ⚠️ 修改此列表必须同步更新cdn_monitor.py的import
# 排序规则：按湖南电信实测延迟从低到高排列
# 更新来源：https://api.uouin.com/cloudflare.html 电信排名
# 自动更换机制：cdn_monitor每小时TCPing验证，IP不可达自动替换下一个
CDN_PREFERRED_IPS = [
    '162.159.45.66',
    '162.159.39.48',
    '172.64.53.253',
    '162.159.44.192',
    '172.64.52.244',
    '162.159.38.190',
    '108.162.198.29',
    '162.159.15.207',
    '162.159.19.243',
    '162.159.58.128',
    '162.159.38.180',
    '108.162.198.116',
    '172.64.53.134',
    '162.159.39.89',
    '162.159.45.244',
    '162.159.44.128',
    '172.64.52.173',
    '172.64.33.166',
    '172.64.53.179',
    '172.64.52.205',
    '108.162.198.145',
    '104.16.123.96',
    '104.16.124.96',
    '104.17.136.90',
]

# CDN优选IP外部API（降级方案，本地池不可用时自动切换）
CDN_API_WETEST_CT = 'ct.cloudflare.182682.xyz'
CDN_API_IPDB = 'https://ipdb.api.030101.xyz/?type=bestcf'
CDN_API_001315_CT = 'https://cf.001315.xyz/ct'

CERT_VALIDITY_DAYS = 365

AI_SOCKS5_SERVER = os.getenv('AI_SOCKS5_SERVER', '')
AI_SOCKS5_PORT = int(os.getenv('AI_SOCKS5_PORT', '0')) if os.getenv('AI_SOCKS5_PORT') else 0
AI_SOCKS5_USER = os.getenv('AI_SOCKS5_USER', '')
AI_SOCKS5_PASS = os.getenv('AI_SOCKS5_PASS', '')

NODE_PREFIX = f'ePS-{COUNTRY_CODE}'


def _compute_port_checksum():
    """计算端口配置的校验和，用于防篡改检测"""
    port_str = json.dumps(LOCKED_PORTS, sort_keys=True)
    return hashlib.sha256(port_str.encode()).hexdigest()


def save_port_lock():
    """保存端口锁定文件（持久化存储）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    lock_data = {
        'ports': LOCKED_PORTS,
        'checksum': _compute_port_checksum(),
        'locked_at': str(os.popen('date -Iseconds 2>/dev/null || date').read().strip()),
        'locked_by': 'config.py v1.0.4',
        'warning': '此文件由系统自动生成，严禁手动修改。修改端口必须通过config.py并重新生成此文件。'
    }
    with open(PORT_LOCK_FILE, 'w') as f:
        json.dump(lock_data, f, indent=2)
    return lock_data


def verify_port_integrity():
    """验证端口配置完整性（防篡改检测）
    返回: (是否完整, 错误信息)
    """
    if not os.path.exists(PORT_LOCK_FILE):
        return False, '端口锁定文件不存在，请运行 save_port_lock() 生成'

    try:
        with open(PORT_LOCK_FILE, 'r') as f:
            lock_data = json.load(f)
    except Exception as e:
        return False, f'端口锁定文件损坏: {e}'

    saved_ports = lock_data.get('ports', {})
    saved_checksum = lock_data.get('checksum', '')

    for name, expected_port in LOCKED_PORTS.items():
        actual_port = saved_ports.get(name)
        if actual_port != expected_port:
            return False, f'端口{name}被篡改: 锁定值={expected_port}, 当前值={actual_port}'

    current_checksum = _compute_port_checksum()
    if current_checksum != saved_checksum:
        return False, f'端口校验和不匹配: 锁定={saved_checksum[:16]}..., 当前={current_checksum[:16]}...'

    return True, '端口配置完整性验证通过'


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
    return _load_env_value(key, default)


def get_sub_domain():
    """获取订阅服务访问域名（优先域名，无域名则用IP）
    ⚠️ HTTPS订阅服务必须用域名访问（SSL证书颁发给域名）
    如果没有配置域名，返回IP（此时客户端需跳过证书验证）
    """
    if CF_DOMAIN and CF_DOMAIN.strip():
        return CF_DOMAIN.strip()
    return SERVER_IP


def load_all_config():
    """加载所有配置"""
    config = {
        'server_ip': get_env('SERVER_IP', SERVER_IP),
        'cf_domain': get_env('CF_DOMAIN', CF_DOMAIN),
        'sub_port': SUB_PORT,
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
