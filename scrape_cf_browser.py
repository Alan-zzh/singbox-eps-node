#!/usr/bin/env python3
"""
Use headless browser to get fully rendered page with CF IPs
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Use Headless Browser to Get CF IPs ===")

# 1. Install playwright
print("\n[1] Install playwright")
code, out, err = run("pip3 install playwright 2>&1 | tail -3")
print(out)

# 2. Install browser
print("\n[2] Install chromium")
code, out, err = run("python3 -m playwright install chromium 2>&1 | tail -5")
print(out)

# 3. Create scrape script
print("\n[3] Create scrape script")
scrape_script = r'''
import asyncio
from playwright.async_api import async_playwright
import re

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("Loading page...")
        await page.goto("https://api.uouin.com/cloudflare.html", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(5)
        
        # Get rendered HTML
        content = await page.content()
        
        # Extract table rows
        rows = re.findall(r'<tr>.*?</tr>', content, re.DOTALL)
        print(f'Found {len(rows)} rows')
        
        # Extract data from each row
        ips_data = []
        for i, row in enumerate(rows):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            if len(cells) >= 3:
                ip = cells[2] if len(cells) > 2 else None
                if ip and re.match(r'\d+\.\d+\.\d+\.\d+', ip):
                    isp = cells[1] if len(cells) > 1 else ''
                    latency = cells[4] if len(cells) > 4 else ''
                    speed = cells[5] if len(cells) > 5 else ''
                    ips_data.append({
                        'rank': i + 1,
                        'isp': isp,
                        'ip': ip,
                        'latency': latency,
                        'speed': speed
                    })
                    print(f"  {i+1}. {ip} ({isp}) - {latency} - {speed}")
        
        print(f'\nTotal: {len(ips_data)} IPs')
        
        # Filter telecom IPs
        telecom_ips = [d for d in ips_data if '电信' in d['isp']]
        print(f'\nTelecom IPs: {len(telecom_ips)}')
        for d in telecom_ips[:15]:
            print(f"  {d['rank']}. {d['ip']} - {d['latency']} - {d['speed']}")
        
        # Get top 10 telecom IPs
        top10 = [d['ip'] for d in telecom_ips[:10]]
        print(f'\nTop 10 Telecom IPs:')
        for ip in top10:
            print(f"  '{ip}',")
        
        await browser.close()

asyncio.run(main())
'''

# Write to server
sftp = ssh.open_sftp()
sftp.put('/tmp/scrape_cf.py', scrape_script)
sftp.close()

# 4. Run scrape script
print("\n[4] Run scrape script")
code, out, err = run("cd /tmp && python3 scrape_cf.py 2>&1", timeout=120)
print(out)
if err and "Error" in err:
    print("STDERR:", err[:1000])

ssh.close()
