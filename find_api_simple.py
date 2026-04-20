#!/usr/bin/env python3
"""
Find the real API by analyzing the page source more carefully
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

print("=== Find Real API by Analyzing Page Source ===")

# 1. Get full page source and save to file
print("\n[1] Get full page source")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' > /tmp/page.html && wc -c /tmp/page.html")
print(out)

# 2. Look for all script tags
print("\n[2] All script tags")
code, out, err = run("grep -i '<script' /tmp/page.html")
print(out[:2000])

# 3. Look for any fetch/XHR calls in the page
print("\n[3] Look for fetch/XHR calls")
code, out, err = run("grep -iE 'fetch\\(|axios\\.|\\$\\.ajax|\\$\\.get|\\$\\.post|XMLHttpRequest' /tmp/page.html | head -20")
print(out[:1000])

# 4. Look for any API URLs in the page
print("\n[4] Look for API URLs")
code, out, err = run("grep -oP 'https?://[^\"\\s<>'\\)]+(?:api|data|json|php|ajax|cf|ip)[^\"\\s<>'\\)]*' /tmp/page.html | sort -u")
print(out[:1000])

# 5. Look for any data-loading functions
print("\n[5] Look for data-loading functions")
code, out, err = run("grep -iE 'function.*load|function.*get|function.*fetch|function.*init' /tmp/page.html | head -20")
print(out[:1000])

# 6. Look for any table-related JS
print("\n[6] Look for table-related JS")
code, out, err = run("grep -iE 'table|tbody|render|draw|datatable' /tmp/page.html | head -20")
print(out[:1000])

# 7. Look for any JSON data embedded in the page
print("\n[7] Look for JSON data")
code, out, err = run("grep -oP '\\{[^{}]*\"[^\"]+\"[^{}]*\\}' /tmp/page.html | head -10")
print(out[:500])

# 8. Look for any data attributes
print("\n[8] Look for data attributes")
code, out, err = run("grep -oP 'data-[^=]+=[\"\\'][^\"\\']*[\"\\']' /tmp/page.html | head -20")
print(out[:500])

# 9. Look for any AJAX calls
print("\n[9] Look for AJAX calls")
code, out, err = run("grep -iE '\\.ajax\\(|\\.get\\(|\\.post\\(' /tmp/page.html | head -10")
print(out[:500])

# 10. Look for any URL patterns
print("\n[10] Look for URL patterns")
code, out, err = run("grep -oP '(?:url|src|href|action)=[\"\\'][^\"\\']*[\"\\']' /tmp/page.html | sort -u | head -30")
print(out[:1000])

ssh.close()
