#!/usr/bin/env python3
"""v4.6 全链路验证测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
os.chdir(os.path.dirname(__file__))

from cdn_quality_filter import CdnQualityFilter, CdnHealthMonitor, CdnFailoverController
from direct_quality_filter import DirectNodeQualityFilter

passed = 0
failed = 0

def check(name, ok, detail=''):
    global passed, failed
    if ok:
        passed += 1
        print(f'  PASS: {name} {detail}')
    else:
        failed += 1
        print(f'  FAIL: {name} {detail}')

print('=== v4.6 全链路验证 ===')
print()

# 1. 类加载
print('[模块加载]')
try:
    cqf = CdnQualityFilter()
    mon = CdnHealthMonitor()
    ctrl = CdnFailoverController()
    dqf = DirectNodeQualityFilter()
    check('CdnQualityFilter', True)
    check('CdnHealthMonitor', True)
    check('CdnFailoverController', True)
    check('DirectNodeQualityFilter', True)
except Exception as e:
    check('类加载', False, str(e))

# 2. 跨网评分
print()
print('[三网跨网评分]')
try:
    s1 = cqf.calculate_cross_isp_score('172.64.32.100')  # Mobile HK
    check('Mobile HK IP', s1 == 100, f'score={s1}')

    s2 = cqf.calculate_cross_isp_score('104.16.160.50')  # Telecom LA
    check('Telecom LA IP', s2 == 100, f'score={s2}')

    s3 = cqf.calculate_cross_isp_score('108.162.236.1')  # Unicom
    check('Unicom IP', s3 == 100, f'score={s3}')

    s4 = cqf.calculate_cross_isp_score('1.1.1.1')  # Telecom general + Mobile HK
    check('1.1.1.1 (both Telecom+Mobile)', s4 == 100, f'score={s4}')

    s5 = cqf.calculate_cross_isp_score('8.8.8.8')
    check('未知IP', s5 == 50, f'score={s5}')
except Exception as e:
    check('跨网评分', False, str(e))

# 3. 三网探测
print()
print('[三网综合探测]')
try:
    test_ips = ['172.64.32.100', '104.16.160.50', '108.162.236.1', '1.1.1.1', '8.8.8.8']
    r = cqf.probe_three_networks(test_ips)
    check('探测结果数', len(r['overall_best']) == 5, f'overall={len(r["overall_best"])}')
    check('电信最优', len(r['telecom_best']) > 0, f'{len(r["telecom_best"])} IPs')
    check('联通最优', len(r['unicom_best']) > 0, f'{len(r["unicom_best"])} IPs')
    check('移动最优', len(r['mobile_best']) > 0, f'{len(r["mobile_best"])} IPs')
except Exception as e:
    check('三网探测', False, str(e))

# 4. 健康监控
print()
print('[CDN健康监控]')
try:
    status = mon.check_ip('1.1.1.1')
    check('健康检查返回', 'healthy' in status, f'healthy={status["healthy"]}')
    check('延时字段', 'latency_ms' in status, f'latency={status["latency_ms"]}')
    check('丢包字段', 'packet_loss_rate' in status, f'loss={status["packet_loss_rate"]}')
    check('连续失败', 'consecutive_fails' in status, f'fails={status["consecutive_fails"]}')
except Exception as e:
    check('健康监控', False, str(e))

# 5. 故障切换
print()
print('[CDN故障切换]')
try:
    # 模拟当前IP故障，从池中选新IP
    dec = ctrl.decide_switch('1.2.3.4', ['1.1.1.1', '8.8.8.8', '4.4.4.4'])
    check('切换决策', dec['switch'] == True, f'reason={dec["reason"][:40]}')
    check('新IP非空', dec['new_ip'] is not None, f'new_ip={dec["new_ip"]}')
    check('未降级直连', not dec['degrade_direct'], f'degrade={dec["degrade_direct"]}')

    # 冷却池验证
    status = ctrl.get_status()
    check('冷却池有IP', len(status['cooldown_pool']) >= 1, f'{len(status["cooldown_pool"])} in cooldown')
    check('切换计数', status['switch_count'] == 1, f'count={status["switch_count"]}')
except Exception as e:
    check('故障切换', False, str(e))

# 6. 直连筛选
print()
print('[直连质量筛选]')
try:
    rr, reason = dqf.hard_reject('1.1.1.1', 443)
    check('直连硬淘汰', not rr, f'reason={reason}')

    # 模拟一个不存在的IP
    rr2, reason2 = dqf.hard_reject('192.0.2.1', 443)
    check('不存在IP淘汰', rr2 == True, f'reason={reason2}')

    probe = dqf.probe_node('1.1.1.1', 443, rounds=2)
    check('直连探测', probe['tcp_avg_ms'] is not None, f'tcp={probe["tcp_avg_ms"]}ms')
except Exception as e:
    check('直连筛选', False, str(e))

# 7. 评分权重验证
print()
print('[评分权重]')
try:
    weights = cqf.SCORE_WEIGHTS
    total_w = sum(weights.values())
    check('九维权重总和=1', abs(total_w - 1.0) < 0.01, f'sum={total_w:.2f}')
    check('cross_isp权重', 'cross_isp' in weights, f'weight={weights.get("cross_isp")}')
except Exception as e:
    check('评分权重', False, str(e))

print()
print(f'=== 结果: {passed} PASS, {failed} FAIL ===')
sys.exit(0 if failed == 0 else 1)