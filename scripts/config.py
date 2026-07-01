#!/usr/bin/env python3
"""
统一配置模块
Author: Alan
Version: v4.14.0
Date: 2026-06-27
功能：集中管理所有配置参数

【⚠️ 端口锁定声明 - 严禁修改】
以下端口号已硬编码锁定，任何AI或程序不得擅自修改：
  SUB_PORT = 2087  （订阅服务端口，已固定，走CDN）
  SINGBOX_PORT = 443
  VLESS_WS_PORT = 8443
  TROJAN_WS_PORT = 2083
  ANYTLS_PORT = 2096  （v4.14.0 新增，直连隐蔽协议）
修改端口号必须由用户明确指令，否则视为违规操作。
历史教训：
  - v1.0.42之前默认端口6969导致防火墙不匹配、服务不可达
  - v1.0.43使用9443端口，但SSL证书颁发给域名，
    用IP访问时证书域名不匹配，V2rayN等客户端拒绝连接。
    9443不在Cloudflare CDN代理端口列表中，无法通过域名走CDN。
  - v1.0.44改用2087端口（CDN支持），通过域名访问解决证书匹配问题。
【v4.14.0 协议栈精简】：
  - 删除 VLESS-HTTPUpgrade-CDN（故障最多，兼容最窄）
  - 新增 anyTLS（sing-box 1.12+ 原生，缓解 TLS-in-TLS 指纹，配置极简）
  - VLESS_UPGRADE_PORT 保留常量定义以兼容旧 .env，但不再使用
【v4.15.0 协议栈调整】：
  - 加回 TUIC v5（用户要求 TCP+UDP 双协议支持，TUIC 提供 UDP relay）
  - TUIC_PORT 重新启用，默认 50444，ENABLE_TUIC 默认 true
  - v2rayN 6.x+ / v2rayNG 1.x+ 归 full 能力（内置 sing-box 内核，支持 anytls:// 和 tuic://）
"""

import os
import json
import hashlib
import secrets
import subprocess

try:
    from dotenv import dotenv_values
except ImportError:
    dotenv_values = None

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
    return load_env_file().get(key, default)


def _strip_inline_comment(value):
    """兼容历史遗留的 `KEY=  # 注释` 写法，避免把注释当成值读进去"""
    value = value.strip()
    if value.startswith('#'):
        return ''
    for marker in (' #', '\t#'):
        idx = value.find(marker)
        if idx != -1:
            value = value[:idx]
    return value.strip()


def load_env_file(path=None):
    """读取.env文件，优先使用python-dotenv，降级时兼容旧的行内注释格式"""
    env_path = path or ENV_FILE
    if not os.path.exists(env_path):
        return {}

    if dotenv_values is not None:
        try:
            parsed = dotenv_values(env_path)
            return {
                str(k).strip(): '' if v is None else _strip_inline_comment(str(v))
                for k, v in parsed.items()
                if k
            }
        except Exception:
            pass

    values = {}
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    values[k.strip()] = _strip_inline_comment(v)
    except Exception:
        return {}
    return values


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
# v4.14.0: VLESS_UPGRADE_PORT 保留以兼容旧 .env，但不再使用（HTTPUpgrade 协议已下线）
VLESS_UPGRADE_PORT = 2053
TROJAN_WS_PORT = 2083
ANYTLS_PORT = 2096  # v4.14.0 新增：anyTLS 直连隐蔽协议（固定端口）
# v4.15.0: TUIC v5 加回（用户要求 TCP+UDP 双协议支持），默认 50444
TUIC_PORT = int(os.getenv('TUIC_PORT', '0')) or 50444
# VLESS-gRPC / Trojan-TCP 可配置端口（从 .env 读取，不固定，随机更安全）
VLESS_GRPC_PORT = int(os.getenv('VLESS_GRPC_PORT', '0')) or 50051
TROJAN_TCP_PORT = int(os.getenv('TROJAN_TCP_PORT', '0')) or 50443
SOCKS5_PORT = 1080

LOCKED_PORTS = {
    'SUB_PORT': SUB_PORT,
    'SINGBOX_PORT': SINGBOX_PORT,
    'VLESS_WS_PORT': VLESS_WS_PORT,
    'VLESS_UPGRADE_PORT': VLESS_UPGRADE_PORT,
    'TROJAN_WS_PORT': TROJAN_WS_PORT,
    'ANYTLS_PORT': ANYTLS_PORT,
    'TUIC_PORT': TUIC_PORT,
    'VLESS_GRPC_PORT': VLESS_GRPC_PORT,
    'TROJAN_TCP_PORT': TROJAN_TCP_PORT,
    'SOCKS5_PORT': SOCKS5_PORT,
}

SUB_TOKEN = os.getenv('SUB_TOKEN', '')
COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'US')

# v4.14.0: anyTLS 协议密码（安装时随机生成，与 TROJAN_PASSWORD 独立）
ANYTLS_PASSWORD = os.getenv('ANYTLS_PASSWORD', '')

# v4.15.2: HK1 香港阿里云节点特殊模式 - 全部直连，无 CDN 节点
# ⚠️ 铁律（v4.15.2 修正）：判断 HK1 必须基于 CF_DOMAIN 域名前缀（hk1.），禁止用 COUNTRY_CODE。
#   - HK  与 HK1 地理都在香港，COUNTRY_CODE 都可能是 'HK'，用 COUNTRY_CODE 根本无法区分。
#   - HK  服务器：hk.290372913.xyz  → CDN  模式（6节点，橙云 proxied=true）
#   - HK1 服务器：hk1.290372913.xyz → 直连模式（4节点，香港阿里云 200GB 流量）
#   - 旧逻辑 (COUNTRY_CODE == 'HK' → direct) 会导致：
#     a) HK1 若 COUNTRY_CODE=HK1 → 不匹配 → 错判为 CDN（用户反馈"老是把 HK1 搞 CDN"）
#     b) HK  若 COUNTRY_CODE=HK  → 匹配 → 错判为 direct（CDN 节点被砍）
#   - 正确做法：fallback 只看域名前缀，hk1. 才是直连；DEPLOY_MODE 显式设置优先级最高。
# v4.15.0: 此标志作为 legacy 向后兼容依据，新部署统一使用 DEPLOY_MODE 控制
_hk1_domain_fallback = (_load_env_value('CF_DOMAIN', '') or os.getenv('CF_DOMAIN', '') or '').strip().lower().startswith('hk1.')
HK_DIRECT_MODE = _hk1_domain_fallback

# v4.15.0: 部署模式 dual-stack 支持
# 'cdn'    = CDN混合模式（6节点：4直连+2WS-CDN，启动singbox-cdn服务）
# 'direct' = 纯直连模式（4节点：去掉WS-CDN和CDN监控，极简无CF依赖）
# 向后兼容策略（v4.15.2 修正：基于域名前缀，非 COUNTRY_CODE）：
#   - 如果 .env 中显式设置了 DEPLOY_MODE → 遵循显式设置（最高优先级）
#   - 如果未设置 DEPLOY_MODE（旧部署升级）：
#     * HK1 节点（CF_DOMAIN 以 hk1. 开头，香港阿里云）→ 默认 direct
#     * 其他节点（HK/JP/SG 等）→ 默认 cdn
_env_deploy_mode = os.getenv('DEPLOY_MODE', '').lower().strip() or _load_env_value('DEPLOY_MODE', '').lower().strip()
if _env_deploy_mode in ('cdn', 'direct'):
    DEPLOY_MODE = _env_deploy_mode
else:
    DEPLOY_MODE = 'direct' if HK_DIRECT_MODE else 'cdn'
CDN_MODE_ENABLED = (DEPLOY_MODE == 'cdn')
DIRECT_MODE_ENABLED = (DEPLOY_MODE == 'direct')


# v4.15.8: Reality 配置从 .env 读取（持久化，确保服务端与订阅端一致）
REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID') or secrets.token_hex(8)
REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')

CDN_DB_URL = 'https://api.uouin.com/cloudflare.html'
CDN_MONITOR_INTERVAL = 3600
CDN_TOP_IPS_COUNT = 15

# 日本→中国整合优选Cloudflare IP池（唯一真相源）
# ⚠️ 修改此列表必须同步更新cdn_monitor.py的import
# 来源整合：
#   - 用户本地实测高速IP（162.159/108.162/172.64段，速度>60mb/s）
#   - 用户本地实测低延迟IP（8.39段，延迟<15ms）
#   - 外部API验证IP（vvhan/090227/001315等多源交叉确认）
# 排序规则：按本地实测延迟从低到高排列，速度优先
# 自动择优机制：cdn_monitor TCP连通测试 + 外部API补充候选，统一按延迟排序
CDN_PREFERRED_IPS = [
    # 8.39段 - 低延迟优选（用户本地实测）
    '8.39.125.221',
    '8.39.125.101',
    '8.39.125.36',
    # 162.159段 - 高速优选（用户本地实测，速度>60mb/s）
    '162.159.109.77',
    '162.159.109.87',
    '162.159.105.93',
    '162.159.105.151',
    '162.159.45.121',
    '162.159.45.152',
    '162.159.45.189',
    '162.159.45.4',
    '162.159.45.136',
    '162.159.5.56',
    '162.159.44.242',
    '162.159.44.146',
    '162.159.44.252',
    '162.159.44.183',
    '162.159.44.8',
    '162.159.39.178',
    '162.159.39.159',
    '162.159.39.207',
    '162.159.38.32',
    '162.159.38.161',
    '162.159.38.140',
    '162.159.38.92',
    '162.159.38.169',
    '162.159.39.14',
    '162.159.13.213',
    '162.159.45.3',
    '162.159.38.60',
    '162.159.36.188',
    '162.159.0.158',
    '162.159.18.197',
    '162.159.23.125',
    # 108.162段 - 高速优选
    '108.162.198.57',
    '108.162.198.221',
    '108.162.198.211',
    '108.162.198.223',
    '108.162.198.165',
    '108.162.198.8',
    '108.162.195.30',
    # 172.64段 - 高速优选
    '172.64.53.146',
    '172.64.48.95',
    '172.64.53.71',
    '172.64.53.231',
    '172.64.53.125',
    '172.64.53.113',
    '172.64.53.47',
    '172.64.52.132',
    '172.64.52.208',
    '172.64.52.35',
    '172.64.52.72',
    '172.64.41.181',
    '172.64.229.110',
    '172.64.229.250',
    '172.64.229.121',
    '172.64.34.89',
    '172.64.146.184',
    '172.64.42.248',
    # 104段 - 备用（日本服务器延迟低，但中国用户可能有差异）
    '104.18.32.206',
    '104.18.42.36',
    '104.18.41.58',
    '104.18.40.58',
    '104.18.40.76',
    # 新增 - 用户投喂优质IP（2026-04-29）
    '162.159.62.41',
    '162.159.22.88',
    '162.159.2.144',
    '162.159.58.39',
    '162.159.46.86',
    '162.159.0.191',
    '172.64.34.99',
    '172.64.49.26',
    '104.18.47.36',
    # 新增 - 用户投喂优质IP（2026-04-29 第二批）
    '172.64.34.224',
    '108.162.195.41',
    '172.64.155.5',
    '162.159.2.57',
    '172.64.156.253',
    '172.64.50.216',
    '162.159.4.12',
    '162.159.35.238',
    '172.64.147.44',
    '162.159.10.113',
    '198.41.223.63',
    '162.159.45.248',
    '172.64.156.209',
    '108.162.195.110',
    # 新增 - 用户投喂优质IP（2026-05-07 第三批）
    '162.159.13.224',
    '162.159.22.59',
    '162.159.24.244',
    '162.159.2.233',
    '162.159.62.83',
    '162.159.60.132',
    '162.159.25.221',
    '162.159.3.156',
    '104.18.37.220',
    '162.159.12.98',
    '162.159.44.202',
    '172.64.229.14',
    '162.159.45.10',
    '172.64.147.233',
    '162.159.1.88',
    # 新增 - 用户投喂优质IP（2026-05-18 第四批）
    '172.64.32.185',
    '162.159.11.77',
    '162.159.32.25',
    '162.159.10.43',
    '162.159.58.98',
    '104.18.34.223',
    '162.159.5.200',
    '172.64.229.10',
    '162.159.44.151',
    '108.162.198.231',
    '162.159.39.145',
    # 新增 - 用户投喂优质IP（2026-05-18 第五批）
    '162.159.58.138',
    '104.18.32.189',
    '162.159.23.112',
    '162.159.36.24',
    '162.159.5.244',
    '162.159.24.30',
    '162.159.35.58',
    '172.64.157.102',
    '104.18.34.160',
    '162.159.40.232',
    '172.64.53.104',
    '162.159.16.200',
    '172.64.229.195',
    # 新增 - 用户投喂优质IP（2026-05-21 第六批）
    '162.159.33.124',
    '162.159.21.60',
    '104.18.40.186',
    '162.159.34.125',
    '172.64.145.178',
    '108.162.193.147',
    '104.18.42.98',
    '172.64.38.178',
    '104.18.36.249',
    '172.64.229.249',
    '162.159.2.128',
    '162.159.46.54',
    # 新增 - 用户投喂优质IP（2026-05-22 第七批）
    '172.64.148.114',
    '162.159.42.53',
    '162.159.48.217',
    '104.18.43.43',
    '172.64.146.161',
    '104.18.46.185',
    '162.159.17.80',
    '104.18.32.24',
    '162.159.14.187',
    '104.18.41.36',
    '162.159.44.116',
    '172.64.149.176',
    '162.159.49.192',
    '172.64.155.63',
    '172.64.229.172',
    # 新增 - 用户本地实测优质IP（2026-06-13 第八批）
    '108.162.198.43',
    '162.159.44.136',
    '162.159.39.181',
    '172.64.229.248',
    '162.159.38.210',
    '172.64.53.93',
    '172.64.52.224',
    '162.159.39.230',
    '162.159.38.215',
]

# v3.0 用户手动标记的黑名单IP（你告诉我哪个不好，我加到这里）
# 脚本会直接跳过这些IP，不参与测试和评分
CDN_IP_BLACKLIST = [
    '162.159.153.144',  # 用户反馈延迟太高（2026-04-25）
    '104.17.111.127',   # 用户反馈延迟大（2026-04-25）
    '104.16.243.59',    # 用户反馈卡（2026-04-26）
    '104.21.92.14',     # 用户反馈延迟高（2026-04-29）
    '104.21.90.16',     # 用户反馈延迟高（2026-04-29）
    '104.17.253.176',   # 用户反馈延迟高（2026-04-29）
    '104.17.181.238',   # 用户反馈不行（2026-04-29 第二批）
    '104.19.38.69',     # 用户反馈不行（2026-04-29 第二批）
    '104.19.33.151',    # 用户反馈不行（2026-04-29 第二批）
    '104.18.185.26',    # 用户反馈拉跨（2026-05-07）
    '104.16.147.135',   # 用户反馈垃圾（2026-05-07）
    '104.17.119.190',   # 用户反馈垃圾（2026-05-07）
    '104.17.110.132',   # 用户反馈垃圾（2026-05-07）
    '104.16.244.71',    # 用户反馈垃圾（2026-05-07）
    '162.159.152.11',   # 用户反馈连不上（2026-05-07）
    '104.19.149.140',   # 用户反馈拉跨（2026-05-07）
    '8.35.211.141',     # 延迟低但速度不行（2026-05-18）
    '173.245.59.21',    # 延迟低但速度不行（2026-05-18）
    '162.159.35.152',   # 延迟低但速度不行（2026-05-18）
    '104.18.91.155',    # 用户反馈不可用（2026-05-22）
]

# CDN优选IP外部API（降级方案，本地池不可用时自动切换）
CDN_API_WETEST_CT = 'ct.cloudflare.182682.xyz'
CDN_API_IPDB = 'https://ipdb.api.030101.xyz/?type=bestcf'
CDN_API_001315_CT = 'https://cf.001315.xyz/ct'
CDN_API_001315_CU = 'https://cf.001315.xyz/cu'
CDN_API_001315_CMCC = 'https://cf.001315.xyz/cmcc'
CDN_API_090227_CT = 'https://addressesapi.090227.xyz/ct'
CDN_API_090227_CU = 'https://addressesapi.090227.xyz/cu'
CDN_API_090227_CMCC = 'https://addressesapi.090227.xyz/cmcc'
CDN_API_VVHAN = 'https://api.vvhan.com/tool/cf_ip'

# cfnew 思路移植：支持自定义优选源 URL（多个用逗号分隔）
CDN_CUSTOM_SOURCE_URLS = os.getenv('CDN_CUSTOM_SOURCE_URLS', '').strip()
# 筛选策略：保留最快N个候选，0表示不限制
CDN_FASTEST_LIMIT = int(os.getenv('CDN_FASTEST_LIMIT', '10') or '10')
# 地区筛选（多个用逗号分隔，如 US,JP,SG；当前用于名称标签粗筛）
CDN_REGION_FILTER = os.getenv('CDN_REGION_FILTER', '').strip()

CERT_VALIDITY_DAYS = 365

# ============ 用户DDNS锚点配置（v4.5 区域化CDN优选）============
# 用户DDNS域名（锚定用户位置和网络环境，服务器通过此域名感知用户网络状态）
USER_DDNS_DOMAIN = os.getenv('USER_DDNS_DOMAIN', '') or _load_env_value('USER_DDNS_DOMAIN', '')

# 用户预期运营商（用于验证DDNS解析结果是否合理，如：电信/联通/移动）
USER_EXPECTED_ISP = os.getenv('USER_EXPECTED_ISP', '电信').strip()

# 用户网络探测间隔（秒），默认300秒（5分钟）
USER_PROBE_INTERVAL = int(os.getenv('USER_PROBE_INTERVAL', '300') or '300')

# 用户网络波动阈值（延迟突增百分比），超过则触发CDN刷新
USER_LATENCY_SPIKE_THRESHOLD = float(os.getenv('USER_LATENCY_SPIKE_THRESHOLD', '0.5') or '0.5')

# 湖南电信已知优质CF IP段前缀（基于历史数据，用于区域适配度评分）
HUNAN_CT_OPTIMAL_PREFIXES = [
    '162.159.', '172.64.', '108.162.', '198.41.', '173.245.',
    '8.39.', '8.41.', '8.43.'
]

# CDN IP硬淘汰阈值：不达标的IP直接淘汰，不进评分（严格标准，全自动无感切换）
CDN_IP_HARD_REJECT = {
    'latency_ms': 180,           # VPS→CF延时超过180ms直接淘汰，避免高延时边缘节点混入
    'user_path_latency_ms': 120, # 通过CDN到用户路径延时超过120ms直接淘汰
    'packet_loss_rate': 0.08,    # 丢包率超过8%直接淘汰
    'download_speed_mbps': 20,   # 下载速度低于20Mbps直接淘汰
}

# ============ CDN故障自愈配置（v4.6 多级回退）============
# 健康监控 + 故障自动切换 + 冷却机制
CDN_FAILOVER = {
    'health_check_interval_sec': 60,       # 健康检查间隔（秒）
    'health_check_timeout_sec': 5,         # 单次健康检查超时（秒）
    'switch_latency_threshold_ms': 200,    # 延时超过此值触发切换
    'switch_loss_threshold': 0.15,         # 丢包超过此值触发切换
    'cooldown_sec': 300,                   # 故障IP冷却时间（秒），冷却期内不重新选中
    'max_consecutive_switches': 5,         # 连续切换上限，超过则降级直连
    'min_stable_duration_sec': 30,         # 切换后稳定时长（秒）
}

# ============ CDN模式配置（v4.8 三模式优选）============
# ip_optimized=优选IP模式（CDN节点用优选IP，SNI=域名）
# domain_optimized=优选域名模式（CDN节点用第三方优选域名，走优化线路）
# domain_default=默认域名模式（CDN节点用自己的CF域名，无优化）
# 兼容旧配置：CDN_PREFER_IP_OVER_DOMAIN=true 自动映射为 ip_optimized
_old_cdn_ip_mode = os.getenv('CDN_PREFER_IP_OVER_DOMAIN', '').lower()
if _old_cdn_ip_mode in ('true', '1', 'yes'):
    _cdn_mode_default = 'ip_optimized'
elif _old_cdn_ip_mode in ('false', '0', 'no'):
    _cdn_mode_default = 'domain_default'
else:
    _cdn_mode_default = os.getenv('CDN_MODE', 'ip_optimized').lower().strip()
CDN_MODE = _cdn_mode_default if _cdn_mode_default in ('ip_optimized', 'domain_optimized', 'domain_default') else 'ip_optimized'

# 优选域名列表（domain_optimized模式使用，逗号分隔）
CDN_OPTIMIZED_DOMAINS = [d.strip() for d in os.getenv('CDN_OPTIMIZED_DOMAINS', 'icook.hk,icook.tw,cf.090227.xyz,time.is,www.visa.cn,mfa.gov.ua,bestcf.030101.xyz,saas.sin.fan').split(',') if d.strip()]

# 优选域名测速URL（用于下载速度测试）
CDN_DOMAIN_TEST_URL = os.getenv('CDN_DOMAIN_TEST_URL', 'https://speed.cloudflare.com/__down?bytes=10000000').strip()

# ============ 直连节点筛选配置（v4.6 REALITY直连）============
# 直连节点硬淘汰阈值
DIRECT_NODE_HARD_REJECT = {
    'latency_ms': 150,           # 直连TCP延时超过150ms淘汰
    'tls_handshake_ms': 200,     # TLS握手超过200ms淘汰
    'packet_loss_rate': 0.15,    # 丢包率超过15%淘汰
    'consecutive_fails': 5,      # 连续失败5次淘汰
}

# 直连节点探测配置
DIRECT_NODE_PROBE_INTERVAL = int(os.getenv('DIRECT_NODE_PROBE_INTERVAL', '300') or '300')  # 探测间隔（秒）

# ============ 三网最优优选配置（v4.6）============
# 各运营商已知优质CF IP段（来自全网公开数据，持续更新）
# 用于跨网综合评分：IP落在某运营商优质段内则给该网加分
THREE_ISP_OPTIMAL_PREFIXES = {
    'telecom': {
        'name': '电信',
        'prefixes': [
            '1.0.0.', '1.1.1.',           # 通用优质
            '104.16.160.',                 # 洛杉矶（圣何塞）
            '172.64.0.',                   # 旧金山
            '104.23.240.',                 # 欧洲（电信部分省份）
            '162.159.208.', '162.159.209.', '162.159.210.', '162.159.211.',  # 百度云合作
        ],
    },
    'unicom': {
        'name': '联通',
        'prefixes': [
            '108.162.236.',                # 美国
            '104.20.157.',                 # 日本
            '104.23.240.', '104.23.241.', '104.23.242.', '104.23.243.',  # 联通/移动共用
            '104.16.160.',                 # 圣何塞
        ],
    },
    'mobile': {
        'name': '移动',
        'prefixes': [
            '172.64.32.',                  # 香港
            '141.101.115.',                # 香港
            '104.28.14.',                  # 新加坡
            '104.18.48.', '104.18.49.', '104.18.50.', '104.18.51.',  # 新加坡
            '104.23.240.', '104.23.241.', '104.23.242.', '104.23.243.',  # 联通/移动共用
            '198.41.208.', '198.41.209.', '198.41.212.', '198.41.214.',  # 移动香港
        ],
    },
}

# 用户路径质量不达标阈值（触发CDN刷新，全自动换IP）
USER_QUALITY_THRESHOLD = {
    'latency_ms': 100,           # VPS→用户延时超过100ms视为不达标
    'packet_loss_rate': 0.05,    # 丢包率超过5%视为不达标
    'download_speed_mbps': 20,   # 下载速度低于20Mbps视为不达标
}

AI_SOCKS5_SERVER = os.getenv('AI_SOCKS5_SERVER', '')
AI_SOCKS5_PORT = int(os.getenv('AI_SOCKS5_PORT', '0')) if os.getenv('AI_SOCKS5_PORT') else 0
AI_SOCKS5_USER = os.getenv('AI_SOCKS5_USER', '')
AI_SOCKS5_PASS = os.getenv('AI_SOCKS5_PASS', '')
AI_SOCKS5_ROUTING = os.getenv('AI_SOCKS5_ROUTING', 'off').lower()
AI_SOCKS5_POOL = os.getenv('AI_SOCKS5_POOL', '')

NODE_PREFIX = f'ePS-{COUNTRY_CODE}'


def _compute_port_checksum():
    """计算端口配置的校验和，用于防篡改检测"""
    port_str = json.dumps(LOCKED_PORTS, sort_keys=True)
    return hashlib.sha256(port_str.encode()).hexdigest()


def save_port_lock():
    """保存端口锁定文件（持久化存储）"""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        import subprocess
        locked_at = subprocess.run(['date', '-Iseconds'], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        locked_at = ''
    lock_data = {
        'ports': LOCKED_PORTS,
        'checksum': _compute_port_checksum(),
        'locked_at': locked_at,
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
        'tuic': f'{NODE_PREFIX}-TUIC v5',
        'socks5': f'{NODE_PREFIX}-SOCKS5'
    }
    return names.get(protocol, f'{NODE_PREFIX}-{protocol}')


def get_env(key, default=''):
    """从环境文件读取配置"""
    return _load_env_value(key, default)


def get_sub_domain():
    """获取订阅服务访问域名
    v4.15.0 dual-stack:
    - cdn模式（默认）：生成 sub-* 子域名（gray cloud 直连源站），绕过 CF DDoS L7
    - direct模式：直接用主域名或IP（不使用sub-*子域名）
    ⚠️ HTTPS订阅服务必须用域名访问（SSL证书已包含 sub-* SAN）
    如果没有配置域名，返回IP（此时客户端需跳过证书验证）
    """
    if DIRECT_MODE_ENABLED:
        return CF_DOMAIN.strip() if (CF_DOMAIN and CF_DOMAIN.strip()) else SERVER_IP
    if CF_DOMAIN and CF_DOMAIN.strip():
        domain = CF_DOMAIN.strip()
        if '.' in domain:
            parts = domain.split('.', 1)
            return f"sub-{parts[0]}.{parts[1]}"
        return domain
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
        'tuic_password': get_env('TUIC_PASSWORD', ''),
        'tuic_uuid': get_env('TUIC_UUID', ''),
        'enable_tuic': get_env('ENABLE_TUIC', 'true'),
        'socks5_user': get_env('SOCKS5_USER', ''),
        'socks5_pass': get_env('SOCKS5_PASS', ''),
        'reality_private_key': get_env('REALITY_PRIVATE_KEY', ''),
        'reality_public_key': get_env('REALITY_PUBLIC_KEY', ''),
        'reality_short_id': get_env('REALITY_SHORT_ID', REALITY_SHORT_ID),
        'reality_dest': get_env('REALITY_DEST', REALITY_DEST),
        'reality_sni': get_env('REALITY_SNI', REALITY_SNI),
    }
    return config
