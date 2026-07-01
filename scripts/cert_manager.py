#!/usr/bin/env python3
"""
Singbox 证书管理服务
Author: Alan
Version: v4.3.5
Date: 2026-05-01
功能：证书管理
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
    from config import CERT_DIR, CF_DOMAIN, CERT_VALIDITY_DAYS, SERVER_IP, BASE_DIR, DATA_DIR
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

    CERT_DIR = '/root/singbox-eps-node/cert'
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    CF_DOMAIN = ''
    CERT_VALIDITY_DAYS = 365
    SERVER_IP = ''

logger = get_logger('cert_manager')

# TG bot 告警（import 失败时降级为只写日志，不崩溃）
# 注意：tg_bot.py 模块级在未配置 TG_BOT_TOKEN 时会 sys.exit(1)，需捕获 SystemExit
_tg_send_message = None
_tg_admin_chat_id = ''
try:
    from tg_bot import send_message as _tg_send, ADMIN_CHAT_ID as _tg_chat_id
    _tg_send_message = _tg_send
    _tg_admin_chat_id = _tg_chat_id
except (ImportError, SystemExit):
    pass

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

    v4.12.22: 同时包含主域名和 sub-* 子域名，让订阅端点可直连。
    """
    try:
        sub_domain = _build_sub_domain(domain)
        hostnames = [domain]
        if sub_domain:
            hostnames.append(sub_domain)

        logger.info(f">>> 请求 Cloudflare SSL 证书 for {hostnames}...")
        ensure_cert_dir()

        csr_file = os.path.join(CERT_DIR, 'domain.csr')
        san_arg = f"subjectAltName=DNS:{domain}"
        if sub_domain:
            san_arg += f",DNS:{sub_domain}"
        subprocess.run(
            ['openssl', 'req', '-new', '-newkey', 'rsa:2048', '-nodes',
             '-keyout', KEY_FILE, '-out', csr_file, '-subj', f'/CN={domain}',
             '-addext', san_arg],
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
            'hostnames': hostnames,
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

def _build_sub_domain(domain):
    """从主域名生成订阅直连子域名。
    例: jp.290372913.xyz -> sub-jp.290372913.xyz
        hk1.290372913.xyz -> sub-hk1.290372913.xyz
    """
    if not domain or '.' not in domain:
        return None
    parts = domain.split('.', 1)
    return f"sub-{parts[0]}.{parts[1]}"


def generate_self_signed_cert(domain=None):
    """生成自签名证书（备用方案）

    v4.12.22: SAN 同时包含主域名和 sub-* 子域名，
    让订阅端点可通过非代理子域名直连（绕过 CF DDoS L7）。
    v4.15.7: 校验 domain 是否为完整 FQDN，否则警告并重读 .env。
    """
    if domain is None:
        domain = CF_DOMAIN if CF_DOMAIN else SERVER_IP

    # 防护：domain 不是合法域名（如空/裸 IP）时直接从 .env 文件重读
    if not domain or '.' not in domain or domain.count('.') < 2:
        logger.warning(f"[WARN] domain='{domain}' 不是完整域名，直接从 .env 文件重读...")
        env_file = os.path.join(BASE_DIR, '.env')
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith('CF_DOMAIN='):
                        domain = line.split('=', 1)[1].strip().strip('"\'')
                        break
        if not domain or '.' not in domain or domain.count('.') < 2:
            logger.warning(f"[WARN] 重读后 domain='{domain}' 仍不合法，跳过 sub-* SAN 扩展")
            sub_domain = None
        else:
            logger.info(f"[INFO] 重读后 domain='{domain}'，正常生成 sub-* SAN")
            sub_domain = _build_sub_domain(domain)
    else:
        sub_domain = _build_sub_domain(domain)

    if sub_domain:
        san = f"subjectAltName=DNS:{domain},DNS:{sub_domain}"
    else:
        san = f"subjectAltName=DNS:{domain}"

    logger.info(f">> 生成自签名证书 for {domain} (SAN: {san})...")
    ensure_cert_dir()

    result = subprocess.run(
        ['openssl', 'req', '-x509', '-nodes', '-newkey', 'rsa:2048',
        '-keyout', KEY_FILE, '-out', CERT_FILE,
        '-days', str(CERT_VALIDITY_DAYS),
        '-subj', f'/CN={domain}',
        '-addext', san],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        logger.info("[OK] 自签名证书生成成功")
        # 确保fullchain.pem存在（[Trae CN] 2026-06-04）
        fullchain_path = os.path.join(CERT_DIR, 'fullchain.pem')
        if not os.path.exists(fullchain_path):
            import shutil
            shutil.copy2(CERT_FILE, fullchain_path)
            logger.info(f"[cert_manager] 已创建 fullchain.pem -> {fullchain_path}")
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


def get_cert_days_left():
    """获取证书剩余天数（供告警使用），找不到证书返回 None"""
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
                    return (end_date - datetime.now()).days
            except Exception as e:
                logger.warning(f"[WARN] 获取证书剩余天数失败({cert_name}): {e}")
    return None


def _send_cert_renew_alert(domain, days_left):
    """证书续签失败时推送 TG 告警，tg_bot 不可用则只写日志"""
    if not _tg_send_message or not _tg_admin_chat_id:
        logger.warning("TG bot 未配置，证书续签失败告警仅写日志")
        return
    days_str = str(days_left) if days_left is not None else "未知"
    msg = (
        f"⚠️ 证书续签失败: {domain}，剩余 {days_str} 天，请手动处理\n"
        f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    try:
        _tg_send_message(_tg_admin_chat_id, msg)
        logger.info("证书续签失败 TG 告警已推送")
    except Exception as e:
        logger.error("证书续签失败 TG 告警推送异常: %s", e)

def restart_singbox():
    """重启Singbox和订阅服务"""
    for svc in ['singbox', 'singbox-sub', 'singbox-cdn']:
        try:
            subprocess.run(['systemctl', 'restart', svc], timeout=30, capture_output=True)
        except Exception as e:
            logger.warning(f"重启 {svc} 失败: {e}")
    logger.info("[OK] Singbox 与订阅服务已重启")

def renew_cert():
    """续签证书（失败时推送 TG 告警）"""
    logger.info(f"证书续签检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if not check_cert_expiry():
        logger.info("[OK] 证书还在有效期内，无需续签")
        return
    logger.info("[INFO] 证书需要续签")
    try:
        if obtain_certificate():
            restart_singbox()
            logger.info("[OK] 证书续签完成")
        else:
            days_left = get_cert_days_left()
            logger.error("[ERROR] 证书续签失败：obtain_certificate 返回 False")
            _send_cert_renew_alert(CF_DOMAIN, days_left)
    except Exception as e:
        days_left = get_cert_days_left()
        logger.error(f"[ERROR] 证书续签异常: {e}")
        _send_cert_renew_alert(CF_DOMAIN, days_left)

def setup_iptables_persistent():
    """设置 iptables 持久化"""
    logger.info(">>> 设置 iptables 持久化...")

    try:
        subprocess.run(['which', 'iptables-persistent'], capture_output=True, check=True)
    except (Exception, subprocess.CalledProcessError):
        logger.info("安装 iptables-persistent...")
        subprocess.run(['bash', '-c', 'export DEBIAN_FRONTEND=noninteractive && apt-get update -y && apt-get install -y iptables-persistent'],
                       capture_output=True, text=True, timeout=120)

    logger.info("[OK] iptables-persistent 已安装")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--renew":
            renew_cert()
        elif sys.argv[1] == "--cf-cert":
            obtain_certificate()
        else:
            logger.info(f"未知参数: {sys.argv[1]}")
    else:
        ensure_cert_dir()
        if not os.path.exists(CERT_FILE):
            obtain_certificate()
        logger.info(f"[INFO] 证书状态: {'已存在' if os.path.exists(CERT_FILE) else '不存在'}")
