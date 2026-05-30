Import-Module Posh-SSH

$servers = @(
    @{Name='JP'; IP='52.195.179.240'; Pass='je*pMaN8QNfCMK'},
    @{Name='SG'; IP='13.212.37.11'; Pass='jbfCMP75@jh.dxclouds.com'}
)

foreach ($srv in $servers) {
    Write-Host "`n===== $($srv.Name) Server ====="
    try {
        $secPwd = ConvertTo-SecureString $srv.Pass -AsPlainText -Force
        $cred = New-Object System.Management.Automation.PSCredential('root', $secPwd)
        $session = New-SSHSession -ComputerName $srv.IP -Credential $cred -AcceptKey -Force -ErrorAction Stop

        # Write script directly on remote server
        $writeScript = @"
cat > /tmp/_dbq.py << 'PYEOF'
import sqlite3
db = sqlite3.connect('data/singbox.db')
c = db.cursor()
preferred = ['8.39.125.221','8.39.125.101','8.39.125.36','162.159.109.77','162.159.45.121','162.159.45.4','172.64.53.146','172.64.48.95','172.64.146.161','172.64.32.185','108.162.198.57','104.18.32.206']
print('=== PREFERRED_IPS perf ===')
for ip in preferred:
    c.execute(f"SELECT ip, total_tests, success_count, fail_count, avg_latency, speed_mbps, source FROM ip_performance WHERE ip='{ip}'")
    row = c.fetchone()
    if row:
        print(f'  {row[0]:<20} t={row[1]:>3} ok={row[2]:>3} f={row[3]:>3} lat={row[4]:>7.1f}ms spd={row[5] if row[5] else 0:>7.1f}Mbps src={row[6] or ""}')
    else:
        print(f'  {ip:<20} NOT IN DB')
c.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
row = c.fetchone()
if row:
    print(f'=== Current CDN IPs full ===')
    ips = [ip.strip() for ip in row[0].split(',') if ip.strip()]
    for i, ip in enumerate(ips):
        c.execute(f"SELECT total_tests, success_count, avg_latency, speed_mbps, source FROM ip_performance WHERE ip='{ip}'")
        r = c.fetchone()
        if r:
            print(f'  {i+1}. {ip:<20} t={r[0]:>3} ok={r[1]:>3} lat={r[2]:>7.1f}ms spd={r[3] if r[3] else 0:>7.1f}Mbps src={r[4] or ""}')
        else:
            print(f'  {i+1}. {ip:<20} NOT IN DB')
c.execute("SELECT ip, total_tests, avg_latency, speed_mbps, source FROM ip_performance WHERE speed_mbps > 0 ORDER BY speed_mbps DESC LIMIT 20")
rows = c.fetchall()
if rows:
    print(f'=== IPs with speed data (Top20) ===')
    for r in rows:
        print(f'  {r[0]:<20} t={r[1]:>3} lat={r[2]:>7.1f}ms spd={r[3]:>7.1f}Mbps src={r[4] or ""}')
c.execute("SELECT ip, google_latency_ms, google_speed_mbps, user_isp_match, composite_score_v2 FROM ip_performance WHERE composite_score_v2 > 0 ORDER BY composite_score_v2 DESC LIMIT 15")
rows = c.fetchall()
if rows:
    print(f'=== v4.9 scores (Top15) ===')
    for r in rows:
        print(f'  {r[0]:<20} g_lat={r[1]:>7.1f} g_spd={r[2]:>7.1f} isp={r[3]:>5.1f} score={r[4]:>6.1f}')
db.close()
PYEOF
"@

        $r1 = Invoke-SSHCommand -SessionId $session.SessionId -Command $writeScript -TimeOut 10
        $result = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /root/singbox-eps-node && python3 /tmp/_dbq.py" -TimeOut 30
        Write-Host $result.Output
        if ($result.Error) { Write-Host "STDERR: $($result.Error)" }

        Remove-SSHSession -SessionId $session.SessionId | Out-Null
    } catch {
        Write-Host "Failed: $_"
    }
}
