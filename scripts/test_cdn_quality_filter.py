#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.5 CDN硬淘汰阈值验证测试脚本
模拟用户网络探测逻辑，验证延时/速度/丢包硬淘汰是否生效

运行方式：
    python scripts/test_cdn_quality_filter.py

[TRAE SOLO CN] v4.5 测试脚本
"""

import os
import sys
import sqlite3
import tempfile

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from cdn_quality_filter import CdnQualityFilter


def create_test_db(db_path):
    """创建测试数据库并插入模拟数据"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建ip_performance表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ip_performance (
            ip TEXT PRIMARY KEY,
            total_tests INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            consecutive_fails INTEGER DEFAULT 0,
            avg_latency REAL DEFAULT 0,
            min_latency REAL DEFAULT 0,
            max_latency REAL DEFAULT 0,
            last_test_time TEXT,
            last_success_time TEXT,
            first_seen TEXT,
            source TEXT DEFAULT 'local',
            speed_mbps REAL DEFAULT 0
        )
    """)

    # 创建user_network_state表
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

    # 插入模拟IP性能数据
    test_ips = [
        # (ip, total_tests, success, fail, consec_fails, avg_latency, speed_mbps, 预期结果)
        ('162.159.1.1',  10, 10, 0, 0, 50,   50,   '✅ 通过'),   # 延时50ms, 速度50Mbps → 应通过
        ('162.159.1.2',  10, 9,  1, 0, 80,   30,   '✅ 通过'),   # 延时80ms, 速度30Mbps → 应通过
        ('162.159.1.3',  10, 9,  1, 0, 99,   25,   '✅ 通过'),   # 延时99ms, 速度25Mbps, 失败率10% → 应通过(等于阈值)
        ('162.159.1.4',  10, 7,  3, 2, 101,  25,   '❌ 淘汰'),   # 延时101ms > 100ms → 应淘汰
        ('172.64.1.1',   10, 5,  5, 3, 60,   15,   '❌ 淘汰'),   # 速度15Mbps < 20Mbps → 应淘汰
        ('172.64.1.2',   10, 4,  6, 4, 70,   10,   '❌ 淘汰'),   # 速度10Mbps < 20Mbps → 应淘汰
        ('104.18.1.1',   10, 9,  1, 0, 120,  40,   '❌ 淘汰'),   # 延时120ms > 100ms → 应淘汰
        ('108.162.1.1',  10, 3,  7, 5, 50,   30,   '❌ 淘汰'),   # 失败率70% > 10% → 应淘汰
        ('198.41.1.1',   10, 8,  2, 1, 85,   19,   '❌ 淘汰'),   # 速度19Mbps < 20Mbps → 应淘汰
        ('8.39.1.1',     10, 10, 0, 0, 45,   60,   '✅ 通过'),   # 延时45ms, 速度60Mbps → 应通过
        ('8.39.1.2',     3,  3,  0, 0, 90,   0,    '✅ 通过'),   # 测试次数不足3次，速度无数据 → 不淘汰
        ('173.245.1.1',  10, 10, 0, 0, 100,  20,   '✅ 通过'),   # 延时=100ms(不超), 速度=20Mbps(不低) → 刚好通过
        ('173.245.1.2',  10, 10, 0, 0, 101,  20,   '❌ 淘汰'),   # 延时101ms > 100ms → 应淘汰
        ('173.245.1.3',  10, 10, 0, 0, 80,   19.5, '❌ 淘汰'),   # 速度19.5Mbps < 20Mbps → 应淘汰
    ]

    for ip_data in test_ips:
        ip, total, success, fail, consec, avg_lat, speed, _ = ip_data
        cursor.execute("""
            INSERT OR REPLACE INTO ip_performance
            (ip, total_tests, success_count, fail_count, consecutive_fails,
             avg_latency, min_latency, max_latency, last_test_time,
             last_success_time, first_seen, source, speed_mbps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), datetime('now'), 'test', ?)
        """, (ip, total, success, fail, consec, avg_lat, avg_lat * 0.8, avg_lat * 1.2, speed))

    conn.commit()
    conn.close()
    return test_ips


def test_hard_reject():
    """测试硬淘汰逻辑"""
    print("=" * 70)
    print("  CDN硬淘汰阈值验证测试")
    print("  阈值: 延时>100ms / 丢包>10% / 速度<20Mbps")
    print("=" * 70)

    # 创建临时数据库
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    try:
        test_ips = create_test_db(db_path)

        # 初始化筛选引擎
        cqf = CdnQualityFilter(
            db_path=db_path,
            ddns_domain='zzpzgroup.com',
            expected_isp='电信',
            hard_reject={
                'latency_ms': 100,
                'user_path_latency_ms': 100,
                'packet_loss_rate': 0.1,
                'download_speed_mbps': 20,
            }
        )

        # 逐个测试
        passed = 0
        failed = 0
        print(f"\n{'IP':<18} {'延时':>8} {'速度':>10} {'失败率':>8} {'实际结果':<12} {'预期结果':<12} {'判定'}")
        print("-" * 70)

        for ip_data in test_ips:
            ip, total, success, fail_count, consec, avg_lat, speed, expected = ip_data
            fail_rate = fail_count / total

            rejected, reason = cqf.hard_reject(ip)
            actual = '❌ 淘汰' if rejected else '✅ 通过'

            # 判定是否与预期一致
            is_correct = (rejected and '❌' in expected) or (not rejected and '✅' in expected)
            verdict = '✅ 正确' if is_correct else '❌ 错误'

            if is_correct:
                passed += 1
            else:
                failed += 1

            reason_str = f'({reason})' if reason else ''
            print(f"{ip:<18} {avg_lat:>6.0f}ms {speed:>7.1f}Mbps {fail_rate*100:>5.0f}%  {actual:<12} {expected:<12} {verdict} {reason_str}")

        print("-" * 70)
        print(f"测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 项")

        # 测试批量筛选
        print("\n" + "=" * 70)
        print("  批量筛选测试 (filter_and_rank)")
        print("=" * 70)

        all_ips = [ip_data[0] for ip_data in test_ips]
        ranked = cqf.filter_and_rank(all_ips)

        print(f"\n输入: {len(all_ips)} 个IP")
        print(f"输出: {len(ranked)} 个合格IP")
        print(f"\n排名  {'IP':<18} {'评分':>8}")
        print("-" * 40)
        for i, (ip, score) in enumerate(ranked, 1):
            print(f"{i:>4}  {ip:<18} {score:>8.2f}")

        # 测试选最优IP
        print("\n" + "=" * 70)
        print("  选最优IP测试 (select_best_ips)")
        print("=" * 70)

        best = cqf.select_best_ips(all_ips, count=3, top_n=5)
        print(f"\n从 {len(all_ips)} 个IP中选出3个最优: {best}")

        return failed == 0

    finally:
        os.unlink(db_path)


def test_user_probe_simulation():
    """模拟用户网络探测逻辑"""
    print("\n" + "=" * 70)
    print("  用户网络探测模拟测试")
    print("=" * 70)

    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
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
        conn.commit()
        conn.close()

        cqf = CdnQualityFilter(
            db_path=db_path,
            ddns_domain='zzpzgroup.com',
            expected_isp='电信',
        )

        # 模拟不同的用户网络状态
        scenarios = [
            {'desc': '优质网络',   'latency_ms': 50,  'packet_loss_rate': 0.0,  'expected_ok': True},
            {'desc': '良好网络',   'latency_ms': 80,  'packet_loss_rate': 0.02, 'expected_ok': True},
            {'desc': '临界网络',   'latency_ms': 99,  'packet_loss_rate': 0.04, 'expected_ok': True},
            {'desc': '延时超标',   'latency_ms': 101, 'packet_loss_rate': 0.02, 'expected_ok': False},
            {'desc': '丢包超标',   'latency_ms': 80,  'packet_loss_rate': 0.06, 'expected_ok': False},
            {'desc': '双超标',     'latency_ms': 150, 'packet_loss_rate': 0.10, 'expected_ok': False},
            {'desc': '严重劣化',   'latency_ms': 300, 'packet_loss_rate': 0.30, 'expected_ok': False},
        ]

        print(f"\n{'场景':<12} {'延时':>8} {'丢包率':>8} {'预期':>8} {'实际':>8} {'判定'}")
        print("-" * 60)

        all_passed = True
        for s in scenarios:
            # 模拟质量判断
            quality_ok = True
            if s['latency_ms'] > cqf._user_quality_config['latency_ms']:
                quality_ok = False
            if s['packet_loss_rate'] > cqf._user_quality_config['packet_loss_rate']:
                quality_ok = False

            actual = '达标' if quality_ok else '不达标'
            expected = '达标' if s['expected_ok'] else '不达标'
            is_correct = quality_ok == s['expected_ok']
            verdict = '✅' if is_correct else '❌'
            if not is_correct:
                all_passed = False

            print(f"{s['desc']:<12} {s['latency_ms']:>6.0f}ms {s['packet_loss_rate']*100:>5.0f}%  {expected:>8} {actual:>8} {verdict}")

        return all_passed

    finally:
        os.unlink(db_path)


def test_boundary_values():
    """边界值测试：精确验证100ms和20Mbps的边界"""
    print("\n" + "=" * 70)
    print("  边界值精确测试")
    print("  验证: 延时=100ms不淘汰, 延时=101ms淘汰")
    print("  验证: 速度=20Mbps不淘汰, 速度=19.9Mbps淘汰")
    print("=" * 70)

    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ip_performance (
                ip TEXT PRIMARY KEY,
                total_tests INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                consecutive_fails INTEGER DEFAULT 0,
                avg_latency REAL DEFAULT 0,
                min_latency REAL DEFAULT 0,
                max_latency REAL DEFAULT 0,
                last_test_time TEXT,
                last_success_time TEXT,
                first_seen TEXT,
                source TEXT DEFAULT 'local',
                speed_mbps REAL DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()

        cqf = CdnQualityFilter(db_path=db_path)

        # 延时边界测试
        print("\n--- 延时边界 (阈值=100ms) ---")
        latency_tests = [
            (99.9,  50, False, '延时99.9ms → 不淘汰'),
            (100.0, 50, False, '延时100.0ms → 不淘汰(等于阈值)'),
            (100.1, 50, True,  '延时100.1ms → 淘汰'),
            (101,   50, True,  '延时101ms → 淘汰'),
        ]

        all_passed = True
        for lat, speed, expect_reject, desc in latency_tests:
            # 手动插入数据
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ip_performance")
            cursor.execute("""
                INSERT INTO ip_performance
                (ip, total_tests, success_count, fail_count, consecutive_fails,
                 avg_latency, min_latency, max_latency, last_test_time,
                 last_success_time, first_seen, source, speed_mbps)
                VALUES ('1.2.3.4', 10, 10, 0, 0, ?, ?, ?, datetime('now'),
                        datetime('now'), datetime('now'), 'test', ?)
            """, (lat, lat * 0.8, lat * 1.2, speed))
            conn.commit()
            conn.close()

            rejected, reason = cqf.hard_reject('1.2.3.4')
            is_correct = rejected == expect_reject
            verdict = '✅' if is_correct else '❌'
            if not is_correct:
                all_passed = False
            actual = '淘汰' if rejected else '通过'
            print(f"  {desc} → 实际:{actual} {verdict} {f'({reason})' if reason else ''}")

        # 速度边界测试
        print("\n--- 速度边界 (阈值=20Mbps) ---")
        speed_tests = [
            (50, 20.0,  False, '速度20.0Mbps → 不淘汰(等于阈值)'),
            (50, 19.9,  True,  '速度19.9Mbps → 淘汰'),
            (50, 15,    True,  '速度15Mbps → 淘汰'),
            (50, 0,     False, '速度0(无数据) → 不淘汰'),
        ]

        for lat, speed, expect_reject, desc in speed_tests:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ip_performance")
            cursor.execute("""
                INSERT INTO ip_performance
                (ip, total_tests, success_count, fail_count, consecutive_fails,
                 avg_latency, min_latency, max_latency, last_test_time,
                 last_success_time, first_seen, source, speed_mbps)
                VALUES ('1.2.3.4', 10, 10, 0, 0, ?, ?, ?, datetime('now'),
                        datetime('now'), datetime('now'), 'test', ?)
            """, (lat, lat * 0.8, lat * 1.2, speed))
            conn.commit()
            conn.close()

            rejected, reason = cqf.hard_reject('1.2.3.4')
            is_correct = rejected == expect_reject
            verdict = '✅' if is_correct else '❌'
            if not is_correct:
                all_passed = False
            actual = '淘汰' if rejected else '通过'
            print(f"  {desc} → 实际:{actual} {verdict} {f'({reason})' if reason else ''}")

        return all_passed

    finally:
        os.unlink(db_path)


if __name__ == '__main__':
    print("\n" + "🔍 CDN硬淘汰阈值验证测试" + "\n")

    r1 = test_hard_reject()
    r2 = test_user_probe_simulation()
    r3 = test_boundary_values()

    print("\n" + "=" * 70)
    print("  最终结果")
    print("=" * 70)
    print(f"  硬淘汰逻辑测试: {'✅ 全部通过' if r1 else '❌ 存在失败'}")
    print(f"  用户探测模拟测试: {'✅ 全部通过' if r2 else '❌ 存在失败'}")
    print(f"  边界值精确测试:   {'✅ 全部通过' if r3 else '❌ 存在失败'}")

    if r1 and r2 and r3:
        print("\n  🎉 所有测试通过！硬淘汰阈值生效。")
        sys.exit(0)
    else:
        print("\n  ⚠️ 部分测试失败，请检查阈值逻辑。")
        sys.exit(1)
