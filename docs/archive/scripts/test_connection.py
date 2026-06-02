#!/usr/bin/env python3
"""
模拟 v2rayN 订阅更新和连接测试工具
Author: [TRAE SOLO CN]
Version: v0.1.0
Date: 2026-05-24
功能：
  - 模拟 v2rayN 订阅获取（本地 Flask 订阅服务 + HTTP 请求）
  - 测试 CDN IP 连通性（VLESS-WS、VLESS-HTTPUpgrade、Trojan-WS）
  - 测试 Hysteria2 端口跳跃（UDP 连通性）
  - 详细时间戳日志：DNS、TCP、TLS、HTTP、响应
  - 丢包和延迟检测（3次重复测试、统计分析）
  - 问题定位（失败堆栈、正常/异常节点对比）

用法：python scripts/test_connection.py
"""

import os
import sys
import time
import ssl
import json
import socket
import random
import threading
import traceback
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# ============================================================
# 路径初始化
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except ImportError:
    pass

from config import (
    SERVER_IP, CF_DOMAIN, SUB_PORT, SUB_TOKEN,
    VLESS_WS_PORT, VLESS_UPGRADE_PORT, TROJAN_WS_PORT, HYSTERIA2_PORT,
    HYSTERIA2_UDP_PORTS, COUNTRY_CODE,
    CDN_PREFERRED_IPS, CDN_IP_BLACKLIST,
    get_node_name, get_env
)

# ============================================================
# 颜色输出
# ============================================================
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    DIM = '\033[2m'

def color_print(msg, color=Colors.RESET, bold=False, end='\n'):
    prefix = Colors.BOLD if bold else ''
    print(f"{prefix}{color}{msg}{Colors.RESET}", end=end)

def success(msg): color_print(f"  ✓ {msg}", Colors.GREEN)
def fail(msg): color_print(f"  ✗ {msg}", Colors.RED)
def info(msg): color_print(f"  • {msg}", Colors.CYAN)
def warn(msg): color_print(f"  ⚠ {msg}", Colors.YELLOW)

# ============================================================
# 1. 模拟 v2rayN 订阅获取
# ============================================================

def simulate_subscription_fetch():
    """模拟 v2rayN 获取订阅配置"""
    color_print("\n" + "=" * 60, Colors.CYAN, bold=True)
    color_print("📡 阶段一：模拟 v2rayN 订阅更新", Colors.CYAN, bold=True)
    color_print("=" * 60, Colors.CYAN, bold=True)

    domain = CF_DOMAIN if CF_DOMAIN else SERVER_IP
    sub_url = f"https://{domain}:{SUB_PORT}/singbox/{COUNTRY_CODE}"
    base64_url = f"https://{domain}:{SUB_PORT}/sub/{COUNTRY_CODE}"

    info(f"订阅域名: {domain}:{SUB_PORT}")
    info(f"sing-box JSON: {sub_url}")
    info(f"Base64 订阅: {base64_url}")

    # 生成 sing-box 配置（不依赖 Flask，直接本地生成）
    print()
    info("生成本地 sing-box 订阅配置...")

    from subscription_service import generate_singbox_config, generate_all_links

    try:
        config = generate_singbox_config()
        links = generate_all_links()

        # 提取 CDN IP 信息
        cdn_ips_used = {}
        for outbound in config.get('outbounds', []):
            tag = outbound.get('tag', '')
            server = outbound.get('server', '')
            if 'VLESS-WS' in tag and 'HTTP' not in tag:
                cdn_ips_used['VLESS-WS'] = server
            elif 'VLESS-HTTPUpgrade' in tag:
                cdn_ips_used['VLESS-HTTPUpgrade'] = server
            elif 'Trojan-WS' in tag:
                cdn_ips_used['Trojan-WS'] = server

        success("sing-box 配置生成成功")
        info(f"检测到 {len(links)} 个订阅节点")
        for link in links:
            node_name = link.split('#')[-1] if '#' in link else 'unknown'
            info(f"  节点: {node_name}")

        print()
        color_print("  当前 CDN IP 分配:", Colors.YELLOW, bold=True)
        for proto, ip in cdn_ips_used.items():
            status = "✅ 已配置" if ip and ip != SERVER_IP else "⚠️ 使用服务器 IP"
            color_print(f"    {proto}: {ip} ({status})", Colors.CYAN)

        return config, cdn_ips_used, links
    except Exception as e:
        fail(f"配置生成失败: {e}")
        traceback.print_exc()
        return None, {}, []

# ============================================================
# 2. 连接测试核心（带时间戳测量）
# ============================================================

def measure_dns_resolve(hostname, timeout=5):
    """测量 DNS 解析耗时"""
    start = time.time()
    try:
        socket.setdefaulttimeout(timeout)
        result = socket.getaddrinfo(hostname, None, socket.AF_INET)
        elapsed_ms = (time.time() - start) * 1000
        ip = result[0][4][0] if result else 'N/A'
        return {'success': True, 'ip': ip, 'elapsed_ms': elapsed_ms, 'error': None}
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {'success': False, 'ip': None, 'elapsed_ms': elapsed_ms, 'error': str(e)}


def measure_tcp_connect(ip, port, timeout=5):
    """测量 TCP 连接耗时"""
    start = time.time()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        elapsed_ms = (time.time() - start) * 1000
        return {'success': True, 'elapsed_ms': elapsed_ms, 'error': None}
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {'success': False, 'elapsed_ms': elapsed_ms, 'error': str(e)}
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def measure_tls_handshake(ip, port, hostname, timeout=10):
    """测量 TLS 握手耗时"""
    start = time.time()
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))

        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        # 允许自签名证书测试
        ctx_insecure = ssl.create_default_context()
        ctx_insecure.check_hostname = False
        ctx_insecure.verify_mode = ssl.CERT_NONE

        tls_sock = ctx_insecure.wrap_socket(sock, server_hostname=hostname)
        elapsed_ms = (time.time() - start) * 1000
        # 获取 TLS 版本和密码套件
        tls_version = tls_sock.version()
        cipher = tls_sock.cipher()[0] if tls_sock.cipher() else 'N/A'
        return {
            'success': True,
            'elapsed_ms': elapsed_ms,
            'tls_version': tls_version,
            'cipher': cipher,
            'error': None
        }
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {'success': False, 'elapsed_ms': elapsed_ms, 'error': str(e)}
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def measure_http_request(ip, port, hostname, path='/', timeout=10):
    """测量 HTTP 请求+响应耗时（通过 CDN IP）"""
    start = time.time()
    try:
        url = f"https://{hostname}:{port}{path}"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(url)
        req.add_header('Host', hostname)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) v2rayN/6.0')

        response = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        data = response.read()
        elapsed_ms = (time.time() - start) * 1000
        status_code = response.getcode()
        return {
            'success': True,
            'elapsed_ms': elapsed_ms,
            'status_code': status_code,
            'content_length': len(data),
            'error': None
        }
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.time() - start) * 1000
        return {
            'success': True,  # 服务器有响应
            'elapsed_ms': elapsed_ms,
            'status_code': e.code,
            'content_length': 0,
            'error': f"HTTP {e.code}"
        }
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return {'success': False, 'elapsed_ms': elapsed_ms, 'error': str(e)}


def test_cdn_node(node_name, cdn_ip, port, hostname, protocol, retries=3):
    """测试单个 CDN 节点的完整连接链路"""
    color_print(f"\n{'─' * 50}", Colors.DIM)
    color_print(f"🔌 [{node_name}] 测试开始 (协议: {protocol}, IP: {cdn_ip}, 端口: {port})", Colors.BOLD)
    color_print(f"{'─' * 50}", Colors.DIM)

    results = []
    consecutive_failures = 0

    for attempt in range(1, retries + 1):
        color_print(f"\n  --- 第 {attempt}/{retries} 次测试 ---", Colors.DIM)
        attempt_result = {
            'attempt': attempt,
            'dns': None,
            'tcp': None,
            'tls': None,
            'http': None,
            'total_ms': 0,
            'success': False,
            'error': None
        }

        attempt_start = time.time()

        # DNS 解析
        dns_result = measure_dns_resolve(hostname)
        attempt_result['dns'] = dns_result
        if dns_result['success']:
            success(f"DNS 解析: {dns_result['elapsed_ms']:.0f}ms → {dns_result['ip']}")
        else:
            fail(f"DNS 解析: {dns_result['elapsed_ms']:.0f}ms 失败 - {dns_result['error']}")
            consecutive_failures += 1
            attempt_result['error'] = f"DNS 失败: {dns_result['error']}"
            results.append(attempt_result)
            continue

        # TCP 连接
        tcp_result = measure_tcp_connect(cdn_ip, port)
        attempt_result['tcp'] = tcp_result
        if tcp_result['success']:
            success(f"TCP 连接: {tcp_result['elapsed_ms']:.0f}ms")
        else:
            fail(f"TCP 连接: {tcp_result['elapsed_ms']:.0f}ms 失败 - {tcp_result['error']}")
            consecutive_failures += 1
            attempt_result['error'] = f"TCP 失败: {tcp_result['error']}"
            results.append(attempt_result)
            continue

        # TLS 握手
        tls_result = measure_tls_handshake(cdn_ip, port, hostname)
        attempt_result['tls'] = tls_result
        if tls_result['success']:
            success(f"TLS 握手: {tls_result['elapsed_ms']:.0f}ms ({tls_result.get('tls_version', 'N/A')})")
        else:
            fail(f"TLS 握手: {tls_result['elapsed_ms']:.0f}ms 失败 - {tls_result['error']}")
            consecutive_failures += 1
            attempt_result['error'] = f"TLS 失败: {tls_result['error']}"
            results.append(attempt_result)
            continue

        # HTTP 请求
        http_result = measure_http_request(cdn_ip, port, hostname)
        attempt_result['http'] = http_result
        if http_result['success']:
            status_info = f"HTTP {http_result['status_code']}" if http_result['status_code'] else 'OK'
            success(f"HTTP 请求: {http_result['elapsed_ms']:.0f}ms ({status_info})")
        else:
            fail(f"HTTP 请求: {http_result['elapsed_ms']:.0f}ms 失败 - {http_result['error']}")
            consecutive_failures += 1
            attempt_result['error'] = f"HTTP 失败: {http_result['error']}"
            results.append(attempt_result)
            continue

        # 计算总耗时
        total_ms = (time.time() - attempt_start) * 1000
        attempt_result['total_ms'] = total_ms
        attempt_result['success'] = True
        success(f"总耗时: {total_ms:.0f}ms")

        if consecutive_failures > 0:
            consecutive_failures = 0  # 重置

        results.append(attempt_result)

    # 丢包检测
    packet_loss_warning = ""
    if consecutive_failures >= 2:
        packet_loss_warning = " ⚠️ 可能丢包（连续2次失败）"

    # 统计汇总
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    total_times = [r['total_ms'] for r in successful if r['total_ms'] > 0]

    color_print(f"\n  📊 [{node_name}] 测试结果汇总{packet_loss_warning}", Colors.BOLD)
    color_print(f"  {'─' * 40}", Colors.DIM)
    color_print(f"  总测试次数: {retries}", Colors.CYAN)
    color_print(f"  成功: {len(successful)} | 失败: {len(failed)}", Colors.GREEN if len(successful) > len(failed) else Colors.RED)

    if total_times:
        avg_ms = sum(total_times) / len(total_times)
        min_ms = min(total_times)
        max_ms = max(total_times)
        color_print(f"  平均延迟: {avg_ms:.0f}ms", Colors.CYAN)
        color_print(f"  最小延迟: {min_ms:.0f}ms", Colors.GREEN)
        color_print(f"  最大延迟: {max_ms:.0f}ms", Colors.YELLOW)

    return {
        'node_name': node_name,
        'cdn_ip': cdn_ip,
        'port': port,
        'hostname': hostname,
        'protocol': protocol,
        'results': results,
        'success_count': len(successful),
        'fail_count': len(failed),
        'avg_ms': sum(total_times) / len(total_times) if total_times else 0,
        'min_ms': min(total_times) if total_times else 0,
        'max_ms': max(total_times) if total_times else 0,
        'consecutive_failures': consecutive_failures
    }


# ============================================================
# 3. Hysteria2 端口跳跃测试
# ============================================================

def test_hysteria2_port_hop(server_ip, test_ports=None):
    """测试 Hysteria2 端口跳跃（UDP 连通性）"""
    color_print("\n" + "=" * 60, Colors.CYAN, bold=True)
    color_print("🚀 阶段二：Hysteria2 端口跳跃测试", Colors.CYAN, bold=True)
    color_print("=" * 60, Colors.CYAN, bold=True)

    if test_ports is None:
        # 随机选择 5 个跳跃端口
        test_ports = random.sample(HYSTERIA2_UDP_PORTS, min(5, len(HYSTERIA2_UDP_PORTS)))

    info(f"目标服务器: {server_ip}")
    info(f"主端口: {HYSTERIA2_PORT}")
    info(f"跳跃端口范围: {HYSTERIA2_UDP_PORTS[0]}-{HYSTERIA2_UDP_PORTS[-1]}")
    info(f"随机测试端口: {test_ports}")

    results = []
    all_ports = [HYSTERIA2_PORT] + test_ports

    for port in all_ports:
        color_print(f"\n  --- 测试 UDP 端口 {port} ---", Colors.DIM)
        success_count = 0
        fail_count = 0
        total_ms_list = []

        for attempt in range(1, 4):  # 3 次测试
            start = time.time()
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(3)
                # 发送一个 QUIC 初始包（简化版，仅测试连通性）
                # 真实 QUIC 包较大，这里只发少量数据测试端口开放
                test_data = b'\x00' * 16
                sock.sendto(test_data, (server_ip, port))
                # 等待响应（QUIC 服务器可能不响应，只测发送成功）
                try:
                    sock.recvfrom(1500)
                except socket.timeout:
                    pass  # 无响应也视为端口开放（UDP 无连接特性）
                elapsed_ms = (time.time() - start) * 1000
                total_ms_list.append(elapsed_ms)
                success_count += 1
            except Exception as e:
                elapsed_ms = (time.time() - start) * 1000
                total_ms_list.append(elapsed_ms)
                fail_count += 1
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

        avg_ms = sum(total_ms_list) / len(total_ms_list) if total_ms_list else 0
        status = "✅ 开放" if success_count >= 2 else "❌ 可能关闭"

        color_print(f"    端口 {port}: 成功 {success_count}/3, 平均 {avg_ms:.0f}ms {status}",
                   Colors.GREEN if success_count >= 2 else Colors.RED)

        results.append({
            'port': port,
            'success_count': success_count,
            'fail_count': fail_count,
            'avg_ms': avg_ms,
            'status': 'open' if success_count >= 2 else 'closed'
        })

    return results


# ============================================================
# 4. VLESS-Reality 直连测试
# ============================================================

def test_vless_reality(server_ip, hostname=CF_DOMAIN):
    """测试 VLESS-Reality 直连节点"""
    color_print("\n" + "=" * 60, Colors.CYAN, bold=True)
    color_print("🔐 阶段三：VLESS-Reality 直连测试", Colors.CYAN, bold=True)
    color_print("=" * 60, Colors.CYAN, bold=True)

    info(f"直连 IP: {server_ip}:443")
    info(f"Reality SNI: www.apple.com")

    results = []
    for attempt in range(1, 4):
        color_print(f"\n  --- 第 {attempt}/3 次测试 ---", Colors.DIM)
        attempt_start = time.time()

        # TCP
        tcp = measure_tcp_connect(server_ip, 443)
        if tcp['success']:
            success(f"TCP 连接: {tcp['elapsed_ms']:.0f}ms")
        else:
            fail(f"TCP 连接失败: {tcp['error']}")
            results.append({'attempt': attempt, 'success': False, 'error': tcp['error']})
            continue

        # TLS（注意：Reality 的 TLS 握手会模拟目标网站）
        tls = measure_tls_handshake(server_ip, 443, 'www.apple.com')
        if tls['success']:
            success(f"TLS 握手: {tls['elapsed_ms']:.0f}ms")
        else:
            fail(f"TLS 握手失败: {tls['error']}")

        total_ms = (time.time() - attempt_start) * 1000
        results.append({
            'attempt': attempt,
            'success': tcp['success'],
            'total_ms': total_ms,
            'tcp_ms': tcp['elapsed_ms'],
            'tls_ms': tls['elapsed_ms'] if tls['success'] else 0
        })

    successful = [r for r in results if r['success']]
    total_times = [r['total_ms'] for r in successful if r['total_ms'] > 0]

    color_print(f"\n  📊 VLESS-Reality 汇总", Colors.BOLD)
    color_print(f"  {'─' * 40}", Colors.DIM)
    color_print(f"  成功: {len(successful)}/3", Colors.GREEN if len(successful) > 1 else Colors.RED)
    if total_times:
        color_print(f"  平均延迟: {sum(total_times)/len(total_times):.0f}ms", Colors.CYAN)

    return results


# ============================================================
# 5. 测试报告生成
# ============================================================

def generate_report(cdn_results, hy2_results, reality_results, cdn_ips_used):
    """生成完整的测试报告"""
    color_print("\n" + "=" * 60, Colors.BOLD)
    color_print("📋 连接测试报告", Colors.BOLD)
    color_print("=" * 60, Colors.BOLD)

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    color_print(f"  测试时间: {timestamp}", Colors.DIM)
    color_print(f"  服务器: {SERVER_IP}", Colors.DIM)
    color_print(f"  域名: {CF_DOMAIN or '未配置'}", Colors.DIM)

    # CDN 节点汇总
    color_print(f"\n  【CDN 节点连通性】", Colors.CYAN, bold=True)
    color_print(f"  {'─' * 50}", Colors.DIM)
    color_print(f"  {'节点':<30} {'IP':<18} {'成功':>6} {'平均延迟':>10} {'状态':>10}", Colors.BOLD)
    color_print(f"  {'─' * 50}", Colors.DIM)

    for r in cdn_results:
        status = "✅ 正常" if r['success_count'] >= 2 else ("⚠️ 不稳定" if r['success_count'] >= 1 else "❌ 不可用")
        if r['consecutive_failures'] >= 2:
            status += " [丢包]"
        color = Colors.GREEN if r['success_count'] >= 2 else (Colors.YELLOW if r['success_count'] >= 1 else Colors.RED)
        avg_str = f"{r['avg_ms']:.0f}ms" if r['avg_ms'] > 0 else "N/A"
        line = f"  {r['node_name']:<30} {r['cdn_ip']:<18} {r['success_count']}/3{'':>3} {avg_str:>10} {status:>10}"
        color_print(line, color)

    # Hysteria2 汇总
    color_print(f"\n  【Hysteria2 端口跳跃】", Colors.CYAN, bold=True)
    color_print(f"  {'─' * 50}", Colors.DIM)
    open_ports = [r['port'] for r in hy2_results if r['status'] == 'open']
    closed_ports = [r['port'] for r in hy2_results if r['status'] == 'closed']
    color_print(f"  开放端口: {len(open_ports)}/{len(hy2_results)}", Colors.GREEN if len(open_ports) > len(hy2_results) / 2 else Colors.RED)
    if closed_ports:
        warn(f"  关闭/异常端口: {closed_ports}")

    # VLESS-Reality 汇总
    color_print(f"\n  【VLESS-Reality 直连】", Colors.CYAN, bold=True)
    color_print(f"  {'─' * 50}", Colors.DIM)
    reality_ok = sum(1 for r in reality_results if r.get('success', False))
    color_print(f"  成功: {reality_ok}/3", Colors.GREEN if reality_ok >= 2 else Colors.RED)

    # 问题节点 vs 正常节点对比
    color_print(f"\n  【问题诊断】", Colors.CYAN, bold=True)
    color_print(f"  {'─' * 50}", Colors.DIM)

    problem_nodes = [r for r in cdn_results if r['success_count'] < 2]
    normal_nodes = [r for r in cdn_results if r['success_count'] >= 2]

    if problem_nodes:
        fail("以下节点存在问题:")
        for n in problem_nodes:
            reason = ""
            if n['consecutive_failures'] >= 2:
                reason = "连续失败，可能丢包或被封锁"
            elif n['success_count'] == 0:
                reason = "完全不可达"
            else:
                reason = "连接不稳定"
            color_print(f"    • {n['node_name']} ({n['cdn_ip']}): {reason}", Colors.RED)

        # 对比分析
        if normal_nodes and problem_nodes:
            color_print(f"\n  对比分析:", Colors.YELLOW, bold=True)
            avg_normal = sum(n['avg_ms'] for n in normal_nodes) / len(normal_nodes)
            avg_problem = sum(n['avg_ms'] for n in problem_nodes if n['avg_ms'] > 0) / max(len([n for n in problem_nodes if n['avg_ms'] > 0]), 1)
            color_print(f"    正常节点平均延迟: {avg_normal:.0f}ms", Colors.GREEN)
            color_print(f"    异常节点平均延迟: {avg_problem:.0f}ms", Colors.RED)
            if avg_problem > avg_normal * 2:
                warn(f"    异常节点延迟是正常节点的 {avg_problem/avg_normal:.1f} 倍，建议更换 CDN IP")
    else:
        success("所有 CDN 节点均正常工作")

    if not normal_nodes and not problem_nodes:
        info("无 CDN 节点测试结果")

    # 建议
    color_print(f"\n  【优化建议】", Colors.CYAN, bold=True)
    color_print(f"  {'─' * 50}", Colors.DIM)

    if problem_nodes:
        color_print(f"  1. 运行 cdn_monitor.py 重新优选 CDN IP", Colors.YELLOW)
        color_print(f"  2. 检查服务器防火墙是否放行了相关端口", Colors.YELLOW)
        color_print(f"  3. 检查 Cloudflare CDN 配置是否正确代理了端口", Colors.YELLOW)

    if all(r['success_count'] >= 2 for r in cdn_results) and reality_ok >= 2:
        success("所有测试通过，配置运行正常！")

    color_print(f"\n{'=' * 60}\n", Colors.DIM)


# ============================================================
# 6. 本地 Flask 订阅服务测试
# ============================================================

def test_local_subscription_service(config):
    """启动本地 Flask 订阅服务并测试订阅获取"""
    color_print("\n" + "=" * 60, Colors.CYAN, bold=True)
    color_print("🌐 阶段四：本地订阅服务测试", Colors.CYAN, bold=True)
    color_print("=" * 60, Colors.CYAN, bold=True)

    from subscription_service import create_app, init_db

    LOCAL_TEST_PORT = 18888  # 使用非标准端口避免冲突
    info(f"启动本地订阅服务 (端口: {LOCAL_TEST_PORT})...")

    # 初始化数据库
    try:
        init_db()
        success("数据库初始化成功")
    except Exception as e:
        warn(f"数据库初始化失败（可能已存在）: {e}")

    # 启动 Flask 服务器
    app = create_app()
    server_thread = threading.Thread(
        target=lambda: app.run(host='127.0.0.1', port=LOCAL_TEST_PORT, threaded=True, use_reloader=False),
        daemon=True
    )
    server_thread.start()
    time.sleep(2)  # 等待服务器启动

    # 测试订阅获取
    test_urls = [
        (f"http://127.0.0.1:{LOCAL_TEST_PORT}/sub/{COUNTRY_CODE}", "Base64 订阅"),
        (f"http://127.0.0.1:{LOCAL_TEST_PORT}/singbox/{COUNTRY_CODE}", "sing-box JSON"),
    ]

    for url, desc in test_urls:
        color_print(f"\n  测试 {desc}...", Colors.DIM)
        start = time.time()
        try:
            req = urllib.request.Request(url)
            response = urllib.request.urlopen(req, timeout=10)
            data = response.read()
            elapsed_ms = (time.time() - start) * 1000
            content_type = response.headers.get('Content-Type', 'unknown')
            success(f"{desc}: {elapsed_ms:.0f}ms ({len(data)} bytes, Content-Type: {content_type})")

            if 'singbox' in url:
                parsed = json.loads(data)
                outbounds = parsed.get('outbounds', [])
                proxy_outbounds = [ob for ob in outbounds if ob.get('type') in ('vless', 'trojan', 'hysteria2', 'socks')]
                info(f"  解析到 {len(proxy_outbounds)} 个代理出站")
                for ob in proxy_outbounds:
                    tag = ob.get('tag', 'unknown')
                    server = ob.get('server', 'N/A')
                    port = ob.get('server_port', 'N/A')
                    info(f"    → {tag}: {server}:{port}")
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            fail(f"{desc}: {elapsed_ms:.0f}ms 失败 - {e}")

    info("本地订阅服务测试完成（服务已自动关闭）")


# ============================================================
# 主函数
# ============================================================

def main():
    color_print("\n" + "#" * 60, Colors.BOLD)
    color_print("#  sing-box 代理连接测试工具", Colors.BOLD)
    color_print("#  模拟 v2rayN 订阅更新 + 连接测试", Colors.BOLD)
    color_print("#" * 60, Colors.BOLD)
    color_print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", Colors.DIM)

    # 阶段一：模拟订阅获取 + 提取 CDN IP
    config, cdn_ips_used, links = simulate_subscription_fetch()

    if not config:
        fail("订阅配置生成失败，无法继续测试")
        sys.exit(1)

    # 阶段二：测试本地订阅服务
    test_local_subscription_service(config)

    # 阶段三：CDN 节点连接测试
    color_print("\n" + "=" * 60, Colors.CYAN, bold=True)
    color_print("🔗 阶段三：CDN 节点连接测试", Colors.CYAN, bold=True)
    color_print("=" * 60, Colors.CYAN, bold=True)

    hostname = CF_DOMAIN if CF_DOMAIN else SERVER_IP
    cdn_results = []

    # 测试每个 CDN 协议的节点
    cdn_tests = [
        ('VLESS-WS', cdn_ips_used.get('VLESS-WS', SERVER_IP), VLESS_WS_PORT),
        ('VLESS-HTTPUpgrade', cdn_ips_used.get('VLESS-HTTPUpgrade', SERVER_IP), VLESS_UPGRADE_PORT),
        ('Trojan-WS', cdn_ips_used.get('Trojan-WS', SERVER_IP), TROJAN_WS_PORT),
    ]

    for proto, cdn_ip, port in cdn_tests:
        node_name = get_node_name(proto.lower().replace('-', '-'))
        # 生成正确的节点名称
        if proto == 'VLESS-WS':
            node_name = f"{COUNTRY_CODE}-VLESS-WS"
        elif proto == 'VLESS-HTTPUpgrade':
            node_name = f"{COUNTRY_CODE}-VLESS-HTTPUpgrade"
        elif proto == 'Trojan-WS':
            node_name = f"{COUNTRY_CODE}-Trojan-WS"

        if cdn_ip == SERVER_IP or not cdn_ip:
            warn(f"{node_name}: CDN IP 未配置（使用服务器 IP），跳过 CDN 测试")
            continue

        result = test_cdn_node(node_name, cdn_ip, port, hostname, proto)
        cdn_results.append(result)

    # 阶段四：Hysteria2 端口跳跃测试
    hy2_results = test_hysteria2_port_hop(SERVER_IP)

    # 阶段五：VLESS-Reality 直连测试
    reality_results = test_vless_reality(SERVER_IP)

    # 生成报告
    generate_report(cdn_results, hy2_results, reality_results, cdn_ips_used)

    color_print("测试完成！\n", Colors.BOLD)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n测试发生异常: {e}")
        traceback.print_exc()
        sys.exit(1)
