#!/usr/bin/env python3
"""
Singbox 证书管理服务
Author: Alan
Version: v1.0.4
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
    from config import CERT_DIR, CF_DOMAIN, CERT_VALIDITY_DAYS, SERVER_IP
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger('cert_manager')

CERT_DIR = '/root/singbox-manager/cert'
CERT_FILE = os.path.join(CERT_DIR, 'cert.crt')
KEY_FILE = os.path.join(CERT_DIR, 'cert.key')
CERT_VALIDITY_DAYS = 365

CF_API_TOKEN = os.getenv('CF_API_TOKEN', '')
CF_DOMAIN = os.getenv('CF_DOMAIN', '')

def ensure_cert_dir():
    """确保证书目录存在"""
    os.makedirs(CERT_DIR, exist_ok=True)

def get_cf_api_token():
    """获取 Cloudflare API Token"""
    token = os.getenv('CF_API_TOKEN', '')
    if token:
        return token

    env_file = '/root/singbox-manager/.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if line.startswith('CF_API_TOKEN='):
                    return line.split('=', 1)[1].strip()
    return ''

def request_cf_ssl_certificate(domain, cf_api_token):
    """
    使用 Cloudflare API 获取SSL证书
    Cloudflare API 可以签发源证书，有效期15年
    """
    try:
        logger.info(f">>> 请求 Cloudflare SSL 证书 for {domain}...")

        api_url = f"https://api.cloudflare.com/client/v4/certificates"

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {cf_api_token}'
        }

        payload = {
            'type': 'origin',
            'host': domain,
            'requested_validity': 5475
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
                    'private_key': cert_data.get('private_key'),
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
            with open(KEY_FILE, 'w') as f:
                f.write(cf_cert['private_key'])
            logger.info(f"[OK] Cloudflare 证书已保存")
            return True
        else:
            logger.warning("[WARN] Cloudflare API 失败，尝试自签名证书...")

    logger.info("使用自签名证书...")
    return generate_self_signed_cert()

def check_cert_expiry():
    """检查证书是否过期"""
    if not os.path.exists(CERT_FILE):
        return True
    try:
        result = subprocess.run(
            ['openssl', 'x509', '-in', CERT_FILE, '-noout', '-enddate'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            end_date_str = result.stdout.split('=')[1].strip()
            end_date = datetime.strptime(end_date_str, '%b %d %H:%M:%S %Y %Z')
            days_left = (end_date - datetime.now()).days
            logger.info(f"[INFO] 证书剩余有效期: {days_left} 天")
            return days_left < 30
    except Exception as e:
        logger.warning(f"[WARN] 检查证书过期失败: {e}")
    return True

def restart_singbox():
    """重启Singbox服务"""
    os.system('systemctl restart singbox')
    logger.info("[OK] Singbox已重启")

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
    """设置 Hysteria2 端口跳跃规则"""
    logger.info(">>> 设置 Hysteria2 端口跳跃规则 (21000-21200)...")

    os.system('iptables -t nat -F PREROUTING')

    for port in range(21000, 21201):
        os.system(f'iptables -t nat -A PREROUTING -p udp --dport {port} -j DNAT --to-destination :4433')
        os.system(f'iptables -t nat -A PREROUTING -p tcp --dport {port} -j DNAT --to-destination :4433')

    logger.info("[OK] 端口跳跃规则已设置 (21000-21200)")

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
