#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.6 直连节点质量筛选引擎
专门处理非CDN的直连节点（REALITY/XTLS/TCP等协议）

功能：
1. 硬淘汰：延时/丢包/稳定性不达标的直连节点直接淘汰
2. TCP/TLS握手延时检测
3. 用户路径质量探测
4. 五维加权评分（延迟35% + 稳定性25% + 用户路径20% + 新鲜度10% + 丢包10%）

与CDN筛选的区别：
- 直连不含谷歌测速、区域适配（无CDN中转）
- 直连更关注基础延时和稳定性
- 评分权重不同

[TRAE SOLO CN] v4.6 新增模块
"""

import json
import logging
import os
import socket
import ssl
import sqlite3
import time
import urllib.request
from datetime import datetime

logger = logging.getLogger('direct_quality_filter')


class DirectNodeQualityFilter:
    """
    直连节点质量筛选引擎

    使用方式：
        filter = DirectNodeQualityFilter(db_path='/path/to/singbox.db')
        # 硬淘汰检查
        rejected, reason = filter.hard_reject('1.2.3.4', port=443)
        # 评分
        score = filter.calculate_score('1.2.3.4', port=443)
        # 批量筛选
        ranked = filter.filter_and_rank([{'ip': '1.2.3.4', 'port': 443}, ...])
    """

    # 默认硬淘汰阈值（直连比CDN更激进，延迟要求更高）
    DEFAULT_HARD_REJECT = {
        'latency_ms': 150,           # 直连延时超过150ms淘汰
        'tls_handshake_ms': 200,     # TLS握手超过200ms淘汰
        'packet_loss_rate': 0.15,    # 丢包率超过15%淘汰
        'min_stability_score': 20,   # 稳定性评分低于20淘汰
        'consecutive_fails': 5,      # 连续失败5次淘汰
    }

    # 五维评分权重
    SCORE_WEIGHTS = {
        'latency': 0.35,      # TCP延时
        'stability': 0.25,    # 稳定性（连续成功/失败）
        'user_path': 0.20,    # 用户路径延时
        'freshness': 0.10,    # 新鲜度
        'packet_loss': 0.10,  # 丢包率
    }

    def __init__(self, db_path=None, ddns_domain='', hard_reject=None,
                 user_path_threshold_ms=100):
        """
        Args:
            db_path: SQLite数据库路径
            ddns_domain: 用户DDNS域名
            hard_reject: 硬淘汰阈值字典
            user_path_threshold_ms: 用户路径延时阈值
        """
        self.db_path = db_path
        self.ddns_domain = ddns_domain
        self.user_path_threshold_ms = user_path_threshold_ms
        self._hard_reject_config = {**self.DEFAULT_HARD_REJECT, **(hard_reject or {})}

    # ==================== 硬淘汰 ====================

    def hard_reject(self, ip, port=443, tls_hostname=''):
        """
        直连节点硬淘汰检查

        Args:
            ip: 节点IP
            port: 端口
            tls_hostname: TLS SNI（如 'www.apple.com'）

        Returns:
            (是否淘汰, 淘汰原因)
        """
        perf = self._get_node_performance(ip)

        # TCP延时检查
        tcp_lat = self._tcp_ping(ip, port)
        if tcp_lat is None:
            return True, f"TCP连接失败 {ip}:{port}"
        if tcp_lat > self._hard_reject_config['latency_ms']:
            return True, f"延时{tcp_lat:.0f}ms>{self._hard_reject_config['latency_ms']}ms"

        # TLS握手检查（如果指定了hostname）
        if tls_hostname:
            tls_lat = self._tls_handshake(ip, port, tls_hostname)
            if tls_lat is not None and tls_lat > self._hard_reject_config['tls_handshake_ms']:
                return True, f"TLS握手{tls_lat:.0f}ms>{self._hard_reject_config['tls_handshake_ms']}ms"

        # 历史数据检查
        if perf and perf.get('total_tests', 0) >= 5:
            fail_rate = perf.get('fail_count', 0) / perf['total_tests']
            if fail_rate > self._hard_reject_config['packet_loss_rate']:
                return True, f"失败率{fail_rate*100:.0f}%>{self._hard_reject_config['packet_loss_rate']*100:.0f}%"

            consec = perf.get('consecutive_fails', 0)
            if consec >= self._hard_reject_config['consecutive_fails']:
                return True, f"连续失败{consec}次>={self._hard_reject_config['consecutive_fails']}次"

        return False, ""

    # ==================== 评分 ====================

    def calculate_score(self, ip, port=443, tls_hostname='', user_probe_result=None):
        """
        五维综合评分

        Returns:
            float 0-100
        """
        perf = self._get_node_performance(ip)
        if not perf or perf.get('total_tests', 0) == 0:
            return 50.0

        total = perf['total_tests']
        success = perf.get('success_count', 0)
        avg_lat = perf.get('avg_latency', 0)
        consec_fails = perf.get('consecutive_fails', 0)
        last_success = perf.get('last_success_time')

        # 1. 延迟分（0-100）
        if avg_lat <= 50:
            latency_score = 100
        elif avg_lat <= 100:
            latency_score = 80
        elif avg_lat <= 150:
            latency_score = 60
        elif avg_lat <= 200:
            latency_score = 40
        else:
            latency_score = max(0, 100 * (1 - avg_lat / 500))

        # 2. 稳定性分（0-100）
        stability_score = max(0, 100 - consec_fails * 25)

        # 3. 用户路径质量分
        user_path_score = 50
        if user_probe_result:
            user_lat = user_probe_result.get('latency_ms', 9999)
            if user_lat < 50:
                user_path_score = 100
            elif user_lat < 100:
                user_path_score = 80
            elif user_lat < 200:
                user_path_score = 50
            else:
                user_path_score = 20
        else:
            # 无用户探测数据，用TCP延时估算
            user_path_score = latency_score

        # 4. 新鲜度分
        freshness_score = 0
        if last_success:
            try:
                last_dt = datetime.fromisoformat(last_success)
                days_since = (datetime.now() - last_dt).days
                freshness_score = max(0, 100 - days_since * 33)
            except Exception:
                pass

        # 5. 丢包分
        if success == total:
            packet_loss_score = 100
        elif total >= 3:
            fail_rate = (total - success) / total
            packet_loss_score = max(0, 100 - fail_rate * 1000)
        else:
            packet_loss_score = 50

        # 加权总分
        w = self.SCORE_WEIGHTS
        total_score = (
            latency_score * w['latency'] +
            stability_score * w['stability'] +
            user_path_score * w['user_path'] +
            freshness_score * w['freshness'] +
            packet_loss_score * w['packet_loss']
        )
        return round(total_score, 2)

    def filter_and_rank(self, nodes, user_probe_result=None):
        """
        批量筛选直连节点

        核心逻辑：硬淘汰兜底机制
        - 节点数 >= 3：严格执行硬淘汰
        - 节点数 <= 2：硬淘汰改为软淘汰（降权30%但不剔除），确保有节点可用

        Args:
            nodes: [{'ip': '1.2.3.4', 'port': 443, 'tls_hostname': 'www.apple.com'}, ...]
            user_probe_result: 用户网络探测结果

        Returns:
            list of (node, score, degraded) 按评分降序
            degraded: True表示该节点处于软淘汰状态（降权）
        """
        qualified = []
        rejected_count = 0
        use_soft_reject = len(nodes) <= 2  # 节点少时软淘汰兜底

        for node in nodes:
            ip = node.get('ip', '')
            port = node.get('port', 443)
            tls_hostname = node.get('tls_hostname', '')

            rejected, reason = self.hard_reject(ip, port, tls_hostname)
            if rejected:
                if use_soft_reject:
                    # 节点少时：降权30%但不剔除，标记degraded=True
                    score = self.calculate_score(ip, port, tls_hostname, user_probe_result)
                    score = score * 0.7  # 降权30%但保留
                    qualified.append((node, round(score, 2), True))
                    logger.warning(f"  {ip} 软淘汰(降权30%): {reason}，节点过少保留使用")
                else:
                    logger.debug(f"  {ip} 硬淘汰: {reason}")
                    rejected_count += 1
                continue

            score = self.calculate_score(ip, port, tls_hostname, user_probe_result)
            qualified.append((node, score, False))

        qualified.sort(key=lambda x: -x[1])

        degraded_count = sum(1 for _, _, d in qualified if d)
        logger.info(f"直连筛选: {len(nodes)}个节点 → 淘汰{rejected_count}个 → 合格{len(qualified)-degraded_count}个 + 软淘汰{degraded_count}个")
        return qualified

    def select_best(self, nodes, user_probe_result=None):
        """
        从节点列表中选出最优的一个

        Returns:
            dict (含额外字段 degraded=True 表示软淘汰节点) 或 None
        """
        ranked = self.filter_and_rank(nodes, user_probe_result)
        if ranked:
            node = ranked[0][0].copy()
            node['degraded'] = ranked[0][2]
            node['score'] = ranked[0][1]
            return node
        return None

    # ==================== 探测方法 ====================

    def optimize_reality_config(self, user_probe_result=None):
        """
        基于用户网络特征优化REALITY直连节点配置

        优化维度：
        1. SNI/dest选择 — 选对用户网络TLS握手最快的域名
        2. flow确认 — xtls-rprx-vision已是最优
        3. 端口确认 — 443标准端口
        4. TCP参数建议 — sing-box层可调优的参数

        Returns:
            {
                'sni_recommendation': str,     # 推荐的SNI
                'dest_recommendation': str,    # 推荐的dest
                'sni_comparison': [...],       # 各SNI的TLS握手对比
                'tcp_tuning': {...},           # TCP参数调优建议
                'current_config_ok': bool,     # 当前配置是否已最优
            }
        """
        # 候选SNI列表（都是大厂域名，对电信友好）
        sni_candidates = [
            ('www.apple.com', '苹果（默认）'),
            ('www.microsoft.com', '微软'),
            ('gateway.icloud.com', 'iCloud'),
            ('www.tesla.com', '特斯拉'),
            ('www.amazon.com', '亚马逊'),
            ('dl.google.com', '谷歌下载'),
        ]

        # 测试各SNI的TLS握手速度
        sni_results = []
        for sni, label in sni_candidates:
            tls_lat = self._tls_handshake_test(sni)
            sni_results.append({
                'sni': sni,
                'label': label,
                'tls_handshake_ms': tls_lat,
            })

        # 按TLS握手速度排序
        sni_results.sort(key=lambda x: x['tls_handshake_ms'] if x['tls_handshake_ms'] else 9999)

        # 推荐最快的SNI
        best = sni_results[0] if sni_results else None
        current_apple = next((r for r in sni_results if r['sni'] == 'www.apple.com'), None)

        # 判断当前配置是否已最优
        current_ok = True
        if current_apple and best and best['sni'] != 'www.apple.com':
            # 如果最优SNI比apple快30%以上，建议换
            if (current_apple['tls_handshake_ms'] and best['tls_handshake_ms'] and
                    current_apple['tls_handshake_ms'] > best['tls_handshake_ms'] * 1.3):
                current_ok = False

        # TCP调优建议（基于用户网络特征）
        tcp_tuning = {
            'tcp_fast_open': True,           # 开启TFO
            'tcp_multi_path': False,         # MPTCP暂不建议
            'tcp_congestion': 'bbr',         # BBR拥塞控制
            'tcp_window_size': 'auto',       # 自动窗口
            'singbox_sniff': True,           # 开启流量嗅探
            'singbox_tcp_fast_open': True,    # sing-box TFO
        }

        # 用户路径质量参考
        if user_probe_result:
            user_lat = user_probe_result.get('latency_ms', 0)
            if user_lat > 100:
                tcp_tuning['tcp_congestion'] = 'bbr'  # 高延迟用BBR
                tcp_tuning['note'] = f'用户路径延迟{user_lat}ms，建议BBR+TFO'
            elif user_lat > 50:
                tcp_tuning['note'] = f'用户路径延迟{user_lat}ms，当前配置合理'
            else:
                tcp_tuning['note'] = f'用户路径延迟{user_lat}ms，网络质量优秀'

        return {
            'sni_recommendation': best['sni'] if best else 'www.apple.com',
            'dest_recommendation': f"{best['sni']}:443" if best else 'www.apple.com:443',
            'sni_comparison': sni_results,
            'tcp_tuning': tcp_tuning,
            'current_config_ok': current_ok,
        }

    # ==================== 内部探测方法 ====================

    def _tls_handshake_test(self, hostname, port=443, timeout=8):
        """测试到指定域名的TLS握手耗时（通过公网DNS解析）"""
        sock = None
        ssock = None
        try:
            # 先DNS解析
            addr = socket.gethostbyname(hostname)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((addr, port))

            ctx = ssl.create_default_context()
            start = time.time()
            ssock = ctx.wrap_socket(sock, server_hostname=hostname)
            elapsed = (time.time() - start) * 1000
            return round(elapsed, 1)
        except Exception:
            return None
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

    def probe_node(self, ip, port=443, tls_hostname='', rounds=3):
        """
        对单个直连节点进行多轮探测

        Returns:
            {'tcp_avg_ms': float, 'tls_avg_ms': float|None,
             'success_rate': float, 'packet_loss': float}
        """
        tcp_lats = []
        tls_lats = []
        successes = 0

        for _ in range(rounds):
            tcp = self._tcp_ping(ip, port)
            if tcp is not None:
                tcp_lats.append(tcp)
                successes += 1

            if tls_hostname:
                tls = self._tls_handshake(ip, port, tls_hostname)
                if tls is not None:
                    tls_lats.append(tls)

            time.sleep(0.3)

        return {
            'tcp_avg_ms': round(sum(tcp_lats) / len(tcp_lats), 1) if tcp_lats else None,
            'tls_avg_ms': round(sum(tls_lats) / len(tls_lats), 1) if tls_lats else None,
            'success_rate': successes / rounds,
            'packet_loss': 1 - (successes / rounds),
        }

    # ==================== 内部方法 ====================

    def _tcp_ping(self, ip, port, timeout=5):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            start = time.time()
            sock.connect((ip, port))
            elapsed = (time.time() - start) * 1000
            sock.close()
            return elapsed
        except Exception:
            return None

    def _tls_handshake(self, ip, port, hostname, timeout=8):
        """TLS握手耗时"""
        sock = None
        ssock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((ip, port))

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            start = time.time()
            ssock = ctx.wrap_socket(sock, server_hostname=hostname)
            elapsed = (time.time() - start) * 1000
            return elapsed
        except Exception:
            return None
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

    def _get_node_performance(self, ip):
        """从数据库获取直连节点性能数据"""
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # 确保表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS direct_node_performance (
                    ip TEXT PRIMARY KEY,
                    port INTEGER DEFAULT 443,
                    total_tests INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    consecutive_fails INTEGER DEFAULT 0,
                    avg_latency REAL DEFAULT 0,
                    min_latency REAL DEFAULT 9999,
                    max_latency REAL DEFAULT 0,
                    last_test_time TEXT,
                    last_success_time TEXT,
                    first_seen TEXT,
                    tls_avg_latency REAL DEFAULT 0,
                    protocol TEXT DEFAULT 'reality'
                )
            """)
            cursor.execute("SELECT * FROM direct_node_performance WHERE ip = ?", (ip,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            if conn:
                conn.commit()
                conn.close()

    def save_node_performance(self, ip, port=443, result=None):
        """保存直连节点探测结果到数据库"""
        if not self.db_path or not result:
            return
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS direct_node_performance (
                    ip TEXT PRIMARY KEY,
                    port INTEGER DEFAULT 443,
                    total_tests INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    consecutive_fails INTEGER DEFAULT 0,
                    avg_latency REAL DEFAULT 0,
                    min_latency REAL DEFAULT 9999,
                    max_latency REAL DEFAULT 0,
                    last_test_time TEXT,
                    last_success_time TEXT,
                    first_seen TEXT,
                    tls_avg_latency REAL DEFAULT 0,
                    protocol TEXT DEFAULT 'reality'
                )
            """)
            now = datetime.now().isoformat()

            success = result.get('success_rate', 0) > 0
            tcp_lat = result.get('tcp_avg_ms')

            cursor.execute("SELECT * FROM direct_node_performance WHERE ip = ?", (ip,))
            existing = cursor.fetchone()
            if existing:
                total = existing[2] + 1
                succ = existing[3] + (1 if success else 0)
                fail = existing[4] + (0 if success else 1)
                consec = (existing[5] + 1) if not success else 0
                old_avg = existing[6]
                old_succ = existing[3]
                if success and tcp_lat is not None:
                    new_avg = (old_avg * old_succ + tcp_lat) / (old_succ + 1) if old_succ > 0 else tcp_lat
                else:
                    new_avg = old_avg
                min_lat = min(existing[7], tcp_lat) if tcp_lat is not None else existing[7]
                max_lat = max(existing[8], tcp_lat) if tcp_lat is not None else existing[8]
                last_success = now if success else existing[10]
                cursor.execute("""
                    UPDATE direct_node_performance SET
                        total_tests=?, success_count=?, fail_count=?,
                        consecutive_fails=?, avg_latency=?, min_latency=?,
                        max_latency=?, last_test_time=?, last_success_time=?,
                        tls_avg_latency=?
                    WHERE ip=?
                """, (total, succ, fail, consec, new_avg, min_lat, max_lat,
                      now, last_success,
                      result.get('tls_avg_ms') or 0, ip))
            else:
                cursor.execute("""
                    INSERT INTO direct_node_performance
                    (ip, port, total_tests, success_count, fail_count,
                     consecutive_fails, avg_latency, min_latency, max_latency,
                     last_test_time, last_success_time, first_seen,
                     tls_avg_latency, protocol)
                    VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (ip, port, 1 if success else 0, 0 if success else 1,
                      0 if success else 1, tcp_lat or 0,
                      tcp_lat or 0, tcp_lat or 0,
                      now, now if success else None, now,
                      result.get('tls_avg_ms') or 0, 'reality'))
            conn.commit()
        except Exception as e:
            logger.debug(f"保存直连节点性能失败: {e}")
        finally:
            if conn:
                conn.close()