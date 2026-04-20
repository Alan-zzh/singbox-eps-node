#!/usr/bin/env python3
"""从本地推送代码到GitHub"""
import subprocess
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
PROJECT_DIR = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node'
os.chdir(PROJECT_DIR)

def run(cmd, timeout=60):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=PROJECT_DIR, 
                          encoding='utf-8', errors='replace', timeout=timeout)
    return result.stdout.strip(), result.stderr.strip()

print('【1. 清理临时脚本】')
files_to_delete = [
    'check_db_paths.py', 'check_server.py', 'check_external_sub.py',
    'check_sub_access.py', 'check_sub_service.py', 'deploy_fix.py',
    'final_verify_report.py', 'fix_cdn_db.py', 'fix_https_sub.py',
    'quick_deploy.py', 'show_sub_links.py', 'test_sub.py',
    'verify_cdn_ips.py', 'verify_server_config.py'
]
for f in files_to_delete:
    path = os.path.join(PROJECT_DIR, f)
    if os.path.exists(path):
        os.remove(path)
        print(f'  已删除: {f}')

print('\n【2. 添加所有文件】')
out, err = run('git add -A')
print(f'  OK')

print('\n【3. 提交】')
out, err = run('git commit -m "v1.0.32: fix Hysteria2 port + CDN SNI + preferred IP pool"')
print(f'  {out if out else err}')

print('\n【4. 推送】')
out, err = run('git push origin main', timeout=120)
print(f'  {out if out else err}')

print('\n✅ 完成')
