#!/usr/bin/env python3
"""
Test fetch IPs from uouin.com
"""
import requests
import re

url = 'https://api.uouin.com/cloudflare.html'
print(f">>> Fetching: {url}")
response = requests.get(url, timeout=15)
if response.status_code == 200:
    text = response.text
    ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
    ips = [ip for ip in ips if all(0 <= int(x) <= 255 for x in ip.split('.'))]
    unique_ips = list(dict.fromkeys(ips))
    print(f"\n[OK] Got {len(unique_ips)} unique IPs")
    print(f"\nTop 10 IPs:")
    for i, ip in enumerate(unique_ips[:10], 1):
        print(f"  {i}. {ip}")
else:
    print(f"[ERR] Status: {response.status_code}")
