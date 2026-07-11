#!/usr/bin/env python3
"""
Singbox sub-* 直连路径监控脚本
Author: Alan
Version: v1.0.0
Date: 2026-06-28

功能：
  - 每 5 分钟对 sub-jp/sub-sg/sub-hk.290372913.xyz:2087 做 TLS 握手 + HTTP /info 请求
  - 失败时调用 tg_bot 推送告警（复用 tg_bot.send_message）
  - 写日志到 /var/log/sub_domain_monitor.log
  - 支持 cron 调度：*/5 * * * * /root/singbox-eps-node/scripts/sub_domain_monitor.py >> /var/log/sub_domain_monitor.log 2>&1
  - 自动检测当前服务器区域（COUNTRY_CODE），告警中标注检测源
  - 三台服务器都部署，互为冗余检测

设计参考：scripts/cdn_monitor.py 的代码风格和 TLS 握手测试逻辑
"""

import os
import sys
import ssl
import socket
import time
import hashlib
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 配置加载（参考 cdn_monitor.py 的 try/except 降级模式）
try:
    from config import CF_DOMAIN, SUB_PORT, COUNTRY_CODE, BASE_DIR, SUB_TOKEN
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)
    BASE_DIR = os.getenv('BASE_DIR', '/root/singbox-eps-node')
    CF_DOMAIN = ''
    SUB_PORT = 2087
    COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'US')
    SUB_TOKEN = ''

logger = get_logger('sub_domain_monitor')

# 从 .env 补全未通过 config.py 加载的变量
def _load_env_value(key, default=''):
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith(f'{key}='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return default

CF_DOMAIN = CF_DOMAIN or _load_env_value('CF_DOMAIN', '')
SUB_TOKEN = SUB_TOKEN or _load_env_value('SUB_TOKEN', '')
COUNTRY_CODE = (COUNTRY_CODE or _load_env_value('COUNTRY_CODE', 'US')).upper()

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

# sub-* 告警去重：同一域名 30 分钟内只推送一次（参考 tg_bot.send_alert 去重机制）
ALERT_DEDUP_MINUTES = 30
ALERT_DEDUP_DIR = '/tmp'

# 监控的区域代码（v4.15.12: 删除已废弃的 sg，加 hkcepin）
ALL_REGIONS = ['jp', 'hk', 'hk1', 'hkcepin']

# 监控超时（秒）
TLS_TIMEOUT = 8
HTTP_TIMEOUT = 10


def _build_sub_domain(region, base_domain):
    """根据区域代码和基础域名构造 sub-* 直连子域名
    例: ('jp', '290372913.xyz') -> 'sub-jp.290372913.xyz'
    例: ('hk1', '290372913.xyz') -> 'sub-hk1.290372913.xyz'
    """
    return f"sub-{region}.{base_domain}"


def _get_base_domain():
    """从 CF_DOMAIN 提取基础域名
    例: 'jp.290372913.xyz' -> '290372913.xyz'
        'hk1.290372913.xyz' -> '290372913.xyz'
    """
    if not CF_DOMAIN or '.' not in CF_DOMAIN:
        return ''
    parts = CF_DOMAIN.split('.', 1)
    return parts[1] if len(parts) == 2 else ''


def _alert_dedup_key(domain, reason):
    """生成告警去重 hash key"""
    raw = f"{domain}:{reason}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]


def _should_send_alert(domain, reason):
    """检查是否应该发送告警（30 分钟去重）"""
    key = _alert_dedup_key(domain, reason)
    dedup_file = os.path.join(ALERT_DEDUP_DIR, f"sub_domain_alert_dedup_{key}")
    if os.path.exists(dedup_file):
        mtime = os.path.getmtime(dedup_file)
        if time.time() - mtime < ALERT_DEDUP_MINUTES * 60:
            return False
    try:
        with open(dedup_file, 'w') as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass
    return True


def send_tg_alert(domain, reason, detail=''):
    """通过 tg_bot 推送告警，未配置或去重窗口内则跳过"""
    if not _tg_send_message or not _tg_admin_chat_id:
        logger.warning("TG bot 未配置，跳过告警推送: %s %s", domain, reason)
        return
    if not _should_send_alert(domain, reason):
        logger.info("告警去重窗口内，跳过推送: %s %s", domain, reason)
        return
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    msg = (
        f"🔴 <b>sub-* 直连路径告警</b>\n"
        f"⏰ {ts}\n"
        f"🌍 检测源: {COUNTRY_CODE}\n"
        f"🌐 域名: <code>{domain}:{SUB_PORT}</code>\n"
        f"❌ 原因: {reason}\n"
    )
    if detail:
        msg += f"📝 详情: {detail}\n"
    try:
        _tg_send_message(_tg_admin_chat_id, msg)
        logger.info("TG 告警已推送: %s %s", domain, reason)
    except Exception as e:
        logger.error("TG 告警推送失败: %s", e)


def test_sub_domain(domain, port=SUB_PORT):
    """对 sub-* 域名做 TLS 握手 + HTTP /info 请求
    返回: (是否成功, 延迟ms, 失败原因)
    参考 cdn_monitor.test_user_path_latency 的 TLS 握手 + HTTP 请求逻辑
    """
    sock = None
    ssock = None
    start = time.time()
    try:
        # 1. TCP 连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TLS_TIMEOUT)
        sock.connect((domain, port))

        # 2. TLS 握手（SNI = sub-* 域名，对应证书 SAN）
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ssock = ctx.wrap_socket(sock, server_hostname=domain)
        tls_time = (time.time() - start) * 1000

        # 3. HTTP GET /info 请求
        # /info 端点不需要 SUB_TOKEN 认证（见 subscription_service.py 注释）
        # SUB_TOKEN 仅作为标识头传入，便于服务端日志追踪
        headers = f"GET /info HTTP/1.1\r\nHost: {domain}\r\nConnection: close\r\n"
        if SUB_TOKEN:
            headers += f"X-Sub-Token: {SUB_TOKEN}\r\n"
        headers += "\r\n"
        ssock.sendall(headers.encode())

        # 读取响应状态行
        resp = ssock.recv(1024)
        if not resp:
            return False, (time.time() - start) * 1000, "HTTP 响应为空"

        status_line = resp.decode('utf-8', errors='ignore').split('\r\n')[0]
        parts = status_line.split()
        status_code = parts[1] if len(parts) >= 2 else '000'
        total_time = (time.time() - start) * 1000

        # 200 = 正常；401/403 = 服务在但认证异常（仍算可用，不误报）
        if status_code in ('200', '301', '302', '401', '403', '404'):
            return True, total_time, f"HTTP {status_code} (TLS={tls_time:.0f}ms)"
        else:
            return False, total_time, f"HTTP 状态码异常: {status_code}"

    except socket.timeout:
        return False, (time.time() - start) * 1000, "连接超时"
    except ssl.SSLError as e:
        return False, (time.time() - start) * 1000, f"TLS 握手失败: {e}"
    except ConnectionRefusedError:
        return False, (time.time() - start) * 1000, "连接被拒绝（服务未监听）"
    except socket.gaierror as e:
        return False, (time.time() - start) * 1000, f"DNS 解析失败: {e}"
    except Exception as e:
        return False, (time.time() - start) * 1000, f"未知错误: {e}"
    finally:
        try:
            if ssock:
                ssock.close()
        except Exception:
            pass
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def run_once():
    """单次检测所有 sub-* 域名（供 cron 调用）"""
    base_domain = _get_base_domain()
    if not base_domain:
        logger.error("无法从 CF_DOMAIN='%s' 提取基础域名，跳过检测", CF_DOMAIN)
        print(f"[sub_domain_monitor] CF_DOMAIN 未配置或格式异常: '{CF_DOMAIN}'")
        return

    logger.info("=" * 50)
    logger.info("sub-* 直连路径监控开始 - %s (检测源: %s)",
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'), COUNTRY_CODE)
    logger.info("=" * 50)

    results = []
    fail_count = 0
    for region in ALL_REGIONS:
        domain = _build_sub_domain(region, base_domain)
        ok, latency_ms, detail = test_sub_domain(domain)
        tag = "✅" if ok else "❌"
        logger.info("  %s %s:%d -> %s (%.0fms) %s",
                    tag, domain, SUB_PORT, "OK" if ok else "FAIL", latency_ms, detail)
        results.append((domain, ok, latency_ms, detail))
        if not ok:
            fail_count += 1
            send_tg_alert(domain, detail)

    summary = f"检测 {len(results)} 个域名, {fail_count} 个失败"
    logger.info("[完成] %s", summary)
    print(f"[sub_domain_monitor] {summary}")


if __name__ == '__main__':
    run_once()
