
import paramiko

servers = [
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
]

def run_command(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    output = stdout.read().decode('utf-8', errors='replace')
    error = stderr.read().decode('utf-8', errors='replace')
    return output, error

results = {}

for srv in servers:
    server_name = srv['name']
    print(f"\n{'='*60}")
    print(f"[{server_name}] 开始检查...")
    print(f"{'='*60}\n")
    
    server_result = {}
    
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        print("--- 1. 检查服务状态 ---")
        cmd1 = "systemctl is-active singbox singbox-sub singbox-cdn"
        out1, err1 = run_command(client, cmd1)
        print(out1)
        if err1:
            print("Error:", err1)
        server_result['service_status'] = out1
        
        print("\n--- 2. 检查最近关键日志 ---")
        cmd2 = 'journalctl -u singbox-cdn --since "10 min ago" --no-pager | grep -E "ICMP|电信API缓存|联通API缓存|移动API缓存|用户路径" | tail -20'
        out2, err2 = run_command(client, cmd2)
        print(out2)
        if err2:
            print("Error:", err2)
        server_result['logs'] = out2
        
        print("\n--- 3. 读取评分数据 ---")
        cmd3 = '''cd /root/singbox-eps-node/data && python3 << 'PYEOF'
import sqlite3
conn = sqlite3.connect('singbox.db')
c = conn.cursor()
c.execute("""
    SELECT ip, composite_score_v2, user_isp_match
    FROM ip_performance
    WHERE composite_score_v2 > 0
    ORDER BY composite_score_v2 DESC
    LIMIT 20
""")
top_rows = c.fetchall()
print("=== 评分前20名IP ===")
for row in top_rows:
    print(f"{row[0]:<20} score={row[1]:>5.1f} isp_match={row[2]:>5.1f}")
c.execute("SELECT count(DISTINCT ip) FROM ip_performance WHERE composite_score_v2 > 0")
count = c.fetchone()[0]
print(f"\\n=== 统计摘要 ===")
c.execute("SELECT MIN(composite_score_v2), MAX(composite_score_v2), AVG(composite_score_v2) FROM ip_performance WHERE composite_score_v2 > 0")
min_s, max_s, avg_s = c.fetchone()
c.execute("SELECT MIN(user_isp_match), MAX(user_isp_match), AVG(user_isp_match) FROM ip_performance WHERE user_isp_match > 0")
min_is, max_is, avg_is = c.fetchone()
print(f"IP数: {count}")
print(f"composite_score_v2: {min_s:.1f}-{max_s:.1f}, avg={avg_s:.1f}")
print(f"user_isp_match: {min_is:.1f}-{max_is:.1f}, avg={avg_is:.1f}")
c.execute("""
    SELECT ip, composite_score_v2, user_isp_match
    FROM ip_performance
    WHERE composite_score_v2 > 0
    ORDER BY composite_score_v2 DESC
""")
all_data = c.fetchall()
print("\\n=== isp_match分布 ===")
bins = {0.0:0, 50.0:0, 60.0:0, 80.0:0, 100.0:0}
for row in all_data:
    im = row[2]
    if im in bins:
        bins[im] += 1
    else:
        bins[0.0] += 1
print(bins)
conn.close()
PYEOF'''
        out3, err3 = run_command(client, cmd3)
        print(out3)
        if err3:
            print("Error:", err3)
        server_result['db_data'] = out3
        
        client.close()
        results[server_name] = server_result
        
    except Exception as e:
        print(f"[错误: {e}]")
        results[server_name] = {'error': str(e)}

print(f"\n{'='*60}")
print("检查完成！")
print(f"{'='*60}\n")

print("\n--- 完整结果摘要 ---")
for name, data in results.items():
    print(f"\n[{name}]")
    if 'error' in data:
        print(f"错误: {data['error']}")
    else:
        print("服务状态:")
        print(data['service_status'])

