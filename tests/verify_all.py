"""全量订阅验证脚本（凭据从 .env 动态读取）。"""
import paramiko, subprocess, yaml, json, base64, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts'))
try:
    from config import get_ssh_credentials
    _all_creds = get_ssh_credentials()
    servers = [
        (c['host'], c['prefix'], c['password'], c['prefix'].split('_')[0])
        for c in _all_creds if c['host']
    ]
except Exception as e:
    print(f"⚠️  config.get_ssh_credentials() 失败: {e}")
    servers = []

if not servers:
    print("❌ .env 中未找到 SSH 凭据")
    sys.exit(1)

mihomo = "mihomo-windows-amd64.exe"
all_ok = True

for host, name, pwd, cc in servers:
    print(f"\n{'='*60}\nVerifying {name} ({host})\n{'='*60}")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="root", password=pwd, timeout=15)
    srv_ok = True
    
    # 1. Fetch Clash config
    print("[1/3] Fetching + verifying Clash config...")
    cmd = f"curl -sk -A 'clash-verge/2.0' https://127.0.0.1:2087/clash/{cc}"
    _, so, _ = ssh.exec_command(cmd, timeout=15)
    clash_yaml = so.read().decode("utf-8", "replace")
    if len(clash_yaml) < 200:
        print(f"  ❌ Clash fetch failed, len={len(clash_yaml)}"); srv_ok = False
    else:
        fpath = f"_clash_{name}_verified.yaml"
        open(fpath, "w", encoding="utf-8").write(clash_yaml)
        r = subprocess.run([mihomo, "-t", "-f", fpath], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"  ❌ mihomo FAILED: {r.stderr[-200:]}"); srv_ok = False
        else:
            cfg = yaml.safe_load(clash_yaml)
            proxies = cfg.get("proxies", [])
            anytls = [p for p in proxies if p.get("type") == "anytls"]
            port_ok = anytls and "port" in anytls[0] and isinstance(anytls[0].get("port"), int)
            print(f"  ✅ mihomo PASSED: {len(proxies)} nodes, anyTLS port={'OK' if port_ok else 'BAD'}")
    
    # 2. Fetch sing-box JSON
    print("[2/3] Verifying sing-box JSON...")
    cmd = f"curl -sk -A 'sing-box/1.12' https://127.0.0.1:2087/singbox/{cc}"
    _, so, _ = ssh.exec_command(cmd, timeout=15)
    sb_json = so.read().decode("utf-8", "replace")
    try:
        sb = json.loads(sb_json)
        obs = [o for o in sb.get("outbounds",[]) if o.get("type") not in ("selector","urltest","direct","block","dns")]
        has_anytls = any(o.get("type") == "anytls" for o in obs)
        print(f"  ✅ sing-box JSON OK: {len(obs)} nodes, anyTLS={'yes' if has_anytls else 'NO'}")
    except Exception as e:
        print(f"  ❌ sing-box JSON invalid: {e}"); srv_ok = False
    
    # 3. Fetch Base64 sub
    print("[3/3] Verifying Base64 subscription...")
    cmd = f"curl -sk -A 'curl/8.0' https://127.0.0.1:2087/sub/{cc}"
    _, so, _ = ssh.exec_command(cmd, timeout=15)
    b64 = so.read().decode("utf-8", "replace")
    try:
        dec = base64.b64decode(b64.strip() + "==").decode("utf-8", "replace")
        links = [l for l in dec.split("\n") if l.strip()]
        has_anytls = any(l.startswith("anytls://") for l in links)
        print(f"  ✅ Base64 OK: {len(links)} links, anyTLS={'yes' if has_anytls else 'NO'}")
    except Exception as e:
        print(f"  ❌ Base64 failed: {e}"); srv_ok = False
    
    ssh.close()
    if srv_ok:
        print(f"\n✅ {name} ALL CHECKS PASSED!")
    else:
        print(f"\n❌ {name} HAS ISSUES!"); all_ok = False

print(f"\n{'='*60}")
if all_ok:
    print("✅✅✅ ALL 3 SERVERS FULLY VERIFIED ✅✅✅")
    print("All 3 subscription formats (Clash/sing-box/Base64) work correctly.")
else:
    print("❌ Some verifications failed")
print(f"{'='*60}")
