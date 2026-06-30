#!/usr/bin/env python3
"""
sing-box 断线诊断脚本
功能：SSH到远程服务器，分析 sing-box 日志中的断线模式
用法：
  python diagnose_disconnect.py                     # 诊断所有服务器
  python diagnose_disconnect.py 52.195.179.240      # 诊断指定IP
  python diagnose_disconnect.py jp                  # 诊断日本服务器（jp/sg）
  python diagnose_disconnect.py --hours 12          # 分析最近12小时
  python diagnose_disconnect.py --user admin        # 指定SSH用户
依赖：仅标准库（subprocess + ssh命令行）
"""

import os
import re
import sys
import argparse
import subprocess
import socket
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import paramiko
except ImportError:
    paramiko = None

# ============================================================
# 常量定义
# ============================================================

# 服务器列表（IP -> 元信息）
SERVERS = {
    '52.195.179.240': {
        'name': 'JP',
        'label': '🇯🇵 日本',
        'domain': 'jp.290372913.xyz',
    },
    '13.212.37.11': {
        'name': 'SG',
        'label': '🇸🇬 新加坡',
        'domain': 'sg.290372913.xyz',
    },
}

# 协议与端口映射（用于日志匹配）
# v4.14.0: VLESS-HTTPUpgrade (vless-upgrade/2053) 已下线，从协议映射中移除
PROTOCOLS = {
    'vless-reality': {'port': 443, 'label': 'VLESS-Reality', 'transport': 'tcp'},
    'vless-ws': {'port': 8443, 'label': 'VLESS-WS', 'transport': 'tcp'},
    'trojan-ws': {'port': 2083, 'label': 'Trojan-WS', 'transport': 'tcp'},
    'tuic': {'port_env': 'TUIC_PORT', 'label': 'TUIC v5', 'transport': 'udp'},
}

# 远程路径
REMOTE_BASE_DIR = '/root/singbox-eps-node'
REMOTE_LOG_FILE = '/var/log/singbox.log'

# 断线关键词（sing-box日志中的连接关闭/重置信号）
DISCONNECT_PATTERNS = [
    r'connection close',
    r'connection reset',
    r'connection refused',
    r'connection aborted',
    r'i/o timeout',
    r'read timeout',
    r'write timeout',
    r'broken pipe',
    r'reset by peer',
    r'EOF',
    r'dial tcp',
    r'dial udp',
]

# Cloudflare阻断关键词
CF_BLOCK_PATTERNS = [
    r'403',
    r'1020',
    r'Access denied',
    r'Bad Gateway',
    r'cloudflare',
]

EMOJI_MAP = {
    '🔍': '[INFO]',
    '✅': '[OK]',
    '❌': '[FAIL]',
    '⚠️': '[WARN]',
    '⚠': '[WARN]',
    '💡': '[TIP]',
    'ℹ️': '[INFO]',
    'ℹ': '[INFO]',
    '🇯🇵': 'JP',
    '🇸🇬': 'SG',
}

# ============================================================
# 工具函数
# ============================================================

def configure_stdout():
    """在Windows等非UTF-8终端中尽量避免UnicodeEncodeError。"""
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8', errors='backslashreplace')
            except Exception:
                pass


def safe_text(text):
    normalized = str(text)
    for src, target in EMOJI_MAP.items():
        normalized = normalized.replace(src, target)
    return normalized


def resolve_related_ip(env):
    candidate = (
        env.get('USER_PUBLIC_IP')
        or env.get('USER_IP')
        or env.get('CLIENT_PUBLIC_IP')
        or env.get('RELATED_IP')
    )
    if candidate:
        return candidate.strip()

    ddns_domain = env.get('USER_DDNS_DOMAIN', '').strip()
    if not ddns_domain:
        return ''

    try:
        return socket.gethostbyname(ddns_domain)
    except OSError:
        return ''

def load_env():
    """从项目根目录的.env文件加载环境变量"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    env = {}
    if not os.path.exists(env_path):
        return env
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    # 去除行内注释
                    for marker in (' #', '\t#'):
                        idx = v.find(marker)
                        if idx != -1:
                            v = v[:idx]
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def ssh_run(host, command, user='root', timeout=30):
    """优先通过paramiko执行SSH远程命令，失败再回退到ssh子进程。"""
    if paramiko is not None:
        env = load_env()
        credential_candidates = [
            (env.get('JP_SSH_IP'), env.get('JP_SSH_USER', 'root'), env.get('JP_SSH_PASS', '')),
            (env.get('SG_SSH_IP'), env.get('SG_SSH_USER', 'root'), env.get('SG_SSH_PASS', '')),
            (env.get('US_SSH_IP'), env.get('US_SSH_USER', 'root'), env.get('US_SSH_PASS', '')),
        ]
        matched = next((item for item in credential_candidates if item[0] == host and item[2]), None)
        if matched:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    host,
                    username=matched[1] or user,
                    password=matched[2],
                    timeout=min(timeout, 15),
                    allow_agent=False,
                    look_for_keys=False,
                )
                stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
                rc = stdout.channel.recv_exit_status()
                return (
                    stdout.read().decode('utf-8', 'replace').strip(),
                    stderr.read().decode('utf-8', 'replace').strip(),
                    rc,
                )
            except Exception:
                pass
            finally:
                client.close()

    ssh_cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', f'ConnectTimeout={min(timeout, 10)}',
        '-o', f'ServerAliveInterval=5',
        '-o', f'ServerAliveCountMax=3',
        f'{user}@{host}',
        command,
    ]
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace',
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return '', f'SSH命令超时（{timeout}秒）', -1
    except FileNotFoundError:
        return '', 'ssh命令不可用，请确认系统已安装OpenSSH客户端', -2
    except Exception as e:
        return '', f'SSH执行异常: {e}', -3


def parse_time_bucket(log_line):
    """从日志行中提取时间，返回小时桶（如 '14:00'）"""
    # 匹配常见日志时间格式：2026-05-25 14:23:45
    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}):(\d{2})', log_line)
    if m:
        return f'{m.group(1)} {m.group(2)}:00'
    # 匹配 journalctl 时间格式：May 25 14:23:45
    m = re.search(r'(\w{3}\s+\d{1,2})\s+(\d{2}):\d{2}:\d{2}', log_line)
    if m:
        return f'{m.group(1)} {m.group(2)}:00'
    return None


def resolve_server(target):
    """解析服务器目标参数，返回IP列表"""
    if not target:
        return list(SERVERS.keys())

    target_lower = target.lower().strip()
    # 按名称别名匹配
    if target_lower in ('jp', 'japan', '日本'):
        return ['52.195.179.240']
    if target_lower in ('sg', 'singapore', '新加坡'):
        return ['13.212.37.11']
    if target_lower in ('all', '全部'):
        return list(SERVERS.keys())

    # 直接IP匹配
    if target_lower in SERVERS:
        return [target_lower]

    # 按域名匹配
    for ip, info in SERVERS.items():
        if info.get('domain', '').lower() == target_lower:
            return [ip]

    # 当作IP直接使用（不在预定义列表中也允许）
    if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', target):
        return [target]

    print(safe_text(f'⚠️ 无法识别服务器目标: {target}'))
    return []


# ============================================================
# 诊断模块
# ============================================================

def check_ssh_connectivity(host, user='root'):
    """检查SSH连通性"""
    out, err, rc = ssh_run(host, 'echo OK', user=user, timeout=10)
    if rc == 0 and 'OK' in out:
        return True, 'SSH连接正常'
    elif rc == -2:
        return False, 'ssh命令不可用'
    elif rc == -1:
        return False, 'SSH连接超时'
    else:
        return False, f'SSH连接失败: {err[:100]}'


def analyze_disconnect_events(host, user='root', hours=6):
    """分析断线事件：按协议统计连接关闭/重置"""
    result = {
        'by_protocol': {},
        'total_disconnects': 0,
        'time_distribution': defaultdict(int),
        'sample_lines': [],
        'invalid_reality_count': 0,
        'unexpected_eof_count': 0,
        'eof_count': 0,
        'reset_timeout_count': 0,
        'related_ip': '',
        'related_ip_samples': [],
    }

    # 构建grep模式：匹配断线关键词
    pattern = '|'.join(DISCONNECT_PATTERNS)
    # 限制日志时间范围
    since_str = ''
    if hours > 0:
        since_str = f'--since "{hours} hours ago"'

    # 从 /var/log/singbox.log 提取
    cmd = (
        f'grep -iE "({pattern})" {REMOTE_LOG_FILE} {since_str} 2>/dev/null | tail -2000'
    )
    out, err, rc = ssh_run(host, cmd, user=user, timeout=30)

    if not out:
        # 降级：尝试从 journalctl 获取
        cmd2 = (
            f'journalctl -u singbox {since_str} --no-pager 2>/dev/null '
            f'| grep -iE "({pattern})" | tail -2000'
        )
        out, err, rc = ssh_run(host, cmd2, user=user, timeout=30)

    if not out:
        result['note'] = '未找到断线日志（日志文件可能为空或不存在）'
        return result

    lines = out.split('\n')
    result['total_disconnects'] = len(lines)

    for line in lines:
        line_lower = line.lower()
        if 'processed invalid connection' in line_lower:
            result['invalid_reality_count'] += 1
        if 'unexpected eof' in line_lower:
            result['unexpected_eof_count'] += 1
        if re.search(r'(^|[^a-z])eof([^a-z]|$)', line_lower):
            result['eof_count'] += 1
        if any(token in line_lower for token in ('reset', 'timeout', 'broken pipe', 'i/o timeout')):
            result['reset_timeout_count'] += 1

    # 按协议分类统计
    for proto_key, proto_info in PROTOCOLS.items():
        port = proto_info['port']
        transport = proto_info['transport']
        count = 0
        for line in lines:
            line_lower = line.lower()
            # 匹配端口或协议名
            if (f':{port}' in line or f'port {port}' in line
                    or proto_key.replace('-', ' ') in line_lower
                    or proto_key.replace('-', '_') in line_lower):
                count += 1
        if count > 0:
            result['by_protocol'][proto_key] = {
                'count': count,
                'label': proto_info['label'],
                'port': port,
            }

    # 时间分布（按小时桶）
    for line in lines:
        bucket = parse_time_bucket(line)
        if bucket:
            result['time_distribution'][bucket] += 1

    # 保留样本行（最多10条）
    result['sample_lines'] = lines[:10]

    return result


def attach_related_ip_samples(result, related_ip):
    """将与用户公网IP相关的断线样本附加到统计结果。"""
    result['related_ip'] = related_ip or ''
    if not related_ip:
        return result

    matched = [line for line in result.get('sample_lines', []) if related_ip in line]
    result['related_ip_samples'] = matched[:5]
    return result


def analyze_time_patterns(time_distribution):
    """分析时间模式：判断是集中断线还是随机断线"""
    if not time_distribution:
        return '无数据', {}

    counts = list(time_distribution.values())
    if not counts:
        return '无数据', {}

    avg = sum(counts) / len(counts)
    max_count = max(counts)
    min_count = min(counts)

    # 计算变异系数（标准差/均值），越大越集中
    if avg > 0:
        variance = sum((c - avg) ** 2 for c in counts) / len(counts)
        std_dev = variance ** 0.5
        cv = std_dev / avg
    else:
        cv = 0

    # 判断模式
    if cv > 1.5:
        pattern_type = '集中爆发'
    elif cv > 0.8:
        pattern_type = '部分集中'
    else:
        pattern_type = '随机分散'

    # 找出峰值时段
    peak_buckets = sorted(time_distribution.items(), key=lambda x: x[1], reverse=True)[:3]

    stats = {
        'avg_per_hour': round(avg, 1),
        'max_per_hour': max_count,
        'min_per_hour': min_count,
        'cv': round(cv, 2),
        'peak_periods': peak_buckets,
    }

    return pattern_type, stats


def detect_cf_blocking(host, user='root', hours=6):
    """检测Cloudflare 403/1020阻断事件"""
    result = {
        'cf_403_count': 0,
        'cf_1020_count': 0,
        'cf_block_total': 0,
        'sample_lines': [],
    }

    since_str = f'--since "{hours} hours ago"' if hours > 0 else ''

    # 从singbox日志搜索
    cf_pattern = '|'.join(CF_BLOCK_PATTERNS)
    cmd = (
        f'grep -iE "({cf_pattern})" {REMOTE_LOG_FILE} {since_str} 2>/dev/null | tail -500'
    )
    out, err, rc = ssh_run(host, cmd, user=user, timeout=30)

    if not out:
        # 降级：从subscription_service日志搜索
        cmd2 = (
            f'journalctl -u singbox-sub {since_str} --no-pager 2>/dev/null '
            f'| grep -iE "403|1020|阻断|blocked" | tail -200'
        )
        out, err, rc = ssh_run(host, cmd2, user=user, timeout=30)

    if not out:
        return result

    lines = out.split('\n')
    for line in lines:
        line_lower = line.lower()
        if '403' in line:
            result['cf_403_count'] += 1
        if '1020' in line:
            result['cf_1020_count'] += 1

    result['cf_block_total'] = len(lines)
    result['sample_lines'] = lines[:8]

    return result


def check_oom_events(host, user='root'):
    """检查OOM killer事件"""
    result = {
        'oom_found': False,
        'oom_details': [],
    }

    # 检查dmesg中的OOM事件
    cmd = 'dmesg 2>/dev/null | grep -iE "oom|out of memory|killed process" | tail -20'
    out, err, rc = ssh_run(host, cmd, user=user, timeout=15)

    if out:
        lines = [l for l in out.split('\n') if l.strip()]
        if lines:
            result['oom_found'] = True
            result['oom_details'] = lines[:10]

    # 补充：检查journalctl中的OOM
    cmd2 = 'journalctl -k --since "24 hours ago" --no-pager 2>/dev/null | grep -iE "oom|out of memory|killed" | tail -10'
    out2, err2, rc2 = ssh_run(host, cmd2, user=user, timeout=15)

    if out2:
        lines2 = [l for l in out2.split('\n') if l.strip()]
        if lines2:
            result['oom_found'] = True
            result['oom_details'].extend(lines2[:5])

    return result


def check_sysctl_params(host, user='root'):
    """检查关键sysctl网络参数"""
    result = {}

    params = [
        ('tcp_keepalive_time', 'net.ipv4.tcp_keepalive_time'),
        ('tcp_keepalive_intvl', 'net.ipv4.tcp_keepalive_intvl'),
        ('tcp_keepalive_probes', 'net.ipv4.tcp_keepalive_probes'),
        ('conntrack_max', 'net.netfilter.nf_conntrack_max'),
        ('conntrack_count', 'net.netfilter.nf_conntrack_count'),
        ('tcp_tw_reuse', 'net.ipv4.tcp_tw_reuse'),
        ('tcp_max_syn_backlog', 'net.ipv4.tcp_max_syn_backlog'),
        ('somaxconn', 'net.core.somaxconn'),
    ]

    for label, param in params:
        cmd = f'sysctl -n {param} 2>/dev/null'
        out, err, rc = ssh_run(host, cmd, user=user, timeout=10)
        result[label] = out.strip() if rc == 0 else 'N/A'

    # 计算连接跟踪使用率
    try:
        max_val = int(result.get('conntrack_max', '0'))
        cur_val = int(result.get('conntrack_count', '0'))
        if max_val > 0:
            result['conntrack_usage_pct'] = f'{cur_val * 100 / max_val:.1f}%'
        else:
            result['conntrack_usage_pct'] = 'N/A'
    except (ValueError, ZeroDivisionError):
        result['conntrack_usage_pct'] = 'N/A'

    return result


def check_singbox_restarts(host, user='root', hours=24):
    """检查sing-box服务重启次数"""
    result = {
        'restart_count': 0,
        'restart_times': [],
        'current_status': 'unknown',
        'uptime': 'unknown',
    }

    # 当前状态
    cmd = 'systemctl is-active singbox 2>/dev/null'
    out, err, rc = ssh_run(host, cmd, user=user, timeout=10)
    result['current_status'] = out.strip() if out else 'unknown'

    # 运行时长
    cmd2 = 'systemctl show singbox --property=ActiveEnterTimestamp 2>/dev/null'
    out2, err2, rc2 = ssh_run(host, cmd2, user=user, timeout=10)
    if out2 and '=' in out2:
        result['uptime'] = out2.split('=', 1)[1].strip()

    # 重启次数（从journalctl统计）
    since_str = f'--since "{hours} hours ago"' if hours > 0 else ''
    cmd3 = (
        f'journalctl -u singbox {since_str} --no-pager 2>/dev/null '
        f'| grep -cE "Started singbox|Starting singbox|start.*sing-box"'
    )
    out3, err3, rc3 = ssh_run(host, cmd3, user=user, timeout=15)
    try:
        result['restart_count'] = int(out3.strip()) if out3.strip() else 0
    except ValueError:
        result['restart_count'] = 0

    # 重启时间点
    cmd4 = (
        f'journalctl -u singbox {since_str} --no-pager 2>/dev/null '
        f'| grep -E "Started singbox|Starting singbox" | tail -10'
    )
    out4, err4, rc4 = ssh_run(host, cmd4, user=user, timeout=15)
    if out4:
        result['restart_times'] = [l.strip() for l in out4.split('\n') if l.strip()][:5]

    return result


# ============================================================
# 报告输出
# ============================================================

def print_section(title):
    """打印分节标题"""
    print(f'\n{"=" * 60}')
    print(f'  {title}')
    print(f'{"=" * 60}')


def print_kv(key, value, indent=2):
    """打印键值对"""
    print(f'{" " * indent}{key}: {value}')


def generate_report(host, server_info, user, hours):
    """对单台服务器生成完整诊断报告"""
    label = server_info.get('label', host) if server_info else host
    domain = server_info.get('domain', 'N/A') if server_info else 'N/A'
    env = load_env()
    related_ip = resolve_related_ip(env)

    print(f'\n{"#" * 60}')
    print(f'# {label} 服务器诊断报告')
    print(f'# IP: {host}  域名: {domain}')
    print(f'# 分析时间范围: 最近 {hours} 小时')
    print(f'# 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"#" * 60}')

    # 1. SSH连通性
    print_section('1. SSH 连通性检查')
    ok, msg = check_ssh_connectivity(host, user=user)
    if not ok:
        print(safe_text(f'  ❌ {msg}'))
        print(safe_text(f'  ⚠️ 后续检查全部跳过，请先解决SSH连接问题'))
        return
    print(safe_text(f'  ✅ {msg}'))

    # 2. 断线事件分析
    print_section('2. 断线事件分析（按协议）')
    disconnect = analyze_disconnect_events(host, user=user, hours=hours)
    attach_related_ip_samples(disconnect, related_ip)

    if disconnect.get('note'):
        print(safe_text(f'  ℹ️ {disconnect["note"]}'))
    else:
        print_kv('断线事件总数', disconnect['total_disconnects'])
        print_kv('REALITY invalid connection', disconnect['invalid_reality_count'])
        print_kv('unexpected EOF', disconnect['unexpected_eof_count'])
        print_kv('EOF 总数', disconnect['eof_count'])
        print_kv('reset/timeout 总数', disconnect['reset_timeout_count'])

        if disconnect['by_protocol']:
            print(f'\n  按协议分布:')
            # 按数量降序排列
            sorted_protos = sorted(
                disconnect['by_protocol'].items(),
                key=lambda x: x[1]['count'],
                reverse=True,
            )
            for proto_key, info in sorted_protos:
                pct = info['count'] * 100 / max(disconnect['total_disconnects'], 1)
                bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
                print(f'    {info["label"]:20s} (:{info["port"]}): {info["count"]:5d} 次  {bar} {pct:.1f}%')
        else:
            print(safe_text(f'  ℹ️ 无法按协议分类（日志中未匹配到端口/协议标识）'))

        # 3. 时间模式分析
        print_section('3. 断线时间模式分析')
        pattern_type, stats = analyze_time_patterns(disconnect['time_distribution'])

        print_kv('模式判断', pattern_type)
        if stats:
            print_kv('平均每小时断线', stats.get('avg_per_hour', 'N/A'))
            print_kv('峰值每小时断线', stats.get('max_per_hour', 'N/A'))
            print_kv('变异系数(CV)', stats.get('cv', 'N/A'))

            if stats.get('peak_periods'):
                print(f'\n  断线峰值时段:')
                for bucket, count in stats['peak_periods']:
                    print(f'    {bucket}  →  {count} 次')

            # 模式解读
            if pattern_type == '集中爆发':
                print(safe_text(f'\n  ⚠️ 检测到集中断线模式！可能原因：'))
                print(f'     - 服务器网络抖动/路由变更')
                print(f'     - 运营商间歇性封锁')
                print(f'     - 服务器资源耗尽（OOM/CPU）')
            elif pattern_type == '部分集中':
                print(safe_text(f'\n  💡 断线存在部分集中趋势，建议关注峰值时段的网络状况'))
            else:
                print(safe_text(f'\n  ✅ 断线呈随机分散模式，通常为正常客户端行为'))

        # 样本行
        if disconnect.get('sample_lines'):
            print(f'\n  断线日志样本（最近{len(disconnect["sample_lines"])}条）:')
            for line in disconnect['sample_lines'][:5]:
                # 截断过长行
                display = line[:120] + '...' if len(line) > 120 else line
                print(f'    {display}')
        if disconnect.get('related_ip'):
            print_kv('related_ip', disconnect['related_ip'])
            if disconnect.get('related_ip_samples'):
                print(f'\n  与用户公网IP相关的样本:')
                for line in disconnect['related_ip_samples'][:5]:
                    display = line[:120] + '...' if len(line) > 120 else line
                    print(f'    {display}')

    # 4. Cloudflare阻断检测
    print_section('4. Cloudflare 阻断检测')
    cf_result = detect_cf_blocking(host, user=user, hours=hours)

    if cf_result['cf_block_total'] == 0:
        print(safe_text(f'  ✅ 未检测到 Cloudflare 403/1020 阻断事件'))
    else:
        print_kv('CF 403 事件数', cf_result['cf_403_count'])
        print_kv('CF 1020 事件数', cf_result['cf_1020_count'])
        print_kv('阻断事件总计', cf_result['cf_block_total'])

        if cf_result['cf_1020_count'] > 0:
            print(safe_text(f'\n  ⚠️ 检测到 1020 错误码！这是 Cloudflare WAF 拦截，说明：'))
            print(f'     - CDN IP 可能被 Cloudflare 标记为可疑')
            print(f'     - 建议运行 cdn_monitor.py 更换优选IP')

        if cf_result.get('sample_lines'):
            print(f'\n  阻断日志样本:')
            for line in cf_result['sample_lines'][:5]:
                display = line[:120] + '...' if len(line) > 120 else line
                print(f'    {display}')

    # 5. OOM检查
    print_section('5. OOM Killer 检查')
    oom_result = check_oom_events(host, user=user)

    if oom_result['oom_found']:
        print(safe_text(f'  ❌ 检测到 OOM 事件！'))
        for detail in oom_result['oom_details'][:5]:
            display = detail[:120] + '...' if len(detail) > 120 else detail
            print(f'    {display}')
        print(f'\n  修复建议:')
        print(f'     - 增加 Swap: fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile')
        print(f'     - 减少连接数限制或优化 sing-box 配置')
    else:
        print(safe_text(f'  ✅ 未检测到 OOM 事件'))

    # 6. sysctl参数
    print_section('6. 内核网络参数检查')
    sysctl_result = check_sysctl_params(host, user=user)

    # 关键参数与建议值
    param_recommend = {
        'tcp_keepalive_time': ('30', '建议保持 30 秒，避免 NAT 超时后连接长期半死不活'),
        'tcp_keepalive_intvl': ('10', '建议保持 10 秒，加快发现坏连接'),
        'tcp_keepalive_probes': ('3', '建议保持 3 次，在移动网络/高丢包场景更快完成判死'),
        'conntrack_max': ('', '建议 ≥ 65536，小内存VPS至少32768'),
        'conntrack_usage_pct': ('', '使用率 > 80% 时需增大 conntrack_max'),
        'tcp_tw_reuse': ('0', '建议设为 2（允许复用TIME_WAIT连接）'),
        'tcp_max_syn_backlog': ('128', '建议 ≥ 1024，高并发时防SYN丢包'),
        'somaxconn': ('128', '建议 ≥ 1024，增大监听队列'),
    }

    warnings = []
    for label, value in sysctl_result.items():
        recommend_info = param_recommend.get(label, ('', ''))
        default_val, advice = recommend_info
        status = ''

        # 检查是否需要优化
        if label == 'tcp_keepalive_time' and value != 'N/A':
            try:
                v = int(value)
                if v != 30:
                    status = '⚠️ 偏离基线'
                    warnings.append(f'tcp_keepalive_time={v}，{advice}')
                else:
                    status = '✅'
            except ValueError:
                status = ''
        elif label == 'tcp_keepalive_intvl' and value != 'N/A':
            try:
                v = int(value)
                if v != 10:
                    status = '⚠️ 偏离基线'
                    warnings.append(f'tcp_keepalive_intvl={v}，{advice}')
                else:
                    status = '✅'
            except ValueError:
                status = ''
        elif label == 'tcp_keepalive_probes' and value != 'N/A':
            try:
                v = int(value)
                if v != 3:
                    status = '⚠️ 偏离基线'
                    warnings.append(f'tcp_keepalive_probes={v}，{advice}')
                else:
                    status = '✅'
            except ValueError:
                status = ''
        elif label == 'conntrack_usage_pct' and value != 'N/A':
            try:
                v = float(value.replace('%', ''))
                if v > 80:
                    status = '⚠️ 偏高'
                    warnings.append(f'conntrack使用率{value}，{advice}')
                else:
                    status = '✅'
            except ValueError:
                status = ''
        elif label == 'tcp_tw_reuse' and value != 'N/A':
            try:
                v = int(value)
                if v != 2:
                    status = '⚠️ 建议设为2'
                    warnings.append(f'tcp_tw_reuse={v}，{advice}')
                else:
                    status = '✅'
            except ValueError:
                status = ''

        print(f'  {label:25s} = {value:15s} {status}')

    if warnings:
        print(f'\n  优化建议:')
        for w in warnings:
            print(safe_text(f'    ⚠️ {w}'))

    # 7. sing-box服务重启
    print_section('7. sing-box 服务重启检查')
    restart_result = check_singbox_restarts(host, user=user, hours=hours)

    status_icon = '✅' if restart_result['current_status'] == 'active' else '❌'
    print_kv('当前状态', f'{restart_result["current_status"]} {status_icon}')
    print_kv('上次启动时间', restart_result['uptime'])
    print_kv(f'最近{hours}小时重启次数', restart_result['restart_count'])

    if restart_result['restart_count'] > 3:
        print(safe_text(f'\n  ⚠️ 重启次数偏多！可能原因：'))
        print(f'     - OOM killer 杀进程（检查上方OOM报告）')
        print(f'     - sing-box 配置错误导致反复崩溃')
        print(f'     - health_check.sh 检测到异常后自动重启')
        print(f'  查看详情: ssh {user}@{host} "journalctl -u singbox --since \\"{hours} hours ago\\" | tail -50"')

    if restart_result.get('restart_times'):
        print(f'\n  重启时间点:')
        for t in restart_result['restart_times'][:5]:
            display = t[:120] + '...' if len(t) > 120 else t
            print(f'    {display}')


# ============================================================
# 主入口
# ============================================================

def main():
    configure_stdout()
    parser = argparse.ArgumentParser(
        description='sing-box 断线诊断脚本 - 分析服务器断线模式',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python diagnose_disconnect.py                     # 诊断所有服务器
  python diagnose_disconnect.py 52.195.179.240      # 诊断指定IP
  python diagnose_disconnect.py jp                  # 诊断日本服务器
  python diagnose_disconnect.py sg --hours 12       # 诊断新加坡，最近12小时
  python diagnose_disconnect.py --user admin        # 指定SSH用户名
        """,
    )
    parser.add_argument(
        'server', nargs='?', default='',
        help='服务器目标：IP地址 / jp / sg / all（默认all）',
    )
    parser.add_argument(
        '--hours', type=int, default=6,
        help='分析最近N小时的日志（默认6）',
    )
    parser.add_argument(
        '--user', type=str, default='root',
        help='SSH用户名（默认root）',
    )

    args = parser.parse_args()

    # 尝试从.env加载SSH用户（仅当命令行未指定非root用户时）
    env = load_env()
    ssh_user = args.user
    if ssh_user == 'root' and env.get('SSH_USER'):
        ssh_user = env['SSH_USER']

    # 解析服务器目标
    targets = resolve_server(args.server)
    if not targets:
        print(safe_text('❌ 未找到可诊断的服务器，请检查参数'))
        print(f'   可用目标: jp, sg, all, 或直接输入IP地址')
        sys.exit(1)

    print(safe_text(f'🔍 sing-box 断线诊断工具'))
    print(f'   目标服务器: {", ".join(targets)}')
    print(f'   分析范围: 最近 {args.hours} 小时')
    print(f'   SSH用户: {ssh_user}')

    # 逐台服务器诊断
    for host in targets:
        server_info = SERVERS.get(host)
        try:
            generate_report(host, server_info, ssh_user, args.hours)
        except KeyboardInterrupt:
            print(safe_text(f'\n\n⚠️ 用户中断，跳过 {host}'))
            continue
        except Exception as e:
            print(safe_text(f'\n❌ 诊断 {host} 时发生异常: {e}'))

    # 总结
    print(f'\n{"#" * 60}')
    print(f'# 诊断完成')
    print(f'# 时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"#" * 60}')


if __name__ == '__main__':
    main()
