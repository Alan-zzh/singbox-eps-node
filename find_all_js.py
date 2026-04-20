#!/usr/bin/env python3
"""
Find all JS in the page that loads data
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Find All JS in Page ===")

# 1. Get all script tags with src
print("\n[1] All script tags with src")
code, out, err = run("grep -oP '<script[^>]+src=[\"\\']([^\"\\']+)[\"\\'][^>]*>' /tmp/page.html")
print(out)

# 2. Get all inline script content
print("\n[2] All inline script content")
code, out, err = run("sed -n '/<script>/,/<\\/script>/p' /tmp/page.html | head -200")
print(out[:3000])

# 3. Look for any JS files referenced
print("\n[3] Look for JS files in the page")
code, out, err = run("grep -oP 'src=[\"\\']([^\"\\']+\\.js[^\"\\']*)[\"\\']' /tmp/page.html")
print(out)

# 4. Look for any data loading code
print("\n[4] Look for data loading code")
code, out, err = run("grep -iE 'load|fetch|get|ajax|table|render|draw|data|ip|cf|result' /tmp/page.html | grep -v '<!--' | head -30")
print(out[:2000])

# 5. Look for the actual table structure
print("\n[5] Table structure")
code, out, err = run("grep -A 50 '<table' /tmp/page.html | head -60")
print(out)

# 6. Look for any API calls
print("\n[6] API calls")
code, out, err = run("grep -iE '\\.get\\(|\\.post\\(|\\.ajax\\(|fetch\\(' /tmp/page.html")
print(out[:500])

# 7. Look for any URL patterns in JS
print("\n[7] URL patterns in JS")
code, out, err = run("grep -oP '(?:url|src|href|api|endpoint)\\s*[:=]\\s*[\"\\'][^\"\\']+[\"\\']' /tmp/page.html | head -20")
print(out)

# 8. Look for any variable assignments with URLs
print("\n[8] Variable assignments with URLs")
code, out, err = run("grep -oP 'var\\s+\\w+\\s*=\\s*[\"\\'][^\"\\']+[\"\\']' /tmp/page.html | head -20")
print(out)

ssh.close()
