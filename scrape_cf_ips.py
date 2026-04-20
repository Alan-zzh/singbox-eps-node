#!/usr/bin/env python3
"""
Use headless browser to scrape ranked CF IPs from uouin.com
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

print("=== Scrape Ranked CF IPs with Headless Browser ===")

# 1. Install playwright
print("\n[1] Install playwright")
code, out, err = run("pip3 install playwright 2>&1 | tail -3")
print(out)

# 2. Install browser
print("\n[2] Install chromium browser")
code, out, err = run("python3 -m playwright install chromium 2>&1 | tail -5")
print(out)

# 3. Create scrape script
print("\n[3] Create scrape script")
scrape_script = '''
import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Capture network requests
        api_requests = []
        page.on("response", lambda resp: api_requests.append({
            "url": resp.url,
            "status": resp.status,
            "type": resp.request.resource_type
        }))
        
        print("Loading page...")
        await page.goto("https://api.uouin.com/cloudflare.html", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(5)
        
        print("\\n=== Network Requests ===")
        for r in api_requests:
            if any(kw in r["url"].lower() for kw in ["api", "cf", "ip", "data", "json", "ajax"]):
                print(f"  {r['status']} {r['type']} {r['url']}")
        
        # Try to get table data
        print("\\n=== Table Data ===")
        try:
            rows = await page.query_selector_all("table tbody tr")
            print(f"Found {len(rows)} rows")
            for i, row in enumerate(rows[:15]):
                cells = await row.query_selector_all("td")
                cell_texts = []
                for cell in cells:
                    text = await cell.inner_text()
                    cell_texts.append(text.strip())
                print(f"  Row {i+1}: {cell_texts}")
        except Exception as e:
            print(f"Table error: {e}")
        
        # Try to get IPs from the page
        print("\\n=== IPs from page ===")
        try:
            content = await page.content()
            import re
            ips = re.findall(r'\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b', content)
            unique_ips = list(dict.fromkeys(ips))
            print(f"Found {len(unique_ips)} unique IPs")
            for ip in unique_ips[:20]:
                print(f"  {ip}")
        except Exception as e:
            print(f"IP extraction error: {e}")
        
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
