import subprocess
import os

os.chdir(r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node')

# 检查git状态
result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
print("=== Git Status ===")
print(result.stdout)
if result.stderr:
    print(f"stderr: {result.stderr}")

# 检查是否有敏感信息
result = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True)
files = result.stdout.strip().split('\n') if result.stdout.strip() else []
print(f"\n=== Staged files ({len(files)}) ===")
for f in files:
    print(f"  {f}")

# 添加所有变更
subprocess.run(['git', 'add', '-A'], capture_output=True)

# 检查是否有敏感信息（密码/IP）
result = subprocess.run(['git', 'diff', '--cached'], capture_output=True, text=True)
diff = result.stdout
secrets_found = []
for line in diff.split('\n'):
    if any(x in line for x in ['oroVIG', '54.250.149', 'TG_BOT_TOKEN=', 'password = "', 'BOT_TOKEN = ']):
        secrets_found.append(line)

if secrets_found:
    print(f"\n⚠️  WARNING: Potential secrets in staged files:")
    for s in secrets_found:
        print(f"  {s.strip()}")
else:
    print("\n✅ No secrets found in staged files")

# 提交
result = subprocess.run(['git', 'diff', '--cached', '--stat'], capture_output=True, text=True)
print(f"\n=== Changes ===")
print(result.stdout)

result = subprocess.run(['git', 'commit', '-m', 'fix: 流量统计改为iptables内核级计数器，修复Clash API不返回流量问题\n\n- 移除无效的Clash API流量统计方案（/proxies端点无download/upload字段）\n- 新增iptables流量计数器统计sing-box各入站端口(443/8443/2053/2083)\n- setup_iptables_traffic_counters()启动时初始化计数器（幂等）\n- get_iptables_traffic_bytes()解析iptables输出提取bytes\n- check_and_reset_month()首次升级初始化iptables_baseline基准值\n- 移除config_generator.py中无用的experimental.clash_api配置\n- 更新project_snapshot.md/AI_DEBUG_HISTORY.md/TECHNICAL_DOC.md'], capture_output=True, text=True)
print(f"\n=== Commit ===")
print(result.stdout)
if result.returncode != 0:
    print(f"Error: {result.stderr}")

# Push
result = subprocess.run(['git', 'push'], capture_output=True, text=True)
print(f"\n=== Push ===")
print(result.stdout)
if result.returncode != 0 and 'Everything up-to-date' not in result.stderr:
    print(f"stderr: {result.stderr}")

print("\n=== DONE ===")
