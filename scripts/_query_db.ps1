Import-Module Posh-SSH

$servers = @(
    @{Name='JP'; IP='52.195.179.240'; Pass='je*pMaN8QNfCMK'},
    @{Name='SG'; IP='13.212.37.11'; Pass='jbfCMP75@jh.dxclouds.com'}
)

$queryScript = @"
import sqlite3
db = sqlite3.connect('data/singbox.db')
c = db.cursor()
c.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
row = c.fetchone()
if row:
    ips = [ip.strip() for ip in row[0].split(',') if ip.strip()]
    print(f'CDN_IPs ({len(ips)}):')
    for ip in ips:
        print(f'  {ip}')
else:
    print('No CDN IPs')
for key in ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']:
    c.execute(f"SELECT value FROM cdn_settings WHERE key='{key}'")
    row = c.fetchone()
    print(f'{key}: {row[0] if row else None}')
c.execute('SELECT ip, total_tests, success_count, fail_count, avg_latency, speed_mbps, source FROM ip_performance ORDER BY avg_latency ASC LIMIT 30')
rows = c.fetchall()
if rows:
    print(f'IP_Perf (top30 by latency):')
    for r in rows:
        spd = r[5] if r[5] else 0
        src = r[6] or ''
        print(f'  {r[0]:<20} t={r[1]:>3} ok={r[2]:>3} f={r[3]:>3} lat={r[4]:>7.1f}ms spd={spd:>7.1f}Mbps src={src}')
else:
    print('No IP perf data')
c.execute('SELECT key, value FROM cdn_settings')
rows = c.fetchall()
if rows:
    print('CDN_Settings:')
    for r in rows:
        val = r[1][:100] if r[1] and len(r[1])>100 else r[1]
        print(f'  {r[0]}: {val}')
db.close()
"@

# Write script to temp file
$tempFile = "$env:TEMP\_check_db.py"
$queryScript | Out-File -FilePath $tempFile -Encoding UTF8

foreach ($srv in $servers) {
    Write-Host "`n===== $($srv.Name) Server ====="
    try {
        $secPwd = ConvertTo-SecureString $srv.Pass -AsPlainText -Force
        $cred = New-Object System.Management.Automation.PSCredential('root', $secPwd)
        $session = New-SSHSession -ComputerName $srv.IP -Credential $cred -AcceptKey -Force -ErrorAction Stop

        # Upload query script via SFTP
        $sftp = New-SFTPSession -ComputerName $srv.IP -Credential $cred -AcceptKey -Force -ErrorAction Stop
        Set-SFTPItem -SessionId $sftp.SessionId -Path $tempFile -Destination "/tmp/" -ErrorAction Stop
        Remove-SFTPSession -SessionId $sftp.SessionId | Out-Null

        # Execute
        $result = Invoke-SSHCommand -SessionId $session.SessionId -Command "cd /root/singbox-eps-node && python3 /tmp/_check_db.py" -TimeOut 30
        Write-Host $result.Output
        if ($result.Error) { Write-Host "STDERR: $($result.Error)" }

        Remove-SSHSession -SessionId $session.SessionId | Out-Null
    } catch {
        Write-Host "Failed: $_"
    }
}
