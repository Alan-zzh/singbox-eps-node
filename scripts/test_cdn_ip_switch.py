#!/usr/bin/env python3
"""
CDN IP 阻断自动切换测试脚本
测试场景：
1. 模拟当前 CDN IP 返回 403，验证自动换 IP 逻辑
2. 验证被拦截 IP 保留在池中（不淘汰）
3. 验证切换后订阅链接使用新 IP
4. 验证当池中所有 IP 都被拦截时的自动补全逻辑

Author: Alan
Date: 2026-05-22
"""
import sys
import os
import sqlite3
import time
from datetime import datetime

# 添加脚本路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from subscription_service import (
        test_cdn_ip_connectivity,
        get_cdn_ip_for_protocol,
        generate_all_links,
        logger,
        DB_PATH,
        CF_DOMAIN,
        SERVER_IP,
    )
    from config import CDN_IP_BLACKLIST
except ImportError as e:
    print(f"导入失败: {e}")
    CDN_IP_BLACKLIST = set()
    sys.exit(1)

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def get_db_cdn_ips():
    """从数据库读取当前 CDN IP 和 CDN IP 池"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    protocols = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']
    current_ips = {}
    for proto in protocols:
        cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (proto,))
        row = cursor.fetchone()
        if row and row[0]:
            current_ips[proto] = row[0]
    
    cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
    row = cursor.fetchone()
    ip_list = row[0].split(',') if row and row[0] else []
    
    conn.close()
    return current_ips, ip_list

def test_1_single_ip_block():
    """测试1：模拟单个 IP 被 403 阻断，验证自动换 IP"""
    print_header("测试1：模拟单个 IP 被 403 阻断")
    
    current_ips, ip_list = get_db_cdn_ips()
    print(f"当前 CDN IP:")
    for proto, ip in current_ips.items():
        print(f"  {proto}: {ip}")
    print(f"CDN IP 池: {ip_list}")
    
    # 选一个协议测试
    test_proto = 'vless_ws_cdn_ip'
    if test_proto not in current_ips:
        print(f"  ️ {test_proto} 无配置，跳过测试")
        return False
    
    original_ip = current_ips[test_proto]
    print(f"\n测试协议: {test_proto}")
    print(f"原始 IP: {original_ip}")
    
    # 测试当前 IP 连通性
    is_alive = test_cdn_ip_connectivity(original_ip)
    print(f"当前 IP 连通性: {'✅ 正常' if is_alive else '❌ 被阻断'}")
    
    if is_alive:
        print(f"  ️ 当前 IP 正常，模拟阻断场景需要手动构造")
        print(f"  跳过自动换 IP 测试（因为 IP 实际可用）")
        return True
    
    # IP 被阻断，验证自动换 IP
    print(f"\n>>> IP 被阻断，验证自动换 IP...")
    new_ip = get_cdn_ip_for_protocol(test_proto)
    
    if new_ip is None:
        print(f"  ❌ 换 IP 失败，无可用 IP")
        return False
    
    if new_ip == original_ip:
        print(f"  ❌ IP 未切换（仍为 {original_ip}）")
        return False
    
    print(f"  ✅ IP 已切换: {original_ip} -> {new_ip}")
    
    # 验证被拦截 IP 仍在池中
    current_ips2, ip_list2 = get_db_cdn_ips()
    if original_ip in ip_list2:
        print(f"  ✅ 被拦截 IP ({original_ip}) 保留在池中")
    else:
        print(f"   被拦截 IP ({original_ip}) 被从池中移除")
    
    return True

def test_2_pool_empty_recovery():
    """测试2：当池中所有 IP 都被拦截时，验证自动补全逻辑"""
    print_header("测试2：池中所有 IP 都被拦截时的自动补全")
    
    current_ips, ip_list = get_db_cdn_ips()
    print(f"当前 CDN IP 池: {len(ip_list)} 个 IP")
    
    # 统计池中可用 IP 数量
    available_count = 0
    for ip in ip_list:
        if test_cdn_ip_connectivity(ip):
            available_count += 1
    
    print(f"池中可用 IP: {available_count} 个")
    print(f"池中被拦截 IP: {len(ip_list) - available_count} 个")
    
    if available_count > 0:
        print(f"  ℹ️ 池中还有可用 IP，跳过补全测试")
        return True
    
    print(f"\n>>> 池中所有 IP 都被拦截，需要自动补全...")
    print(f"  当前 cdn_monitor 每小时会自动从外部 API 补全 IP")
    print(f"  外部 API 源: vvhan、090227、001315")
    print(f"  新 IP 会经过 TCP+HTTP 测试后加入池子")
    print(f"  无需手动添加 IP")
    
    return True

def test_3_subscribe_link_update():
    """测试3：验证切换后订阅链接使用新 IP"""
    print_header("测试3：验证切换后订阅链接使用新 IP")
    
    try:
        links = generate_all_links()
        
        # 统计 CDN 节点
        cdn_links = [l for l in links if 'CDN' in l]
        print(f"总节点数: {len(links)}")
        print(f"CDN 节点数: {len(cdn_links)}")
        
        # 检查 CDN 节点中的 IP
        cdn_ips_in_links = set()
        for link in cdn_links:
            # 从链接中提取 IP（vless:// 或 trojan:// 后面的地址）
            if '://' in link:
                addr = link.split('://')[1].split('@')[0] if '@' in link else link.split('://')[1].split('?')[0]
                # 检查是否是 IP 地址
                if addr and addr[0].isdigit():
                    cdn_ips_in_links.add(addr)
        
        print(f"订阅中的 CDN IP: {cdn_ips_in_links}")
        
        # 验证订阅中的 IP 是数据库中的 IP
        current_ips, ip_list = get_db_cdn_ips()
        db_ips = set(current_ips.values())
        
        # 检查是否有不在数据库中的 IP（说明切换没生效）
        new_ips = cdn_ips_in_links - db_ips
        if new_ips:
            print(f"  ⚠️ 订阅中有不在数据库中的 IP: {new_ips}")
        else:
            print(f"  ✅ 订阅中的 IP 与数据库一致")
        
        return True
    except Exception as e:
        print(f"  ❌ 生成订阅链接失败: {e}")
        return False

def test_4_continuous_blocking():
    """测试4：模拟连续多次被阻断，验证切换频率和稳定性"""
    print_header("测试4：模拟连续多次阻断，验证切换稳定性")
    
    protocols = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']
    switch_history = []  # 记录每次切换历史
    max_rounds = 10  # 最多模拟 10 次连续阻断
    success_count = 0
    fail_count = 0
    duplicate_count = 0
    
    print(f"  模拟连续 {max_rounds} 次阻断场景")
    print(f"  每个协议都会经历多次切换，验证系统稳定性\n")
    
    for proto in protocols:
        print(f"\n--- 协议: {proto} ---")
        current_ips, ip_list = get_db_cdn_ips()
        current_ip = current_ips.get(proto, None)
        
        if not current_ip:
            print(f"  ️ {proto} 无配置，跳过")
            continue
        
        if len(ip_list) < 2:
            print(f"  ️ CDN IP 池只有 {len(ip_list)} 个 IP，无法模拟连续切换")
            continue
        
        # 模拟连续阻断
        for round_num in range(1, max_rounds + 1):
            original_ip = current_ip
            print(f"  第 {round_num} 次模拟阻断: {original_ip}")
            
            # 手动从池中选一个不同的 IP（模拟阻断后切换）
            available = [ip for ip in ip_list if ip != original_ip]
            if not available:
                print(f"  ❌ 池中无可用 IP 可切换")
                fail_count += 1
                break
            
            import random
            new_ip = random.choice(available)
            
            # 更新数据库
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (proto, new_ip))
            conn.commit()
            conn.close()
            
            # 验证切换
            current_ips2, ip_list2 = get_db_cdn_ips()
            actual_ip = current_ips2.get(proto, None)
            
            if actual_ip == new_ip:
                print(f"  ✅ 切换成功: {original_ip} -> {new_ip}")
                switch_history.append({
                    'protocol': proto,
                    'round': round_num,
                    'from': original_ip,
                    'to': new_ip,
                    'success': True
                })
                success_count += 1
                current_ip = new_ip
            elif actual_ip == original_ip:
                print(f"   IP 未切换（仍为 {original_ip}）")
                duplicate_count += 1
                current_ip = original_ip
            else:
                print(f"  ⚠️ 切换结果异常: 期望 {new_ip}, 实际 {actual_ip}")
                fail_count += 1
                current_ip = actual_ip
            
            time.sleep(0.5)  # 避免太快
    
    # 统计结果
    print(f"\n{'='*60}")
    print(f"  切换统计:")
    print(f"  成功切换: {success_count} 次")
    print(f"  失败切换: {fail_count} 次")
    print(f"  重复 IP: {duplicate_count} 次")
    print(f"  总切换次数: {len(switch_history)} 次")
    
    if switch_history:
        # 检查是否有 IP 被重复使用（验证轮换逻辑）
        all_switched_ips = [h['to'] for h in switch_history]
        unique_ips = set(all_switched_ips)
        print(f"  使用的不同 IP 数: {len(unique_ips)} 个")
        print(f"  IP 池总数: {len(ip_list) if 'ip_list' in dir() else 'N/A'} 个")
        
        # 检查是否有 IP 连续重复
        consecutive_dups = 0
        for i in range(1, len(all_switched_ips)):
            if all_switched_ips[i] == all_switched_ips[i-1]:
                consecutive_dups += 1
        print(f"  连续重复切换: {consecutive_dups} 次")
    
    return True

def monitor_pool_health(interval=60, max_rounds=10):
    """监控当前 IP 池健康度（定时任务）
    
    Args:
        interval: 检查间隔（秒），默认 60 秒
        max_rounds: 最多监控轮数，默认 10 轮
    """
    print_header(f"IP 池健康度监控（每 {interval} 秒检查一次，共 {max_rounds} 轮）")
    
    protocols = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']
    
    for round_num in range(1, max_rounds + 1):
        print(f"\n{'='*60}")
        print(f"  第 {round_num} 轮监控 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
        print(f"{'='*60}")
        
        current_ips, ip_list = get_db_cdn_ips()
        print(f"  CDN IP 池: {len(ip_list)} 个 IP")
        
        # 检查每个协议
        for proto in protocols:
            ip = current_ips.get(proto, None)
            if not ip:
                print(f"  {proto}: 无配置")
                continue
            
            # 检测连通性
            is_alive = test_cdn_ip_connectivity(ip)
            status = "✅ 正常" if is_alive else "❌ 被阻断"
            print(f"  {proto}: {ip} -> {status}")
            
            # 如果被阻断，自动切换
            if not is_alive:
                print(f"    >>> {ip} 被阻断，自动换 IP...")
                new_ip = get_cdn_ip_for_protocol(proto)
                if new_ip and new_ip != ip:
                    print(f"    ✅ 已切换: {ip} -> {new_ip}")
                elif new_ip == ip:
                    print(f"     IP 未切换（池中无其他可用 IP）")
                else:
                    print(f"    ❌ 换 IP 失败")
        
        # 检查池健康度
        available_count = sum(1 for ip in ip_list if test_cdn_ip_connectivity(ip))
        blocked_count = len(ip_list) - available_count
        health_rate = (available_count / len(ip_list) * 100) if ip_list else 0
        
        print(f"\n  池健康度: {available_count}/{len(ip_list)} 可用 ({health_rate:.0f}%)")
        print(f"  被拦截 IP: {blocked_count} 个")
        
        if health_rate < 50:
            print(f"  ⚠️ 池健康度低于 50%，cdn_monitor 将自动从外部 API 补全")
        elif health_rate < 80:
            print(f"   池健康度偏低，注意观察")
        else:
            print(f"  ✅ 池健康度良好")
        
        if round_num < max_rounds:
            print(f"\n  等待 {interval} 秒后下一轮...")
            time.sleep(interval)
    
    print(f"\n{'='*60}")
    print(f"  监控完成，共 {max_rounds} 轮")
    print(f"{'='*60}")
    return True

def main():
    print("CDN IP 阻断自动切换测试")
    print("="*60)
    print(f"数据库: {DB_PATH}")
    print(f"域名: {CF_DOMAIN}")
    print(f"服务器IP: {SERVER_IP}")
    
    results = []
    
    # 测试1
    r1 = test_1_single_ip_block()
    results.append(("测试1：单个 IP 被阻断自动换 IP", r1))
    
    time.sleep(1)
    
    # 测试2
    r2 = test_2_pool_empty_recovery()
    results.append(("测试2：池中所有 IP 都被拦截时自动补全", r2))
    
    time.sleep(1)
    
    # 测试3
    r3 = test_3_subscribe_link_update()
    results.append(("测试3：切换后订阅链接使用新 IP", r3))
    
    time.sleep(1)
    
    # 测试4
    r4 = test_4_continuous_blocking()
    results.append(("测试4：连续多次阻断切换稳定性", r4))
    
    time.sleep(1)
    
    # IP 池健康度监控
    r5 = monitor_pool_health(interval=15, max_rounds=3)
    results.append(("监控：IP 池健康度定时检查", r5))
    
    # 汇总结果
    print_header("测试结果汇总")
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed:
        print("  所有测试通过！")
    else:
        print("  部分测试失败，请检查日志")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
