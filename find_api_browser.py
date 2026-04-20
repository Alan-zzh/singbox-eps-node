#!/usr/bin/env python3
"""
Use headless browser to find the real API for ranked CF IPs
"""
import paramiko
import re

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Use Headless Browser to Find API ===")

# 1. Install playwright if not present
print("\n[1] Install playwright")
code, out, err = run("pip3 install playwright 2>&1 | tail -5")
print(out)

# 2. Install browser
print("\n[2] Install browser")
code, out, err = run("python3 -m playwright install chromium 2>&1 | tail -10")
print(out)

# 3. Create a script to capture network requests
print("\n[3] Create network capture script")
script = '''
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Capture all network requests
        requests = []
        page.on("request", lambda req: requests.append({"url": req.url, "method": req.method}))
        
        await page.goto("https://api.uouin.com/cloudflare.html", wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Print all requests
        print("=== All Network Requests ===")
        for r in requests:
            if "api" in r["url"].lower() or "cf" in r["url"].lower() or "ip" in r["url"].lower() or "data" in r["url"].lower():
                print(f"  {r['method']} {r['url']}")
        
        # Try to get the table data
        print("\\n=== Table Content ===")
        table = await page.query_selector("table")
        if table:
            rows = await table.query_selector_all("tr")
            for i, row in enumerate(rows[:15]):
                cells = await row.query_selector_all("td")
                cell_texts = [await cell.inner_text() for cell in cells]
                print(f"  Row {i}: {cell_texts}")
        
        await browser.close()

asyncio.run(main())
'''

# Write script to server
sftp = ssh.open_sftp()
sftp.put('/tmp/capture_api.py', script)
sftp.close()

# 4. Run the capture script
print("\n[4] Run capture script")
code, out, err = run("cd /tmp && python3 capture_api.py 2>&1", timeout=120)
print(out)
if err:
    print("STDERR:", err[:500])

ssh.close()
