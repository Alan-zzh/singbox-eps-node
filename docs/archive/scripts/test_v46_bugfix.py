#!/usr/bin/env python3
"""v4.6 BUG修复验证"""
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
        print('  PASS: ' + name + ' ' + str(detail))
    else:
        failed += 1
        print('  FAIL: ' + name + ' ' + str(detail))

print('[直连软淘汰兜底]')
dqf = DirectNodeQualityFilter()
nodes = [{'ip': '1.1.1.1', 'port': 443}, {'ip': '192.0.2.1', 'port': 443}]
r = dqf.filter_and_rank(nodes)
# 当前VPS隔离网络，两节点都被硬淘汰 → 软淘汰兜底保留（降权30%）
check('2节点时全部保留', len(r) == 2, '保留' + str(len(r)) + '个')
check('两个都被软淘汰', all(n[2] for n in r), '2个degraded=' + str([n[2] for n in r]))
check('评分被降权', r[0][1] < 50, 'score=' + str(r[0][1]))

print()
print('[select_best扩展字段]')
best = dqf.select_best(nodes)
check('best不为空', best is not None)
check('有degraded字段', 'degraded' in best)
check('有score字段', 'score' in best)
check('degraded=True(网络隔离)', best['degraded'] == True, 'degraded=' + str(best['degraded']))
print('  INFO: degraded=' + str(best['degraded']) + ' score=' + str(best['score']))

print()
print('[CDN回退机制]')
ctrl = CdnFailoverController(recovery_check_interval_sec=5)
ctrl.degrade_to_direct(['1.1.1.1', '8.8.8.8', '4.4.4.4'])
check('cdn_recovering=True', ctrl._cdn_recovering == True)
check('备份3个IP', len(ctrl._cdn_pool_backup) == 3)

result = ctrl.decide_cdn_recover(direct_mode_tag='direct')
check('返回recover字段', 'recover' in result)
check('返回still_degraded', 'still_degraded' in result)
check('CDN未恢复', result['recover'] == False)
check('仍降级', result['still_degraded'] == True)

print()
print('[手动触发CDN恢复]')
ctrl.manual_recover_cdn()
result2 = ctrl.decide_cdn_recover()
check('CDN IP仍未恢复', result2['recover'] == False)

print()
print('Result: ' + str(passed) + ' PASS, ' + str(failed) + ' FAIL')
sys.exit(0 if failed == 0 else 1)
