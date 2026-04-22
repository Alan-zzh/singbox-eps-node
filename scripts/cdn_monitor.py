#!/usr/bin/env python3
"""
CDN监控脚本
Author: Alan
Version: v1.0.82
Date: 2026-04-23
功能：
  - 本地实测IP池优先，外部API补充
  - TCPing验证可达性
  - 每小时自动更新，确保始终使用最优IP
  - 自动分配每个协议独立IP

⚠️ CDN优选IP获取策略（按优先级）：
  1. 本地实测IP池（CDN_PREFERRED_IPS）- 最优先！
     - 162.159.x.x / 172.64.x.x 段，中国用户实测50ms
     - TCPing验证可达性，不可达自动替换
     - 【Bug #27 避坑】：外部API从日本服务器获取的IP（104.18.x.x段）对中国延迟高
  2. cf.001315.xyz/ct电信API（补充方案1）
     - 返回格式为 `IP#电信`，解析提取电信专用IP
     - 仅本地池不足时触发
  3. WeTest.vip电信优选DNS（补充方案2）
     - 通过DNS解析获取电信线路最优IP
     - ⚠️ 从日本服务器用8.8.8.8解析可能返回104.18.x.x段（高延迟），需筛选
  4. IPDB API bestcf（最后补充）
     - 返回通用优选IP，不按运营商分类

历史教训：
  - v1.0.36用日本服务器DNS实时解析，返回的IP对中国延迟150-200ms
  - v1.0.37恢复固定IP池，但IP可能过期失效
  - v1.0.45改用指定DNS解析+固定IP池降级，但指定DNS从日本不可达
  - v1.0.55改用中国DoH解析+优选IP池TCPing验证可达性
  - v1.0.56改用IPDB API获取实时优选IP，但不按运营商分类
  - v1.0.57改用WeTest.vip电信优选DNS，按运营商分类获取最优IP
"""

import os
import sys
import time
import sqlite3
import json
import socket
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import (
        SERVER_IP, DATA_DIR, CF_DOMAIN,
        CDN_MONITOR_INTERVAL, CDN_TOP_IPS_COUNT,
        CDN_PREFERRED_IPS, CDN_API_WETEST_CT, CDN_API_IPDB, CDN_API_001315_CT,
    )
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)
    CDN_PREFERRED_IPS = [
        '162.159.45.66', '162.159.39.48', '172.64.53.253',
        '162.159.44.192', '172.64.52.244', '162.159.38.190',
        '108.162.198.29', '162.159.15.207', '162.159.19.243',
        '162.159.58.128', '162.159.38.180', '108.162.198.116',
        '172.64.53.134', '162.159.39.89', '162.159.45.244',
        '162.159.44.128', '172.64.52.173', '172.64.33.166',
        '172.64.53.179', '172.64.52.205', '108.162.198.145',
        '104.16.123.96', '104.16.124.96', '104.17.136.90',
    ]
    CDN_API_WETEST_CT = 'ct.cloudflare.182682.xyz'
    CDN_API_IPDB = 'https://ipdb.api.030101.xyz/?type=bestcf'
    CDN_API_001315_CT = 'https://cf.001315.xyz/ct'
    CDN_MONITOR_INTERVAL = 3600
    CDN_TOP_IPS_COUNT = 5

logger = get_logger('cdn_monitor')

DNS_SERVER = '8.8.8.8'

IPDB_API_URL = CDN_API_IPDB

# 湖南电信最优IP段（从实测数据提炼）
# 162.159.x.x / 172.64.x.x / 108.162.x.x 段对湖南电信延迟最低(50-53ms)
# 104.16-21.x.x 段对湖南电信延迟高(130ms+)，需要过滤掉
HUNAN_CT_OPTIMAL_PREFIXES = ('162.159.', '172.64.', '108.162.', '198.41.', '173.245.')

TCPING_PORT = 443
TCPING_TIMEOUT = 3


def is_hunan_ct_optimal(ip):
    """判断IP是否属于湖南电信最优IP段
    
    从uouin.com实测数据提炼：
    - 162.159.x.x / 172.64.x.x / 108.162.x.x 段延迟50-53ms
    - 198.41.x.x / 173.245.x.x 段延迟50-55ms
    - 104.16-21.x.x 段延迟130ms+，需要过滤
    """
    return any(ip.startswith(prefix) for prefix in HUNAN_CT_OPTIMAL_PREFIXES)


def init_db():
    """初始化数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    db_path = os.path.join(DATA_DIR, 'singbox.db')
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cdn_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path


def tcping(ip, port=TCPING_PORT, timeout=TCPING_TIMEOUT):
    """TCPing测试：验证IP端口可达性"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def resolve_dns(dns_name, dns_server=DNS_SERVER, timeout=10):
    """通过指定DNS服务器解析域名，返回IP列表
    
    使用dig命令解析，从日本服务器用Google DNS(8.8.8.8)解析
    WeTest.vip的电信优选域名，获取电信线路最优IP。
    """
    try:
        result = subprocess.run(
            ['dig', '+short', dns_name, f'@{dns_server}', '+time=5'],
            capture_output=True, text=True, timeout=timeout
        )
        ips = []
        for line in result.stdout.strip().split('\n'):
            ip = line.strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        return ips
    except Exception as e:
        logger.warning(f"  DNS解析 {dns_name} 失败: {e}")
        return []


def fetch_from_wetest_ct():
    """从WeTest.vip电信优选DNS获取IP
    
    WeTest.vip提供按运营商分类的Cloudflare优选IP：
    - ct.cloudflare.182682.xyz — 电信优选
    - cm.cloudflare.182682.xyz — 移动优选
    - cu.cloudflare.182682.xyz — 联通优选
    
    每15分钟更新，从Google DNS(8.8.8.8)解析即可获取。
    返回的IP已按电信用户延迟排序。
    """
    logger.info(f"  查询WeTest.vip电信优选: {CDN_API_WETEST_CT}")
    ips = resolve_dns(CDN_API_WETEST_CT)
    # 筛选湖南电信最优IP段，过滤掉104.16-21段
    filtered = [ip for ip in ips if is_hunan_ct_optimal(ip)]
    if filtered:
        logger.info(f"  WeTest电信返回 {len(ips)} 个IP，筛选后 {len(filtered)} 个: {filtered}")
    elif ips:
        logger.info(f"  WeTest电信返回 {len(ips)} 个IP，但无湖南电信最优段，全部保留")
        filtered = ips
    else:
        logger.warning("  WeTest电信DNS无响应")
        filtered = []
    return filtered


def fetch_from_001315_ct():
    """从cf.001315.xyz/ct获取电信优选IP

    cf.001315.xyz提供按运营商分类的Cloudflare优选IP：
    - /ct — 电信优选
    - /cm — 移动优选
    - /cu — 联通优选

    返回格式为 `IP#电信`，每行一个，需解析提取IP部分。
    """
    try:
        import urllib.request
        req = urllib.request.Request(CDN_API_001315_CT)
        req.add_header('User-Agent', 'Mozilla/5.0')

        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()

        ips = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 格式为 `IP#电信`，提取#前面的IP
            ip = line.split('#')[0].strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        if ips:
            logger.info(f"  001315电信API返回 {len(ips)} 个IP: {ips[:5]}...")
        else:
            logger.warning("  001315电信API返回空列表")
        return ips
    except Exception as e:
        logger.warning(f"  001315电信API获取失败: {e}")
        return []


def fetch_from_ipdb_api():
    """从IPDB API获取通用优选IP（降级方案3，不按运营商分类，需筛选）"""
    try:
        import urllib.request
        req = urllib.request.Request(IPDB_API_URL)
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8').strip()
        
        ips = []
        for line in content.split('\n'):
            ip = line.strip()
            if ip and len(ip.split('.')) == 4 and ip[0].isdigit():
                ips.append(ip)
        # 筛选湖南电信最优IP段
        filtered = [ip for ip in ips if is_hunan_ct_optimal(ip)]
        if filtered:
            logger.info(f"  IPDB返回 {len(ips)} 个IP，筛选后 {len(filtered)} 个: {filtered[:5]}...")
        elif ips:
            logger.info(f"  IPDB返回 {len(ips)} 个IP，但无湖南电信最优段，全部保留")
            filtered = ips
        else:
            logger.warning("  IPDB API返回空列表")
        return filtered
    except Exception as e:
        logger.warning(f"  IPDB API获取失败: {e}")
        return []


def fetch_cdn_ips():
    """获取优选IP（4级降级保障机制，确保主方案失效时自动切换备选方案）

    【4级降级策略 - 按优先级自动切换】
    
    ⚠️ 重要：本地实测IP池优先！外部API仅作补充。
    这是Bug #27的教训：外部API从日本服务器获取的IP（104.18.x.x段）对中国延迟高。
    
    第1级：本地实测IP池（CDN_PREFERRED_IPS）- 最优先！
       - 162.159.x.x / 172.64.x.x 段，中国用户实测50ms
       - TCPing验证可达性，不可达自动跳过
       - 【Bug #27 避坑】：WeTest.vip从日本服务器解析返回104.18.x.x段，延迟150-200ms
    
    第2级：cf.001315.xyz/ct电信API（补充实时IP）
       - 当第1级IP数量不足时触发
       - 返回格式为 `IP#电信`，按运营商分类，电信线路专属IP
    
    第3级：WeTest.vip电信优选DNS（补充方案2）
       - 当第1、2级都不够时触发
       - ⚠️ 从日本服务器用8.8.8.8解析可能返回104.18.x.x段，需筛选
    
    第4级：IPDB API bestcf（通用优选IP，需筛选）
       - 当第1、2、3级都不够时触发
       - 返回通用优选IP，不按运营商分类
    
    【为什么本地池优先？- Bug #27教训】
    - WeTest.vip从日本服务器用8.8.8.8解析，返回104.18.x.x段
    - 104.18.x.x段对中国用户延迟150-200ms，远高于本地池的50ms
    - 本地池（162.159.x.x / 172.64.x.x）是湖南电信实测最优IP
    - 策略：本地池优先，外部API仅补充不足部分
    
    【自动切换逻辑】
    - 不是"主方案挂了才切备选"，而是"主方案不够就补备选"
    - 每一级都尝试获取IP，TCPing验证可达性后加入valid_ips
    - 达到CDN_TOP_IPS_COUNT（默认5个）就停止，避免浪费API请求
    - 如果某级API不可达，跳过该级，继续下一级
    - 所有方案都不可达时，使用本地降级IP池前5个
    
    【湖南电信最优IP段筛选】
    - 162.159.x.x / 172.64.x.x / 108.162.x.x 段延迟50-53ms（最优）
    - 198.41.x.x / 173.245.x.x 段延迟50-55ms（次优）
    - 104.16-21.x.x 段延迟130ms+（必须过滤）
    
    【实时同步机制】
    - 每小时自动检测一次IP可达性
    - 不可达IP自动替换为下一个可用IP
    - 确保每次更新都是实时同步的最新IP
    """
    # 【规则7 CDN IP避坑教训】：
    # v1.0.36 用日本服务器DNS实时解析，返回IP对中国用户延迟150-200ms
    # v1.0.37 恢复固定IP池（中国用户实测50ms左右）才是正确方案
    # WeTest.vip从日本服务器用8.8.8.8解析返回104.18.x.x段，对中国用户延迟高
    # 正确策略：固定IP池为主（实测最优）+ 外部API仅作补充
    valid_ips = []
    seen = set()
    
    # 记录各方案获取结果
    source_results = {
        '001315_api': False, 
        'wetest_dns': False,
        'ipdb_api': False,
        'local_pool': False
    }

    # ==================== 步骤1：本地实测IP池（中国用户实测最优，优先使用） ====================
    # 【规则7教训】：固定IP池24个IP是中国用户实测延迟50ms左右的优选IP
    # 必须优先使用！外部API从日本服务器获取的IP不一定对中国最优
    logger.info(f">>> 步骤1：本地实测IP池（中国用户实测最优，{len(CDN_PREFERRED_IPS)}个候选）")
    local_success = False
    for ip in CDN_PREFERRED_IPS:
        if tcping(ip):
            valid_ips.append(ip)
            seen.add(ip)
            logger.info(f"  {ip}(实测池): 可达")
            local_success = True
        else:
            logger.info(f"  {ip}(实测池): 不可达")
        if len(valid_ips) >= CDN_TOP_IPS_COUNT:
            break
    source_results['local_pool'] = local_success

    # 步骤2：cf.001315.xyz/ct电信API（补充，仅本地池不足时触发）
    if len(valid_ips) < CDN_TOP_IPS_COUNT:
        logger.info(f"\n>>> 步骤2：cf.001315.xyz/ct电信API（补充，还需{CDN_TOP_IPS_COUNT - len(valid_ips)}个）")
        ct_001315_ips = fetch_from_001315_ct()
        if ct_001315_ips:
            api_success = False
            for ip in ct_001315_ips:
                if ip not in seen:
                    seen.add(ip)
                    if tcping(ip):
                        valid_ips.append(ip)
                        logger.info(f"  {ip}(001315电信): 可达")
                        api_success = True
                    if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                        break
            source_results['001315_api'] = api_success
        else:
            logger.warning("  001315电信API无响应")

    # 步骤3：WeTest.vip电信优选DNS（补充，延迟较高仅作备选）
    # 【规则7教训】：从日本解析返回104.18.x.x段对中国用户延迟高，仅作补充
    if len(valid_ips) < CDN_TOP_IPS_COUNT:
        logger.info(f"\n>>> 步骤3：WeTest.vip电信优选DNS（补充，还需{CDN_TOP_IPS_COUNT - len(valid_ips)}个）")
        ct_ips = fetch_from_wetest_ct()
        if ct_ips:
            dns_success = False
            for ip in ct_ips:
                if ip not in seen:
                    seen.add(ip)
                    if tcping(ip):
                        valid_ips.append(ip)
                        logger.info(f"  {ip}(WeTest电信): 可达")
                        dns_success = True
                    if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                        break
            source_results['wetest_dns'] = dns_success
        else:
            logger.warning("  WeTest电信DNS无响应")

    # 步骤4：IPDB API（最后补充）
    if len(valid_ips) < CDN_TOP_IPS_COUNT:
        logger.info(f"\n>>> 步骤4：IPDB API（最后补充，还需{CDN_TOP_IPS_COUNT - len(valid_ips)}个）")
        ipdb_ips = fetch_from_ipdb_api()
        if ipdb_ips:
            logger.info(f"  返回 {len(ipdb_ips)} 个IP: {ipdb_ips[:5]}...")
            api_success = False
            for ip in ipdb_ips:
                if ip not in seen:
                    seen.add(ip)
                    if tcping(ip):
                        valid_ips.append(ip)
                        logger.info(f"  {ip}(IPDB): 可达")
                        api_success = True
                    if len(valid_ips) >= CDN_TOP_IPS_COUNT:
                        break
            source_results['ipdb_api'] = api_success
        else:
            logger.warning("  IPDB API无响应")

    # 自动切换状态报告
    logger.info(f"\n[自动切换状态报告]")
    for source, success in source_results.items():
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {source}: {status}")

    if valid_ips:
        logger.info(f"\n[OK] 验证通过 {len(valid_ips)} 个IP: {valid_ips[:CDN_TOP_IPS_COUNT]}")
        return valid_ips[:CDN_TOP_IPS_COUNT]
    else:
        logger.warning("[WARN] 所有方案均不可达，使用降级IP池前5个")
        return CDN_PREFERRED_IPS[:CDN_TOP_IPS_COUNT]


def assign_and_save_ips(ips):
    """分配并保存优选IP（每个协议独立IP）"""
    if not ips:
        return

    db_path = os.path.join(DATA_DIR, 'singbox.db')

    selected_ips = ips[:3] if len(ips) >= 3 else ips + [ips[0]] * (3 - len(ips))

    vless_ws_ip = selected_ips[0]
    vless_upgrade_ip = selected_ips[1]
    trojan_ws_ip = selected_ips[2]

    logger.info(f"\n>>> CDN优选IP（每个协议独立IP）:")
    logger.info(f"  VLESS-WS IP: {vless_ws_ip}")
    logger.info(f"  VLESS-HTTPUpgrade IP: {vless_upgrade_ip}")
    logger.info(f"  Trojan-WS IP: {trojan_ws_ip}")

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_ws_cdn_ip', vless_ws_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('vless_upgrade_cdn_ip', vless_upgrade_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('trojan_ws_cdn_ip', trojan_ws_ip))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ','.join(ips)))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
        conn.commit()
    finally:
        conn.close()
    logger.info(f"\n[OK] CDN优选IP已保存")


def run_once():
    """执行一次监控"""
    logger.info("\n" + "="*50)
    logger.info(f"CDN监控启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*50)

    ips = fetch_cdn_ips()
    if ips:
        assign_and_save_ips(ips)
    else:
        logger.error("[ERROR] 未获取到任何IP，跳过本次更新")

    logger.info(f"\n>>> 等待 {CDN_MONITOR_INTERVAL}秒后下次检测...")


if __name__ == '__main__':
    init_db()
    while True:
        try:
            run_once()
            time.sleep(CDN_MONITOR_INTERVAL)
        except KeyboardInterrupt:
            logger.info("CDN监控已停止")
            break
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            time.sleep(60)
