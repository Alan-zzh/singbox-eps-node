#!/usr/bin/env python3
"""Setup Cloudflare DNS for hkcepin.290372913.xyz"""
import json, urllib.request

ZONE_ID = "806b3853607b06c33f5951fce5e730ec"
API_EMAIL = "puzangroup@gmail.com"
API_KEY = "73a1fd81dd0f5087d45572135d5bf783ab26a"
SERVER_IP = "18.166.210.81"
DOMAIN = "hkcepin.290372913.xyz"
SUB_DOMAIN = "sub-hkcepin.290372913.xyz"

def cf_api(method, path, data=None):
    url = f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/{path}"
    headers = {
        "X-Auth-Email": API_EMAIL,
        "X-Auth-Key": API_KEY,
        "Content-Type": "application/json"
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())

# Check existing records
print("=== Checking existing DNS records ===")
result = cf_api("GET", f"dns_records?name={DOMAIN}")
for r in result.get("result", []):
    print(f"  {r['name']} -> {r['content']} (proxied: {r['proxied']})")

result = cf_api("GET", f"dns_records?name={SUB_DOMAIN}")
if result.get("result"):
    for r in result["result"]:
        print(f"  {r['name']} -> {r['content']} (proxied: {r['proxied']})")
else:
    print(f"  {SUB_DOMAIN} not found, creating...")
    result = cf_api("POST", "dns_records", {
        "type": "A",
        "name": "sub-hkcepin",
        "content": SERVER_IP,
        "ttl": 120,
        "proxied": False
    })
    if result.get("success"):
        r = result["result"]
        print(f"  CREATED: {r['name']} -> {r['content']} (proxied: {r['proxied']})")
    else:
        print(f"  FAILED: {result.get('errors')}")

print("=== DNS setup complete ===")
