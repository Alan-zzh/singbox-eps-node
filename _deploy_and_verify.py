#!/usr/bin/env python3
"""
部署修复后的 subscription_service.py 到三台服务器 + 验证
"""
import paramiko
import os
import sys
import yaml
import subprocess
import time

SERVERS = [
    {'host': '43.207.152.47', 'name': 'JP', 'password': 'sarEBA97@jh.dxclouds.com', 'cc': 'JP'},
    {'host': '13.212.37.11', 'name': 'SG', 'password': 'jbfCMP75@jh.dxclouds.com', 'cc': 'SG'},
    {'host': '43.249.174.222', 'name': 'HK', 'password': '2aKf9Xt!4U.gOywfci', 'cc': 'HK'},
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_DIR = '/opt/tokenpass/scripts'
MIHOMO_EXE = os.path.join(SCRIPT_DIR, 'mihomo-windows-amd64.exe')

def run_ssh_cmd(ssh, cmd, timeout=30):
    _, so, se = ssh.exec_command(cmd, timeout=timeout)
    out = so.read().decode('utf-8', errors='replace')
    err = se.read().decode('utf-8', errors='replace')
    return out, err

def main():
    all_ok = True
    
    for srv in SERVERS:
        print(f"\n{'='*70}")
        print(f"=== 部署到 {srv['name']} ({srv['host']}) ===")
        print(f"{'='*70}")
        
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        sftp = None
        try:
            ssh.connect(srv['host'], username='root', password=srv['password'], timeout=15)
            sftp = ssh.open_sftp()
            
            # 1. 上传 subscription_service.py
            local_file = os.path.join(SCRIPT_DIR, 'scripts', 'subscription_service.py')
            remote_file = f"{REMOTE_DIR}/subscription_service.py"
            print(f"[1/5] 上传 subscription_service.py -> {remote_file}")
            sftp.put(local_file, remote_file)
            
            # 2. 重启订阅服务
            print(f"[2/5] 重启 tokenpass 服务...")
            out, err = run_ssh_cmd(ssh, "systemctl restart tokenpass && sleep 2 && systemctl is-active tokenpass")
            print(f"  服务状态: {out.strip()} {err.strip()}")
            if 'active' not in out:
                print(f"  ❌ 服务启动失败!")
                all_ok = False
                continue
            
            # 3. 等待服务启动
            time.sleep(2)
            
            # 4. 拉取 Clash 订阅配置
            print(f"[3/5] 拉取 Clash 订阅配置...")
            cmd = f"curl -sk -A 'clash-verge/2.0' https://127.0.0.1:2087/clash/{srv['cc']}"
            out, err = run_ssh_cmd(ssh, cmd, timeout=15)
            if not out or len(out) < 100:
                print(f"  ❌ 订阅拉取失败! 响应长度: {len(out)}, err: {err}")
                all_ok = False
                continue
            
            # 保存到本地
            local_yaml = os.path.join(SCRIPT_DIR, f'_clash_{srv["name"]}_deployed.yaml')
            with open(local_yaml, 'w', encoding='utf-8') as f:
                f.write(out)
            print(f"  保存到: {local_yaml} (大小: {len(out)} bytes)")
            
            # 5. 用本地 mihomo 验证配置
            print(f"[4/5] 用 mihomo -t 验证配置...")
            result = subprocess.run(
                [MIHOMO_EXE, '-t', '-f', local_yaml],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=SCRIPT_DIR
            )
            print(f"  mihomo exit code: {result.returncode}")
            if result.returncode != 0:
                print(f"  ❌ mihomo 验证失败!")
                print(f"  stdout: {result.stdout[-500:]}")
                print(f"  stderr: {result.stderr[-500:]}")
                all_ok = False
                continue
            else:
                print(f"  ✅ mihomo 配置验证通过!")
            
            # 6. 检查节点数量和 anyTLS 字段
            print(f"[5/5] 检查节点列表...")
            try:
                config = yaml.safe_load(out)
                proxies = config.get('proxies', [])
                print(f"  节点总数: {len(proxies)}")
                found_anytls = False
                for i, p in enumerate(proxies):
                    ptype = p.get('type', 'unknown')
                    pname = p.get('name', f'proxy{i}')
                    has_port = 'port' in p
                    port_val = p.get('port', 'MISSING')
                    mark = '✅' if has_port else '❌'
                    if ptype == 'anytls':
                        found_anytls = True
                        anytls_ok = has_port and isinstance(port_val, int)
                        mark = '✅' if anytls_ok else '❌'
                    print(f"  {mark} [{i}] {pname:25s} type={ptype:10s} port={port_val}")
                if not found_anytls:
                    print(f"  ❌ 未找到 anyTLS 节点!")
                    all_ok = False
            except Exception as e:
                print(f"  YAML 解析失败: {e}")
                all_ok = False
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_ok = False
        finally:
            if sftp:
                sftp.close()
            ssh.close()
    
    print(f"\n{'='*70}")
    if all_ok:
        print(f"✅ 所有三台服务器部署+验证全部通过!")
    else:
        print(f"❌ 部分服务器验证失败，请检查上面的错误")
    print(f"{'='*70}")
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())
