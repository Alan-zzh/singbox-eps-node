#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.5 CDN质量筛选与硬淘汰引擎
独立封装，可集成到订阅服务或其他模块

功能：
1. 硬淘汰：延时/丢包/速度不达标的IP直接淘汰
2. 用户网络探测：通过DDNS域名感知用户位置和链路质量
3. 区域适配度评分：根据用户位置评估CDN IP适配度
4. 用户链路质量评分：综合延时+丢包+区域适配
5. 综合评分：七维加权评分

[TRAE SOLO CN] v4.5 新增模块
"""

import json
import logging
import os
import socket
import sqlite3
import ssl
import time
import urllib.request
from datetime import datetime

logger = logging.getLogger('cdn_quality_filter')


class CdnQualityFilter:
    """
    CDN质量筛选与硬淘汰引擎

    使用方式：
        filter = CdnQualityFilter(db_path='/path/to/singbox.db')

        # 硬淘汰检查
        rejected, reason = filter.hard_reject('162.159.1.1')

        # 用户网络探测
        result = filter.probe_user_network()

        # 综合评分
        score = filter.calculate_score(ip='162.159.1.1', user_probe=result)

        # 批量筛选（淘汰+评分+排序）
        qualified = filter.filter_and_rank(ip_list)
    """

    # 默认硬淘汰阈值
    DEFAULT_HARD_REJECT = {
        'latency_ms': 100,           # VPS→CF延时超过100ms直接淘汰
        'user_path_latency_ms': 100, # 用户路径延时超过100ms直接淘汰
        'packet_loss_rate': 0.1,     # 丢包率超过10%直接淘汰
        'download_speed_mbps': 20,   # 下载速度低于20Mbps直接淘汰
    }

    # 默认用户质量阈值
    DEFAULT_USER_QUALITY = {
        'latency_ms': 100,
        'packet_loss_rate': 0.05,
        'download_speed_mbps': 20,
    }

    # 湖南电信已知优质CF IP段
    DEFAULT_OPTIMAL_PREFIXES = [
        '162.159.', '172.64.', '108.162.', '198.41.', '173.245.',
        '8.39.', '8.41.', '8.43.',
    ]

    # 八维评分权重（v4.6 新增跨网评分维度）
    SCORE_WEIGHTS = {
        'latency': 0.07,
        'speed': 0.07,
        'success_rate': 0.12,
        'stability': 0.10,
        'freshness': 0.04,
        'region_fitness': 0.10,
        'user_path': 0.18,
        'google_speed': 0.17,
        'cross_isp': 0.14,  # 新增：三网跨网综合评分
    }

    def __init__(self, db_path=None, ddns_domain='', expected_isp='电信',
                 hard_reject=None, user_quality=None, optimal_prefixes=None,
                 cf_domain='cloudflare.com', latency_spike_threshold=0.5):
        """
        初始化CDN质量筛选引擎

        Args:
            db_path: SQLite数据库路径
            ddns_domain: 用户DDNS域名（如 zzpzgroup.com）
            expected_isp: 用户预期运营商
            hard_reject: 硬淘汰阈值字典（覆盖默认值）
            user_quality: 用户质量阈值字典（覆盖默认值）
            optimal_prefixes: 优质CF IP段前缀列表
            cf_domain: Cloudflare域名（SNI用）
            latency_spike_threshold: 延时突增阈值（百分比）
        """
        self.db_path = db_path
        self.ddns_domain = ddns_domain
        self.expected_isp = expected_isp
        self.cf_domain = cf_domain
        self.latency_spike_threshold = latency_spike_threshold

        # 合并自定义阈值
        self._hard_reject_config = {**self.DEFAULT_HARD_REJECT, **(hard_reject or {})}
        self._user_quality_config = {**self.DEFAULT_USER_QUALITY, **(user_quality or {})}
        self._optimal_prefixes = optimal_prefixes or self.DEFAULT_OPTIMAL_PREFIXES

        # 缓存
        self._user_probe_cache = None
        self._user_probe_cache_time = 0
        self._cache_ttl = 300  # 缓存5分钟

    # ==================== 硬淘汰 ====================

    def hard_reject(self, ip, user_probe_result=None):
        """
        硬淘汰检查：不达标的IP直接淘汰，不进评分

        Args:
            ip: CDN IP地址
            user_probe_result: 用户网络探测结果（可选）

        Returns:
            (是否淘汰, 淘汰原因)
        """
        perf = self._get_ip_performance(ip)

        # VPS→CF延时检查
        if perf and perf.get('avg_latency', 0) > 0:
            if perf['avg_latency'] > self._hard_reject_config['latency_ms']:
                return True, f"CF延时{perf['avg_latency']:.0f}ms>{self._hard_reject_config['latency_ms']}ms"

        # 用户路径延时检查
        if user_probe_result and user_probe_result.get('http_latency_ms'):
            if user_probe_result['http_latency_ms'] > self._hard_reject_config['user_path_latency_ms']:
                return True, f"用户路径延时{user_probe_result['http_latency_ms']:.0f}ms>{self._hard_reject_config['user_path_latency_ms']}ms"

        # 丢包率检查（基于历史数据，至少3次测试）
        if perf and perf.get('total_tests', 0) >= 3:
            fail_rate = perf.get('fail_count', 0) / perf['total_tests']
            if fail_rate > self._hard_reject_config['packet_loss_rate']:
                return True, f"失败率{fail_rate*100:.0f}%>{self._hard_reject_config['packet_loss_rate']*100:.0f}%"

        # 速度检查
        if perf and perf.get('speed_mbps', 0) > 0:
            if perf['speed_mbps'] < self._hard_reject_config['download_speed_mbps']:
                return True, f"速度{perf['speed_mbps']:.1f}Mbps<{self._hard_reject_config['download_speed_mbps']}Mbps"

        return False, ""

    def hard_reject_current(self, ip):
        """
        检查当前正在使用的IP是否需要硬淘汰
        用于订阅服务实时判断，即使IP连通但质量差也自动换

        Args:
            ip: 当前使用的CDN IP

        Returns:
            (是否淘汰, 淘汰原因)
        """
        perf = self._get_ip_performance(ip)
        if not perf or perf.get('total_tests', 0) < 3:
            return False, ""  # 数据不足，暂不淘汰

        avg_lat = perf.get('avg_latency', 0)
        fail_rate = perf.get('fail_count', 0) / perf['total_tests']
        speed = perf.get('speed_mbps', 0)

        if avg_lat > 0 and avg_lat > self._hard_reject_config['latency_ms']:
            return True, f"延时{avg_lat:.0f}ms>{self._hard_reject_config['latency_ms']}ms"
        if fail_rate > self._hard_reject_config['packet_loss_rate']:
            return True, f"失败率{fail_rate*100:.0f}%>{self._hard_reject_config['packet_loss_rate']*100:.0f}%"
        if speed > 0 and speed < self._hard_reject_config['download_speed_mbps']:
            return True, f"速度{speed:.1f}Mbps<{self._hard_reject_config['download_speed_mbps']}Mbps"

        return False, ""

    # ==================== 用户网络探测 ====================

    def probe_user_network(self, force=False):
        """
        通过DDNS域名探测用户网络状态

        Args:
            force: 是否强制刷新（忽略缓存）

        Returns:
            dict 或 None
        """
        if not self.ddns_domain:
            return None

        # 缓存检查
        now = time.time()
        if not force and self._user_probe_cache and (now - self._user_probe_cache_time) < self._cache_ttl:
            return self._user_probe_cache

        result = self._do_probe()
        if result:
            self._user_probe_cache = result
            self._user_probe_cache_time = now
        return result

    def _do_probe(self):
        """执行实际的网络探测"""
        # 解析DDNS域名
        user_ip = self._resolve_ddns()
        if not user_ip:
            logger.warning(f"DDNS域名 {self.ddns_domain} 解析失败")
            return None

        logger.info(f"DDNS解析: {self.ddns_domain} → {user_ip}")

        # IP变更检测
        last_ip = self._get_last_user_ip()
        ip_changed = (last_ip is not None and last_ip != user_ip)

        # IP归属地查询
        user_isp, user_region = self._query_ip_geo(user_ip, force=ip_changed or not last_ip)

        # TCP延时探测（3次取平均）
        latencies = []
        for _ in range(3):
            lat = self._tcp_ping(user_ip, 443, timeout=5)
            if lat is not None:
                latencies.append(lat)
            time.sleep(0.3)
        avg_latency = sum(latencies) / len(latencies) if latencies else 9999

        # HTTP全链路延时
        http_latency = self._http_latency_test()

        # 丢包率检测（5次TCP）
        fail_count = sum(1 for _ in range(5) if not self._tcp_ping(user_ip, 443, timeout=3))
        packet_loss_rate = fail_count / 5

        # 质量达标判断
        quality_ok = True
        if avg_latency > self._user_quality_config['latency_ms']:
            quality_ok = False
        if packet_loss_rate > self._user_quality_config['packet_loss_rate']:
            quality_ok = False

        # 延时突增检测
        latency_spike = False
        if last_ip:
            hist_avg = self._get_historical_avg_latency()
            if hist_avg and hist_avg > 0 and avg_latency > hist_avg * (1 + self.latency_spike_threshold):
                latency_spike = True

        result = {
            'ip': user_ip,
            'isp': user_isp,
            'region': user_region,
            'latency_ms': avg_latency,
            'http_latency_ms': http_latency,
            'packet_loss_rate': packet_loss_rate,
            'ip_changed': ip_changed,
            'latency_spike': latency_spike,
            'quality_ok': quality_ok,
        }

        # 保存到数据库
        self._save_user_state(result)

        logger.info(f"探测结果: 延时={avg_latency:.0f}ms 丢包={packet_loss_rate*100:.0f}% 质量={'达标' if quality_ok else '不达标'}")
        return result

    # ==================== 评分 ====================

    def calculate_score(self, ip, user_probe_result=None):
        """
        七维综合评分

        Args:
            ip: CDN IP地址
            user_probe_result: 用户网络探测结果

        Returns:
            float 0-100
        """
        perf = self._get_ip_performance(ip)
        if not perf or perf.get('total_tests', 0) == 0:
            return 50.0  # 新IP给中等分

        total = perf['total_tests']
        success = perf.get('success_count', 0)
        avg_lat = perf.get('avg_latency', 0)
        consec_fails = perf.get('consecutive_fails', 0)
        last_success = perf.get('last_success_time')
        speed = perf.get('speed_mbps', 0) or 0

        # 1. 延迟分
        latency_score = max(0, 100 * (1 - avg_lat / 500)) if avg_lat > 0 else 50

        # 2. 速度分
        if speed >= 50:
            speed_score = 100
        elif speed >= 30:
            speed_score = 80
        elif speed >= 20:
            speed_score = 60
        elif speed >= 10:
            speed_score = 40
        elif speed >= 1:
            speed_score = 20
        elif speed > 0:
            speed_score = 10
        else:
            speed_score = 0

        # 3. 成功率分
        success_score = (success / total * 100) if total > 0 else 0

        # 4. 稳定性分
        stability_score = max(0, 100 - consec_fails * 20)

        # 5. 新鲜度分
        freshness_score = 0
        if last_success:
            try:
                last_dt = datetime.fromisoformat(last_success)
                days_since = (datetime.now() - last_dt).days
                freshness_score = max(0, 100 - days_since * 33)
            except Exception:
                pass

        # 6. 区域适配度
        region_fitness = self._calc_region_fitness(
            ip,
            user_probe_result.get('isp', '') if user_probe_result else '',
            user_probe_result.get('region', '') if user_probe_result else ''
        )

        # 7. 用户链路质量
        user_path = self._calc_user_path_quality(ip, user_probe_result)

        # 8. 三网跨网综合评分（v4.6）
        cross_isp = self.calculate_cross_isp_score(ip)

        # 9. 谷歌速度评分（CDN→谷歌服务的速度）
        google_speed_score = 50  # 默认中等分
        if user_probe_result:
            # 执行谷歌测速（缓存结果）
            google_result = self.test_cdn_to_google_speed(ip)
            if google_result['success']:
                g_latency = google_result['latency_ms']
                g_speed = google_result['speed_mbps']
                # 延时分
                if g_latency < 100:
                    g_lat_score = 100
                elif g_latency < 200:
                    g_lat_score = 80
                elif g_latency < 300:
                    g_lat_score = 50
                else:
                    g_lat_score = 0
                # 速度分
                if g_speed >= 30:
                    g_speed_score = 100
                elif g_speed >= 20:
                    g_speed_score = 80
                elif g_speed >= 10:
                    g_speed_score = 60
                elif g_speed >= 5:
                    g_speed_score = 40
                else:
                    g_speed_score = 20
                google_speed_score = round(g_lat_score * 0.5 + g_speed_score * 0.5)

        # 加权总分
        w = self.SCORE_WEIGHTS
        total_score = (
            latency_score * w['latency'] +
            speed_score * w['speed'] +
            success_score * w['success_rate'] +
            stability_score * w['stability'] +
            freshness_score * w['freshness'] +
            region_fitness * w['region_fitness'] +
            user_path * w['user_path'] +
            google_speed_score * w['google_speed'] +
            cross_isp * w['cross_isp']
        )
        return round(total_score, 2)

    def filter_and_rank(self, ip_list, user_probe_result=None):
        """
        批量筛选：硬淘汰 → 评分 → 排序

        Args:
            ip_list: CDN IP列表
            user_probe_result: 用户网络探测结果

        Returns:
            list of (ip, score) 按评分降序排列，已淘汰的IP不在列表中
        """
        qualified = []
        rejected_count = 0

        for ip in ip_list:
            rejected, reason = self.hard_reject(ip, user_probe_result)
            if rejected:
                logger.debug(f"  {ip} 硬淘汰: {reason}")
                rejected_count += 1
                continue

            score = self.calculate_score(ip, user_probe_result)
            qualified.append((ip, score))

        qualified.sort(key=lambda x: -x[1])
        logger.info(f"筛选结果: {len(ip_list)}个IP → 淘汰{rejected_count}个 → 合格{len(qualified)}个")
        return qualified

    def select_best_ips(self, ip_list, count=3, top_n=5, user_probe_result=None):
        """
        从IP列表中选出最优的N个IP

        Args:
            ip_list: CDN IP列表
            count: 需要选出的IP数量
            top_n: 从评分TopN中随机选（防单点故障）
            user_probe_result: 用户网络探测结果

        Returns:
            list of ip
        """
        ranked = self.filter_and_rank(ip_list, user_probe_result)
        if not ranked:
            return []

        import random
        top_ips = [ip for ip, score in ranked[:top_n]]
        if len(top_ips) >= count:
            return random.sample(top_ips, count)
        return top_ips[:count]

    # ==================== 内部方法 ====================

    def _calc_region_fitness(self, ip, user_isp, user_region):
        """区域适配度评分"""
        if user_isp and '电信' in user_isp and user_region and '湖南' in user_region:
            for prefix in self._optimal_prefixes:
                if ip.startswith(prefix):
                    return 100
            if ip.startswith('104.'):
                return 20
            return 50
        return 50

    def _calc_user_path_quality(self, ip, user_probe_result):
        """用户链路质量评分"""
        if not user_probe_result:
            return 50

        latency = user_probe_result.get('latency_ms', 9999)
        packet_loss = user_probe_result.get('packet_loss_rate', 1.0)

        # 延时分
        if latency < 50:
            lat_score = 100
        elif latency < 100:
            lat_score = 80
        elif latency < 200:
            lat_score = 50
        else:
            lat_score = 0

        # 丢包分
        if packet_loss == 0:
            loss_score = 100
        elif packet_loss <= 0.05:
            loss_score = 80
        elif packet_loss <= 0.10:
            loss_score = 50
        else:
            loss_score = 0

        # 区域适配度
        region_score = self._calc_region_fitness(
            ip, user_probe_result.get('isp', ''), user_probe_result.get('region', '')
        )

        return round(lat_score * 0.4 + loss_score * 0.3 + region_score * 0.3, 2)

    # ==================== v4.6 三网最优优选 ====================

    def calculate_cross_isp_score(self, ip):
        """
        计算CDN IP的跨网综合评分（电信/联通/移动三网）

        原理：IP落在某运营商已知优质段内→该网满分
              IP不在任何已知优质段→中等分
              综合 = max(三网各自得分)，取三网最优值

        返回: float 0-100
        """
        try:
            from config import THREE_ISP_OPTIMAL_PREFIXES
        except ImportError:
            return 50

        isp_scores = {}
        for isp_key, isp_data in THREE_ISP_OPTIMAL_PREFIXES.items():
            for prefix in isp_data['prefixes']:
                if ip.startswith(prefix):
                    isp_scores[isp_key] = 100
                    break
            if isp_key not in isp_scores:
                isp_scores[isp_key] = 50  # 不在已知优质段，中等分

        # 三网取最优（因为用户只需要一个最优IP即可）
        if isp_scores:
            best_score = max(isp_scores.values())
            # 如果IP在三网中都优质，给满分
            if len([s for s in isp_scores.values() if s == 100]) >= 2:
                best_score = 100
            return best_score

        return 50

    def probe_three_networks(self, ip_list=None, user_probe_result=None):
        """
        三网综合探测：模拟三网用户视角评估CDN IP质量

        原理：
        1. 电信：使用用户DDNS域名实测（已有数据）
        2. 联通/移动：通过IP段前缀匹配估算（VPS无法直接测联通/移动网络）
        3. 综合输出三网最优IP列表

        Args:
            ip_list: 待评估IP列表，None则从数据库获取
            user_probe_result: 用户网络探测结果（电信实测）

        Returns:
            {
                'telecom_best': [(ip, score), ...],   # 电信最优
                'unicom_best': [(ip, score), ...],     # 联通最优
                'mobile_best': [(ip, score), ...],     # 移动最优
                'overall_best': [(ip, score), ...],    # 三网综合最优
            }
        """
        if ip_list is None:
            ip_list = self._get_all_monitored_ips()

        if not ip_list:
            return {'telecom_best': [], 'unicom_best': [], 'mobile_best': [],
                    'overall_best': []}

        scored = []
        try:
            from config import THREE_ISP_OPTIMAL_PREFIXES
        except ImportError:
            THREE_ISP_OPTIMAL_PREFIXES = {}

        for ip in ip_list:
            rejected, _ = self.hard_reject(ip, user_probe_result)
            if rejected:
                continue

            base_score = self.calculate_score(ip, user_probe_result)
            cross_isp = self.calculate_cross_isp_score(ip)

            # 各ISP独立评分
            isp_scores = {}
            for isp_key in THREE_ISP_OPTIMAL_PREFIXES:
                isp_fit = 100 if self._ip_matches_isp(ip, isp_key) else 50
                # 该ISP评分 = 基础评分 × 0.7 + ISP适配 × 0.3
                isp_scores[isp_key] = round(base_score * 0.7 + isp_fit * 0.3, 2)

            scored.append({
                'ip': ip,
                'base_score': base_score,
                'cross_isp': cross_isp,
                'isp_scores': isp_scores,
                'overall': round(base_score * 0.85 + cross_isp * 0.15, 2),
            })

        # 排序
        telecom_best = sorted(scored, key=lambda x: -x['isp_scores'].get('telecom', 0))
        unicom_best = sorted(scored, key=lambda x: -x['isp_scores'].get('unicom', 0))
        mobile_best = sorted(scored, key=lambda x: -x['isp_scores'].get('mobile', 0))
        overall_best = sorted(scored, key=lambda x: -x['overall'])

        def to_tuples(items):
            return [(item['ip'], item['overall']) for item in items[:10]]

        logger.info(f"三网探测完成: {len(scored)}个IP → 电信最优 {telecom_best[0]['ip'] if telecom_best else 'N/A'}")
        return {
            'telecom_best': to_tuples(telecom_best),
            'unicom_best': to_tuples(unicom_best),
            'mobile_best': to_tuples(mobile_best),
            'overall_best': to_tuples(overall_best),
        }

    def _ip_matches_isp(self, ip, isp_key):
        """判断IP是否匹配某ISP的优质段"""
        try:
            from config import THREE_ISP_OPTIMAL_PREFIXES
            prefixes = THREE_ISP_OPTIMAL_PREFIXES.get(isp_key, {}).get('prefixes', [])
            for prefix in prefixes:
                if ip.startswith(prefix):
                    return True
        except ImportError:
            pass
        return False

    def _get_all_monitored_ips(self):
        """从数据库获取所有受监控的CDN IP"""
        if not self.db_path or not os.path.exists(self.db_path):
            return []
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT ip FROM ip_performance")
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            if conn:
                conn.close()

    def _get_ip_performance(self, ip):
        """从数据库获取IP性能数据"""
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ip_performance WHERE ip = ?", (ip,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

    def _resolve_ddns(self):
        """解析DDNS域名"""
        try:
            import socket
            ips = socket.getaddrinfo(self.ddns_domain, 443, socket.AF_INET)
            return ips[0][4][0] if ips else None
        except Exception:
            return None

    def _get_last_user_ip(self):
        """获取上次记录的用户IP"""
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT user_ip FROM user_network_state ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

    def _query_ip_geo(self, ip, force=False):
        """查询IP归属地"""
        if not force:
            # 尝试复用缓存
            if not self.db_path or not os.path.exists(self.db_path):
                return '', ''
            conn = None
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT user_isp, user_region FROM user_network_state WHERE user_isp != '' ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return row[0], row[1]
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

        # 在线查询
        try:
            url = f"http://ip-api.com/json/{ip}?lang=zh-CN"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get('isp', ''), data.get('regionName', '')
        except Exception:
            return '', ''

    def _tcp_ping(self, ip, port=443, timeout=5):
        """TCP ping测延时，返回毫秒或None"""
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

    def _http_latency_test(self):
        """HTTP全链路延时测试"""
        try:
            start = time.time()
            req = urllib.request.Request(
                f"https://{self.ddns_domain}/",
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                resp.read(1)
            return (time.time() - start) * 1000
        except Exception:
            return None

    def test_cdn_to_google_speed(self, cdn_ip, port=443, timeout=15):
        """
        测试CDN节点到谷歌服务的速度（通过CDN访问谷歌测速）
        
        原理：通过CDN IP访问谷歌服务，测量完整链路速度
        返回: {'latency_ms': float, 'speed_mbps': float, 'success': bool}
        """
        sni_host = self.cf_domain
        if not sni_host:
            sni_host = 'www.google.com'
        
        sock = None
        ssock = None
        start_time = time.time()
        
        try:
            # 连接CDN IP
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((cdn_ip, port))

            # TLS握手
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ssock = ctx.wrap_socket(sock, server_hostname=sni_host)

            # 发送HTTP请求到谷歌
            request = f"GET /generate_204 HTTP/1.1\r\nHost: www.google.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            ssock.sendall(request.encode())

            # 读取响应
            response = b""
            while b"\r\n\r\n" not in response:
                chunk = ssock.recv(4096)
                if not chunk:
                    break
                response += chunk

            handshake_time = (time.time() - start_time) * 1000

            # 下载小文件测速度
            download_start = time.time()
            request_size = f"GET /favicon.ico HTTP/1.1\r\nHost: www.google.com\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n"
            ssock = None  # 重新建立连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((cdn_ip, port))
            ssock = ctx.wrap_socket(sock, server_hostname=sni_host)
            ssock.sendall(request_size.encode())
            
            download_data = b""
            while True:
                chunk = ssock.recv(4096)
                if not chunk:
                    break
                download_data += chunk
                if len(download_data) > 1024 * 1024:  # 最多下载1MB
                    break

            download_time = time.time() - download_start
            speed_mbps = 0
            if download_time > 0 and len(download_data) > 0:
                speed_mbps = (len(download_data) * 8) / (1024 * 1024 * download_time)

            return {
                'latency_ms': handshake_time,
                'speed_mbps': speed_mbps,
                'success': True
            }

        except Exception as e:
            logger.debug(f"CDN→谷歌测速失败 {cdn_ip}: {e}")
            return {
                'latency_ms': 9999,
                'speed_mbps': 0,
                'success': False
            }
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

    def _get_historical_avg_latency(self):
        """获取历史平均延时"""
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(latency_ms) FROM user_network_state WHERE latency_ms > 0 AND latency_ms < 9999 ORDER BY id DESC LIMIT 10")
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
        except Exception:
            return None
        finally:
            if conn:
                conn.close()

    def _save_user_state(self, result):
        """保存用户网络状态到数据库"""
        if not self.db_path:
            return
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            # 确保表存在
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_network_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT (datetime('now', 'localtime')),
                    user_ip TEXT,
                    user_isp TEXT,
                    user_region TEXT,
                    latency_ms REAL,
                    http_latency_ms REAL,
                    download_speed_mbps REAL,
                    packet_loss_rate REAL,
                    ip_changed INTEGER DEFAULT 0,
                    latency_spike INTEGER DEFAULT 0,
                    quality_ok INTEGER DEFAULT 1
                )
            """)
            cursor.execute("""
                INSERT INTO user_network_state
                (user_ip, user_isp, user_region, latency_ms, http_latency_ms,
                 packet_loss_rate, ip_changed, latency_spike, quality_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (result['ip'], result['isp'], result['region'],
                  result['latency_ms'], result.get('http_latency_ms'),
                  result['packet_loss_rate'],
                  1 if result['ip_changed'] else 0,
                  1 if result['latency_spike'] else 0,
                  1 if result['quality_ok'] else 0))
            conn.commit()
        except Exception as e:
            logger.debug(f"保存用户网络状态失败: {e}")
        finally:
            if conn:
                conn.close()


# ==================== v4.6 CDN故障自愈：健康监控 ====================

class CdnHealthMonitor:
    """
    CDN IP健康监控器
    持续监控当前分配的CDN IP状态，检测延时/丢包异常

    使用方式：
        monitor = CdnHealthMonitor(db_path='/path/to/singbox.db')
        status = monitor.check_ip('162.159.1.1')
        # status: {'healthy': True/False, 'latency_ms': 45, ...}
    """

    DEFAULT_LATENCY_THRESHOLD = 200   # 延时超过200ms标记不健康
    DEFAULT_LOSS_THRESHOLD = 0.15     # 丢包超过15%标记不健康
    CHECK_TIMEOUT = 5                 # 单次检测超时

    def __init__(self, db_path=None, latency_threshold=None, loss_threshold=None):
        self.db_path = db_path
        self.latency_threshold = latency_threshold or self.DEFAULT_LATENCY_THRESHOLD
        self.loss_threshold = loss_threshold or self.DEFAULT_LOSS_THRESHOLD
        self._check_history = {}  # ip -> [(timestamp, healthy), ...]

    def check_ip(self, ip, port=443):
        """
        检查单个IP的健康状态

        返回:
            {'healthy': bool, 'latency_ms': float|None,
             'packet_loss_rate': float, 'consecutive_fails': int,
             'last_ok_time': str|None}
        """
        latencies = []
        for _ in range(3):
            lat = self._tcp_ping(ip, port, self.CHECK_TIMEOUT)
            if lat is not None:
                latencies.append(lat)
            time.sleep(0.2)

        avg_latency = sum(latencies) / len(latencies) if latencies else None
        fail_count = 3 - len(latencies)
        loss_rate = fail_count / 3

        # 历史数据
        hist = self._get_performance(ip)
        consec_fails = 0
        last_ok = None
        if hist:
            consec_fails = hist.get('consecutive_fails', 0)
            last_ok = hist.get('last_success_time')

        # 健康判断
        latency_ok = True
        if avg_latency is not None and avg_latency > self.latency_threshold:
            latency_ok = False
        loss_ok = loss_rate <= self.loss_threshold

        healthy = latency_ok and loss_ok and fail_count < 2

        # 记录历史
        if ip not in self._check_history:
            self._check_history[ip] = []
        self._check_history[ip].append((time.time(), healthy))
        # 只保留最近20条
        if len(self._check_history[ip]) > 20:
            self._check_history[ip] = self._check_history[ip][-20:]

        return {
            'healthy': healthy,
            'latency_ms': round(avg_latency, 1) if avg_latency else None,
            'packet_loss_rate': round(loss_rate, 3),
            'consecutive_fails': consec_fails + (0 if healthy else 1),
            'last_ok_time': last_ok,
        }

    def get_recent_failure_rate(self, ip, window_seconds=300):
        """获取IP在时间窗口内的失败率"""
        if ip not in self._check_history:
            return 0
        now = time.time()
        recent = [h for t, h in self._check_history[ip] if now - t <= window_seconds]
        if not recent:
            return 0
        return sum(1 for h in recent if not h) / len(recent)

    def _tcp_ping(self, ip, port, timeout):
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

    def _get_performance(self, ip):
        if not self.db_path or not os.path.exists(self.db_path):
            return None
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ip_performance WHERE ip = ?", (ip,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception:
            return None
        finally:
            if conn:
                conn.close()


class CdnFailoverController:
    """
    CDN故障切换控制器（v4.6.1 精简版）
    管理故障IP冷却池、自动切换决策、迟滞防抖

    核心原则：
    - 当前IP没问题就不换（迟滞机制：新IP必须比当前好15%以上才换）
    - 有问题才换，换到池中最优的
    - 故障IP进冷却池，5分钟后才可重新选中
    - CF防封：探测间隔不低于30秒，单IP每分钟最多2次探测

    使用方式：
        controller = CdnFailoverController(db_path='/path/to/singbox.db')
        decision = controller.decide_switch(current_ip='162.159.1.1', available_pool=['ip1', 'ip2'])
        # decision: {'switch': bool, 'new_ip': str|None, 'reason': str}
    """

    # 迟滞阈值：新IP评分必须比当前高15%才触发切换
    HYSTERESIS_THRESHOLD = 0.15

    # CF防封：探测频率限制
    MIN_PROBE_INTERVAL_SEC = 30      # 两次探测最小间隔
    MAX_PROBES_PER_IP_PER_MIN = 2    # 单IP每分钟最多探测次数

    def __init__(self, db_path=None, cooldown_sec=300, min_stable_duration_sec=60,
                 health_monitor=None):
        self.db_path = db_path
        self.cooldown_sec = cooldown_sec
        self.min_stable_duration_sec = min_stable_duration_sec
        self.health_monitor = health_monitor or CdnHealthMonitor(db_path=db_path)

        # 状态
        self._cooldown_pool = {}      # ip -> 冷却结束时间戳
        self._switch_count = 0        # 连续切换计数
        self._last_switch_time = 0    # 上次切换时间
        self._current_ip = None       # 当前使用的IP
        self._current_score = 0       # 当前IP评分
        self._last_probe_time = 0     # 上次探测时间
        self._probe_count_per_ip = {} # ip -> [(timestamp), ...] CF防封计数

    def decide_switch(self, current_ip, available_pool, quality_filter=None, user_probe=None):
        """
        故障切换决策（含迟滞机制）

        切换条件（必须同时满足）：
        1. 当前IP不健康（延时>200ms 或 丢包>15%）
        2. 新IP评分 > 当前IP评分 × (1 + HYSTERESIS_THRESHOLD)
        3. 距上次切换超过稳定期
        4. CF探测频率未超限

        Args:
            current_ip: 当前使用的CDN IP
            available_pool: 可用IP池
            quality_filter: CdnQualityFilter实例
            user_probe: 用户网络探测结果

        Returns:
            {'switch': bool, 'new_ip': str|None, 'reason': str}
        """
        self._current_ip = current_ip

        # 0. CF防封检查
        now = time.time()
        if now - self._last_probe_time < self.MIN_PROBE_INTERVAL_SEC:
            return {'switch': False, 'new_ip': None, 'reason': 'CF防封：探测间隔过短'}

        # 1. 健康检查当前IP
        status = self.health_monitor.check_ip(current_ip)
        self._last_probe_time = now
        self._record_probe(current_ip)

        if status['healthy']:
            # 当前IP健康 → 重置切换计数
            self._switch_count = 0

            # 即使健康，也检查是否有明显更优的IP（迟滞：好15%以上才换）
            if quality_filter and available_pool:
                current_score = quality_filter.calculate_score(current_ip, user_probe)
                self._current_score = current_score

                # 清理冷却池中过期IP
                expired = [ip for ip, end in self._cooldown_pool.items() if now >= end]
                for ip in expired:
                    del self._cooldown_pool[ip]

                clean_pool = [ip for ip in available_pool
                              if ip != current_ip and ip not in self._cooldown_pool]
                if clean_pool:
                    ranked = quality_filter.filter_and_rank(clean_pool, user_probe)
                    if ranked:
                        best_ip, best_score = ranked[0]
                        # 迟滞：新IP必须好15%以上
                        threshold = current_score * (1 + self.HYSTERESIS_THRESHOLD)
                        if best_score > threshold and best_score > current_score + 10:
                            # 稳定期保护
                            if self._last_switch_time > 0:
                                elapsed = now - self._last_switch_time
                                if elapsed < self.min_stable_duration_sec:
                                    return {'switch': False, 'new_ip': None,
                                            'reason': f'发现更优IP {best_ip}({best_score:.0f})但稳定期保护中'}

                            logger.info(f"发现更优IP: {best_ip}({best_score:.0f}) > {current_ip}({current_score:.0f})+15%")
                            self._switch_count += 1
                            self._last_switch_time = now
                            self._cooldown_pool[current_ip] = now + self.cooldown_sec
                            return {
                                'switch': True, 'new_ip': best_ip,
                                'reason': f'更优: {best_ip}({best_score:.0f}) > {current_ip}({current_score:.0f})+15%',
                            }

            return {'switch': False, 'new_ip': None, 'reason': '健康，无需切换'}

        # 2. 当前IP不健康 → 必须切换
        # 稳定期保护
        if self._last_switch_time > 0:
            elapsed = now - self._last_switch_time
            if elapsed < self.min_stable_duration_sec:
                logger.info(f"切换后仅{elapsed:.0f}秒，稳定期保护中")
                return {'switch': False, 'new_ip': None, 'reason': '稳定期保护'}

        # 3. 清理冷却池 + 筛选可用IP
        expired = [ip for ip, end in self._cooldown_pool.items() if now >= end]
        for ip in expired:
            del self._cooldown_pool[ip]

        clean_pool = [ip for ip in available_pool
                      if ip != current_ip and ip not in self._cooldown_pool]

        if not clean_pool:
            logger.warning("所有IP都在冷却中，无可用备选")
            return {'switch': False, 'new_ip': None, 'reason': '无可用备选'}

        # 4. 选择新IP（评分最优）
        new_ip = None
        if quality_filter:
            ranked = quality_filter.filter_and_rank(clean_pool, user_probe)
            if ranked:
                new_ip = ranked[0][0]
        if not new_ip:
            import random
            new_ip = random.choice(clean_pool)

        # 5. 故障IP加入冷却池
        self._cooldown_pool[current_ip] = now + self.cooldown_sec
        logger.info(f"IP {current_ip} 故障(延时{status['latency_ms']}ms/丢包{status['packet_loss_rate']}) → 切换到 {new_ip}，冷却{self.cooldown_sec}秒")

        # 6. 更新状态
        self._switch_count += 1
        self._last_switch_time = now

        return {
            'switch': True, 'new_ip': new_ip,
            'reason': f"故障切换: {current_ip}延时{status['latency_ms']}ms → {new_ip}",
        }

    def add_to_cooldown(self, ip, duration_sec=None):
        """手动加入冷却池"""
        dur = duration_sec or self.cooldown_sec
        self._cooldown_pool[ip] = time.time() + dur

    def remove_from_cooldown(self, ip):
        """手动解除冷却"""
        self._cooldown_pool.pop(ip, None)

    def _record_probe(self, ip):
        """记录探测次数（CF防封）"""
        now = time.time()
        if ip not in self._probe_count_per_ip:
            self._probe_count_per_ip[ip] = []
        self._probe_count_per_ip[ip].append(now)
        # 只保留最近60秒的记录
        self._probe_count_per_ip[ip] = [t for t in self._probe_count_per_ip[ip] if now - t <= 60]

    def _is_probe_rate_limited(self, ip):
        """检查IP探测频率是否超限"""
        now = time.time()
        recent = [t for t in self._probe_count_per_ip.get(ip, []) if now - t <= 60]
        return len(recent) >= self.MAX_PROBES_PER_IP_PER_MIN

    def get_status(self):
        """获取控制器状态（供API查询）"""
        now = time.time()
        cooldown_list = [
            {'ip': ip, 'remaining_sec': max(0, end - now)}
            for ip, end in self._cooldown_pool.items()
        ]
        return {
            'current_ip': self._current_ip,
            'current_score': self._current_score,
            'cooldown_pool': cooldown_list,
            'switch_count': self._switch_count,
            'last_switch_time': self._last_switch_time,
        }
