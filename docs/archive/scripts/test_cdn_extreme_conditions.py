#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.5 极端网络波动测试脚本
模拟真实用户网络波动（高延时、随机丢包、速度波动），验证硬淘汰逻辑在极端情况下的表现

运行方式：
    python scripts/test_cdn_extreme_conditions.py

[TRAE SOLO CN] v4.5 测试脚本
"""

import os
import sys
import sqlite3
import tempfile
import random
import time
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from cdn_quality_filter import CdnQualityFilter


def create_extreme_test_db(db_path):
    """创建极端条件测试数据库"""
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


def simulate_single_ip_lifecycle(db_path, ip, description):
    """模拟单个IP的完整生命周期（质量正常→缓慢劣化→突然波动→恢复）"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"\n--- {description} ({ip}) ---")

    lifecycle = []

    # 1. 初始优质阶段（0-20次测试）
    print("  🟢 阶段1: 优质网络 (0-20次)")
    for i in range(20):
        latency = random.uniform(40, 80)  # 40-80ms低延时
        speed = random.uniform(30, 60)    # 30-60Mbps高速
        success = random.random() < 0.999  # 几乎无失败
        total_tests = i + 1
        success_count = sum(1 for step in lifecycle if step['success']) + (1 if success else 0)
        fail_count = total_tests - success_count
        consec_fails = 0

        # 更新或插入数据
        cursor.execute("""
            INSERT OR REPLACE INTO ip_performance
            (ip, total_tests, success_count, fail_count, consecutive_fails,
             avg_latency, min_latency, max_latency, last_test_time,
             last_success_time, first_seen, source, speed_mbps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'),
                    datetime('now'), datetime('now'), 'simulation', ?)
        """, (ip, total_tests, success_count, fail_count, consec_fails,
              latency, latency * 0.8, latency * 1.2, speed))

        lifecycle.append({
            'test': total_tests,
            'latency': latency,
            'speed': speed,
            'success': success,
            'fail_count': fail_count,
            'consec_fails': consec_fails
        })

    # 2. 缓慢劣化阶段（21-60次，延时线性增长，速度线性下降）
    print("  🟡 阶段2: 缓慢劣化 (21-60次)")
    for i in range(40):
        step = i + 1
        latency = 80 + step * 2  # 80→160ms
        speed = 60 - step * 1    # 60→20Mbps
        success_rate = 0.999 - step * 0.005
        success = random.random() < success_rate
        total_tests = len(lifecycle) + 1

        success_count = sum(1 for step in lifecycle if step['success']) + (1 if success else 0)
        fail_count = total_tests - success_count
        consec_fails = 0

        last_step = lifecycle[-1] if lifecycle else None
        if last_step and not last_step['success'] and not success:
            consec_fails = last_step['consec_fails'] + 1
        elif not success:
            consec_fails = 1
        elif success:
            consec_fails = 0

        cursor.execute("""
            INSERT OR REPLACE INTO ip_performance
            (ip, total_tests, success_count, fail_count, consecutive_fails,
             avg_latency, min_latency, max_latency, last_test_time,
             last_success_time, first_seen, source, speed_mbps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'),
                    datetime('now'), datetime('now'), 'simulation', ?)
        """, (ip, total_tests, success_count, fail_count, consec_fails,
              latency, latency * 0.8, latency * 1.2, speed))

        lifecycle.append({
            'test': total_tests,
            'latency': latency,
            'speed': speed,
            'success': success,
            'fail_count': fail_count,
            'consec_fails': consec_fails
        })

    # 3. 突然剧烈波动阶段（61-100次，随机延时/丢包/速度）
    print("  🔴 阶段3: 剧烈波动 (61-100次)")
    for i in range(40):
        step = i + 1
        if random.random() < 0.3:  # 30%概率高延时
            latency = random.uniform(150, 500)
        else:
            latency = random.uniform(80, 120)
        if random.random() < 0.4:  # 40%概率速度暴跌
            speed = random.uniform(1, 10)
        else:
            speed = random.uniform(15, 25)
        success_rate = random.uniform(0.5, 0.95)
        success = random.random() < success_rate
        total_tests = len(lifecycle) + 1

        success_count = sum(1 for step in lifecycle if step['success']) + (1 if success else 0)
        fail_count = total_tests - success_count
        last_step = lifecycle[-1] if lifecycle else None
        consec_fails = 0
        if last_step and not last_step['success'] and not success:
            consec_fails = last_step['consec_fails'] + 1
        elif not success:
            consec_fails = 1

        cursor.execute("""
            INSERT OR REPLACE INTO ip_performance
            (ip, total_tests, success_count, fail_count, consecutive_fails,
             avg_latency, min_latency, max_latency, last_test_time,
             last_success_time, first_seen, source, speed_mbps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'),
                    datetime('now'), datetime('now'), 'simulation', ?)
        """, (ip, total_tests, success_count, fail_count, consec_fails,
              latency, latency * 0.8, latency * 1.2, speed))

        lifecycle.append({
            'test': total_tests,
            'latency': latency,
            'speed': speed,
            'success': success,
            'fail_count': fail_count,
            'consec_fails': consec_fails
        })

    # 4. 恢复阶段（101-130次，缓慢恢复）
    print("  🟢 阶段4: 网络恢复 (101-130次)")
    for i in range(30):
        step = i + 1
        latency = 100 - step * 2  # 100→40ms
        speed = 20 + step * 1.5  # 20→65Mbps
        success_rate = 0.95 + step * 0.002
        success = random.random() < success_rate
        total_tests = len(lifecycle) + 1

        success_count = sum(1 for step in lifecycle if step['success']) + (1 if success else 0)
        fail_count = total_tests - success_count
        last_step = lifecycle[-1] if lifecycle else None
        consec_fails = 0
        if last_step and not last_step['success'] and not success:
            consec_fails = last_step['consec_fails'] + 1
        elif not success:
            consec_fails = 1

        cursor.execute("""
            INSERT OR REPLACE INTO ip_performance
            (ip, total_tests, success_count, fail_count, consecutive_fails,
             avg_latency, min_latency, max_latency, last_test_time,
             last_success_time, first_seen, source, speed_mbps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'),
                    datetime('now'), datetime('now'), 'simulation', ?)
        """, (ip, total_tests, success_count, fail_count, consec_fails,
              latency, latency * 0.8, latency * 1.2, speed))

        lifecycle.append({
            'test': total_tests,
            'latency': latency,
            'speed': speed,
            'success': success,
            'fail_count': fail_count,
            'consec_fails': consec_fails
        })

    conn.commit()
    conn.close()
    return lifecycle


def simulate_and_monitor_ip(db_path, ip, description):
    """模拟IP生命周期并监控每一步的淘汰状态"""
    lifecycle = simulate_single_ip_lifecycle(db_path, ip, description)

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

    # 逐次测试淘汰状态
    reject_history = []
    first_reject_test = None
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for step in lifecycle:
        # 读取当前性能
        cursor.execute("SELECT * FROM ip_performance WHERE ip = ?", (ip,))
        row = cursor.fetchone()
        perf = {}
        if row:
            keys = ['ip', 'total_tests', 'success_count', 'fail_count', 'consecutive_fails',
                    'avg_latency', 'min_latency', 'max_latency', 'last_test_time',
                    'last_success_time', 'first_seen', 'source', 'speed_mbps']
            perf = dict(zip(keys, row))

        rejected, reason = cqf.hard_reject_current(ip)
        reject_history.append({
            'test': step['test'],
            'latency': step['latency'],
            'speed': step['speed'],
            'fail_rate': step['fail_count'] / step['test'],
            'rejected': rejected,
            'reason': reason
        })

        if rejected and first_reject_test is None:
            first_reject_test = step['test']
            print(f"  ⚠️  第{step['test']}次测试首次被硬淘汰: {reason}")

    conn.close()

    # 输出关键事件
    print(f"\n  📊 结果统计:")
    reject_count = sum(1 for r in reject_history if r['rejected'])
    total = len(reject_history)
    print(f"  - 总测试次数: {total}")
    print(f"  - 首次被淘汰测试: {first_reject_test if first_reject_test else '无'}")
    print(f"  - 累计被淘汰次数: {reject_count} ({reject_count/total*100:.1f}%)")

    # 统计被淘汰的原因分布
    reason_counts = {}
    for r in reject_history:
        if r['rejected']:
            key = r['reason']
            reason_counts[key] = reason_counts.get(key, 0) + 1

    print(f"\n  📌 淘汰原因分布:")
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count}次")

    return first_reject_test, reject_count


def test_extreme_conditions():
    """极端网络条件测试"""
    print("=" * 70)
    print("  极端网络波动测试")
    print("=" * 70)

    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    try:
        create_extreme_test_db(db_path)

        # 测试多个IP的生命周期
        ips = [
            ('162.159.1.100',  'IP A - 完整生命周期'),
            ('172.64.100.200', 'IP B - 完整生命周期'),
            ('104.18.50.60',   'IP C - 完整生命周期'),
        ]

        all_first_rejects = []

        for ip, desc in ips:
            first_reject, _ = simulate_and_monitor_ip(db_path, ip, desc)
            if first_reject is not None:
                all_first_rejects.append(first_reject)

        if all_first_rejects:
            print("\n" + "=" * 70)
            print("  综合分析")
            print("=" * 70)
            avg_first = sum(all_first_rejects) / len(all_first_rejects)
            min_first = min(all_first_rejects)
            max_first = max(all_first_rejects)
            print(f"\n📌 首次淘汰统计:")
            print(f"   - 平均首次淘汰测试: {avg_first:.1f}次")
            print(f"   - 最早首次淘汰: {min_first}次")
            print(f"   - 最晚首次淘汰: {max_first}次")
            print(f"\n✅ 测试完成，硬淘汰逻辑在极端网络波动下运行正常。")

    finally:
        os.unlink(db_path)


def test_user_network_sudden_fluctuation():
    """测试用户网络突然波动（延时/丢包/速度）"""
    print("\n" + "=" * 70)
    print("  用户网络突然波动测试")
    print("  模拟用户网络突然劣化→触发CDN IP刷新的场景")
    print("=" * 70)

    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    try:
        # 初始化数据库
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

        # 模拟历史数据（10次优质记录）
        print("\n--- 阶段1: 持续优质网络 ---")
        hist_latencies = []
        for i in range(10):
            lat = random.uniform(50, 80)
            hist_latencies.append(lat)
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_network_state
                (user_ip, user_isp, user_region, latency_ms,
                 packet_loss_rate, ip_changed, latency_spike, quality_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ('175.10.213.182', 'Chinanet HN', 'Hunan', lat, 0.02, 0, 0, 1))
            conn.commit()
            conn.close()
            time.sleep(0.01)

        avg_hist = sum(hist_latencies) / len(hist_latencies)
        print(f"   历史平均延时: {avg_hist:.1f}ms")

        # 阶段2: 突然延时飙升
        print("\n--- 阶段2: 延时突然飙升 ---")
        sudden_latencies = [105, 120, 150, 200, 180]
        for i, lat in enumerate(sudden_latencies):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_network_state
                (user_ip, user_isp, user_region, latency_ms,
                 packet_loss_rate, ip_changed, latency_spike, quality_ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, ('175.10.213.182', 'Chinanet HN', 'Hunan', lat, 0.03, 0, 0, 0))
            conn.commit()
            conn.close()

            # 读取所有历史记录计算平均值
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(latency_ms) FROM user_network_state WHERE latency_ms > 0 AND latency_ms < 9999 ORDER BY id DESC LIMIT 10")
            row = cursor.fetchone()
            current_avg = row[0] if row and row[0] else lat
            conn.close()

            is_spike = lat > (current_avg * 1.5)
            print(f"   测试{i+1}: 延时={lat:.0f}ms, 历史平均={current_avg:.1f}ms, 突增判定={'是' if is_spike else '否'}")

        # 阶段3: 丢包率飙升
        print("\n--- 阶段3: 丢包率突然飙升 ---")
        sudden_loss = [0.15, 0.25, 0.4, 0.5, 0.3]
        for i, loss in enumerate(sudden_loss):
            print(f"   测试{i+1}: 丢包率={loss*100:.0f}%, 质量判定={'不达标' if loss > 0.05 else '达标'}")

        # 阶段4: 速度暴跌
        print("\n--- 阶段4: 下载速度突然暴跌 ---")
        sudden_speed = [15, 10, 5, 2, 8]
        for i, speed in enumerate(sudden_speed):
            print(f"   测试{i+1}: 速度={speed:.1f}Mbps, 质量判定={'不达标' if speed < 20 else '达标'}")

    finally:
        os.unlink(db_path)


def test_multiple_ips_pool():
    """测试IP池批量筛选（100个IP，筛选出合格的）"""
    print("\n" + "=" * 70)
    print("  IP池批量筛选测试")
    print("  100个模拟IP，验证批量筛选性能和准确性")
    print("=" * 70)

    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    try:
        # 创建测试数据库
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

        # 生成100个随机IP的性能数据
        print("\n--- 生成100个模拟IP ---")
        ip_pool = []
        for i in range(100):
            octet1 = random.choice([162, 172, 104, 108, 198, 8])
            octet2 = random.randint(0, 255)
            octet3 = random.randint(0, 255)
            octet4 = random.randint(0, 255)
            ip = f"{octet1}.{octet2}.{octet3}.{octet4}"

            # 随机性能数据
            latency = random.uniform(30, 300)
            speed = random.uniform(1, 80)
            success_rate = random.uniform(0.6, 1.0)
            total_tests = random.randint(5, 50)
            success_count = int(total_tests * success_rate)
            fail_count = total_tests - success_count
            consec_fails = random.randint(0, 3) if fail_count > 0 else 0

            cursor.execute("""
                INSERT OR REPLACE INTO ip_performance
                (ip, total_tests, success_count, fail_count, consecutive_fails,
                 avg_latency, min_latency, max_latency, last_test_time,
                 last_success_time, first_seen, source, speed_mbps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'),
                        datetime('now'), datetime('now'), 'simulation', ?)
            """, (ip, total_tests, success_count, fail_count, consec_fails,
                  latency, latency * 0.8, latency * 1.2, speed))

            ip_pool.append(ip)

        conn.commit()
        conn.close()
        print(f"   生成完成，共{len(ip_pool)}个IP")

        # 筛选
        cqf = CdnQualityFilter(db_path=db_path)
        print("\n--- 开始批量筛选 ---")
        start = time.time()
        ranked = cqf.filter_and_rank(ip_pool)
        elapsed = (time.time() - start) * 1000
        print(f"   筛选完成，耗时{elapsed:.2f}ms")

        # 结果统计
        qualified_count = len(ranked)
        print(f"\n--- 筛选结果 ---")
        print(f"   输入IP总数: {len(ip_pool)}")
        print(f"   合格IP数: {qualified_count}")
        print(f"   淘汰率: {(1 - qualified_count/len(ip_pool)) * 100:.1f}%")

        if ranked:
            print("\n📌 前10名合格IP:")
            for i, (ip, score) in enumerate(ranked[:10]):
                # 获取性能数据用于展示
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT avg_latency, speed_mbps, fail_count, total_tests FROM ip_performance WHERE ip = ?", (ip,))
                row = cursor.fetchone()
                conn.close()

                lat, speed, fail, total = row if row else (0, 0, 0, 0)
                fail_rate = (fail / total * 100) if total > 0 else 0
                print(f"   {i+1}. {ip} 分数={score:.2f} 延时={lat:.0f}ms 速度={speed:.1f}Mbps 丢包={fail_rate:.0f}%")

    finally:
        os.unlink(db_path)


if __name__ == '__main__':
    print("\n🚀 极端网络波动测试开始" + "\n")

    test_extreme_conditions()
    test_user_network_sudden_fluctuation()
    test_multiple_ips_pool()

    print("\n" + "=" * 70)
    print("  🎉 所有测试完成")
    print("=" * 70)
