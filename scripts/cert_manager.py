#!/usr/bin/env python3
"""
Singbox 证书管理服务
Author: Alan
Version: v1.0.54
Date: 2026-04-20
功能：
  - 支持 Cloudflare API 申请长期证书
  - 支持自签证书（备用）
  - 自动续签
"""

import os
import sys
import subprocess
import json
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import CERT_DIR, CF_DOMAIN, CERT_VALIDITY_DAYS, SERVER_IP, BASE_DIR
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

    CERT_DIR = '/root/singbox-eps-node/cert'
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
    CF_DOMAIN = ''
    CERT_VALIDITY_DAYS = 365
    SERVER_IP = ''

logger = get_logger('cert_manager')

CERT_FILE = os.path.join(CERT_DIR, 'cert.pem')
KEY_FILE = os.path.join(CERT_DIR, 'key.pem')

# ⚠️ CF_API_TOKEN从.env读取，不直接用os.getenv覆盖config.py的CF_DOMAIN
# config.py的CF_DOMAIN已经从.env读取过了，这里直接用导入的值
def _load_cf_api_token():
    """从.env文件读取CF_API_TOKEN（不在环境变量中，必须从文件读取）"""
    token = os.getenv('CF_API_TOKEN', '')
    if token:
        return token
    env_file = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('CF_API_TOKEN='):
                    return line.split('=', 1)[1].strip()
    return ''

CF_API_TOKEN = _load_cf_api_token()

def ensure_cert_dir():
    """确保证书目录存在"""
    os.makedirs(CERT_DIR, exist_ok=True)

def get_cf_api_token():
    """获取 Cloudflare API Token"""
    return CF_API_TOKEN

def request_cf_ssl_certificate(domain, cf_api_token):
    """
    使用 Cloudflare API 获取SSL证书
    Cloudflare API 可以签发源证书，有效期15年
    """
    try:
        logger.info(f">>> 请求 Cloudflare SSL 证书 for {domain}...")
        ensure_cert_dir()

        csr_file = os.path.join(CERT_DIR, 'domain.csr')
        subprocess.run(
            ['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
             '-keyout', KEY_FILE, '-out', csr_file, '-subj', f'/CN={domain}'],
            capture_output=True, check=True
        )

        with open(csr_file, 'r') as f:
            csr_content = f.read()

        api_url = "https://api.cloudflare.com/client/v4/certificates"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cf_api_token}'
        }

        payload = {
            'hostnames': [domain],
            'requested_validity': 5475,
            'request_type': 'origin-rsa',
            'csr': csr_content
        }

        req = Request(api_url, data=json.dumps(payload).encode(), headers=headers, method='POST')

        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())

            if result.get('success'):
                cert_data = result.get('result', {})
                logger.info(f"[OK] Cloudflare 证书获取成功")
                logger.info(f"  证书ID: {cert_data.get('id')}")
                logger.info(f"  有效期: {cert_data.get('expires_on')}")
                return {
                    'certificate': cert_data.get('certificate'),
                    'private_key': None,
                    'expires_on': cert_data.get('expires_on')
                }
            else:
                errors = result.get('errors', [])
                error_msg = errors[0].get('message', 'Unknown error') if errors else 'Unknown error'
                logger.error(f"[ERROR] Cloudflare API 错误: {error_msg}")
                return None

    except URLError as e:
        logger.error(f"[ERROR] 请求失败: {e}")
        return None
    except Exception as e:
        logger.error(f"[ERROR] 获取证书异常: {e}")
        return None

def generate_self_signed_cert(domain=None):
    """生成自签名证书（备用方案）"""
    if domain is None:
        domain = CF_DOMAIN if CF_DOMAIN else SERVER_IP

    logger.info(f">>> 生成自签名证书 for {domain}...")
    ensure_cert_dir()

    result = subprocess.run(
        ['openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048',
        '-keyout', KEY_FILE, '-out', CERT_FILE,
        '-days', str(CERT_VALIDITY_DAYS),
        '-subj', f'/CN={domain}'],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        logger.info("[OK] 自签名证书生成成功")
        return True
    else:
        logger.error(f"[ERROR] {result.stderr}")
        return False

def obtain_certificate():
    """获取证书主函数"""
    ensure_cert_dir()

    cf_token = get_cf_api_token()
    domain = CF_DOMAIN

    if cf_token and domain:
        logger.info(f"尝试使用 Cloudflare API 获取证书...")
        cf_cert = request_cf_ssl_certificate(domain, cf_token)

        if cf_cert:
            with open(CERT_FILE, 'w') as f:
                f.write(cf_cert['certificate'])
            if cf_cert.get('private_key'):
                with open(KEY_FILE, 'w') as f:
                    f.write(cf_cert['private_key'])
            logger.info(f"[OK] Cloudflare 证书已保存")
            return True
        else:
            logger.warning("[WARN] Cloudflare API 失败，尝试自签名证书...")

    logger.info("使用自签名证书...")
    return generate_self_signed_cert()

def check_cert_expiry():
    """检查证书是否过期
    检查顺序：fullchain.pem（Let's Encrypt） > cert.pem（Cloudflare API/自签名）
    """
    for cert_name in ['fullchain.pem', 'cert.pem']:
        cert_path = os.path.join(CERT_DIR, cert_name)
        if os.path.exists(cert_path):
            try:
                result = subprocess.run(
                    ['openssl', 'x509', '-in', cert_path, '-noout', '-enddate'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    end_date_str = result.stdout.split('=')[1].strip()
                    end_date = datetime.strptime(end_date_str, '%b %d %H:%M:%S %Y %Z')
                    days_left = (end_date - datetime.now()).days
                    logger.info(f"[INFO] 证书({cert_name})剩余有效期: {days_left} 天")
                    return days_left < 30
            except Exception as e:
                logger.warning(f"[WARN] 检查证书过期失败({cert_name}): {e}")
    logger.warning("[WARN] 未找到任何证书文件，需要申请")
    return True

def restart_singbox():
    """重启Singbox和订阅服务"""
    os.system('systemctl restart singbox')
    os.system('systemctl restart singbox-sub')
    logger.info("[OK] Singbox 与订阅服务已重启")

def renew_cert():
    """续签证书"""
    logger.info(f"证书续签检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if check_cert_expiry():
        logger.info("[INFO] 证书需要续签")
        if obtain_certificate():
            restart_singbox()
            logger.info("[OK] 证书续签完成")
    else:
        logger.info("[OK] 证书还在有效期内，无需续签")

def setup_iptables_persistent():
    """设置 iptables 持久化"""
    logger.info(">>> 设置 iptables 持久化...")

    try:
        subprocess.run(['which', 'iptables-persistent'], capture_output=True)
    except Exception:
        logger.info("安装 iptables-persistent...")
        os.system('export DEBIAN_FRONTEND=noninteractive && apt-get update -y')
        os.system('export DEBIAN_FRONTEND=noninteractive && apt-get install -y iptables-persistent')

    logger.info("[OK] iptables-persistent 已安装")

def setup_hysteria2_port_hopping():
    """设置 Hysteria2 端口跳跃规则

    ⚠️ 端口跳跃目标必须与singbox配置中HY2的listen_port一致
    当前HY2监听443端口（与VLESS-Reality共用）
    历史Bug：之前转发到4433，但HY2不在4433监听，导致端口跳跃无效

    ⚠️ 必须同时设置UDP和TCP规则：
    - UDP：HY2主要使用QUIC(UDP)协议，这是核心
    - TCP：当UDP被封锁或不稳定时，HY2可降级使用TCP，确保节点可用
    - 双协议保障：UDP不通→TCP兜底，TCP不通→UDP兜底
    """
    logger.info(">>> 设置 Hysteria2 端口跳跃规则 (21000-21200 → 443, UDP+TCP)...")

    if os.popen('iptables-save | grep "DNAT.*4433"').read():
        os.popen('iptables-save | grep -v "DNAT.*4433" | iptables-restore')
        logger.info("[INFO] 旧规则(→4433)已清理")

    if os.popen('iptables-save | grep "DNAT.*:443"').read():
        os.popen('iptables-save | grep -v "DNAT.*:443" | iptables-restore')
        logger.info("[INFO] 旧规则(→443)已清理")

    for port in range(21000, 21201):
        os.system(f'iptables -t nat -A PREROUTING -p udp --dport {port} -j DNAT --to-destination :443')
        os.system(f'iptables -t nat -A PREROUTING -p tcp --dport {port} -j DNAT --to-destination :443')

    logger.info("[OK] 端口跳跃规则已设置 (21000-21200 → 443, UDP+TCP双协议保障)")

    setup_iptables_persistent()

    logger.info(">>> 保存 iptables 规则...")
    os.system('debconf-set-selections <<< "iptables-persistent iptables-persistent/autosave_v4 boolean true"')
    os.system('debconf-set-selections <<< "iptables-persistent iptables-persistent/autosave_v6 boolean true"')
    os.system('netfilter-persistent save')
    logger.info("[OK] iptables 规则已持久化")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--renew":
            renew_cert()
        elif sys.argv[1] == "--setup-iptables":
            setup_hysteria2_port_hopping()
        elif sys.argv[1] == "--cf-cert":
            obtain_certificate()
        else:
            logger.info(f"未知参数: {sys.argv[1]}")
    else:
        ensure_cert_dir()
        if not os.path.exists(CERT_FILE):
            obtain_certificate()
        logger.info(f"[INFO] 证书状态: {'已存在' if os.path.exists(CERT_FILE) else '不存在'}")
