#!/usr/bin/env python3
"""
实时观察用户公网IP相关的 sing-box 异常日志。

用途：
  - 用户正在用 v2rayN / Clash 实测固定节点时，快速查看 JP/SG 是否出现
    EOF / timeout / reset / REALITY invalid connection 等异常
  - 避免每次都手工拼 journalctl

示例：
  python scripts/watch_user_disconnects.py --minutes 2 --interval 5
  python scripts/watch_user_disconnects.py --related-ip 1.2.3.4 --server jp
"""

import argparse
import os
import socket
import subprocess
import sys
import time

try:
    import paramiko
except ImportError:
    paramiko = None


# 从 .env 动态读取服务器列表
def _build_servers():
    """从 .env 读取所有 SSH 凭据构建服务器字典"""
    env = load_env()
    servers = {}
    for k, v in env.items():
        if k.endswith('_SSH_IP') and v:
            p = k.replace('_SSH_IP', '').lower()
            servers[p] = {
                "host": v,
                "label": p.upper(),
                "username": env.get(f'{p.upper()}_SSH_USER', 'root'),
                "password": env.get(f'{p.upper()}_SSH_PASS', ''),
            }
    return servers

SERVERS = _build_servers()

ERROR_PATTERN = "unexpected EOF|EOF|processed invalid connection|timeout|reset|fatal|panic"


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    values = {}
    if not os.path.exists(env_path):
        return values
    with open(env_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.split(" #", 1)[0].split("\t#", 1)[0].strip()
    return values


def resolve_related_ip(explicit_ip=""):
    if explicit_ip:
        return explicit_ip

    env = load_env()
    candidate = (
        env.get("USER_PUBLIC_IP")
        or env.get("USER_IP")
        or env.get("CLIENT_PUBLIC_IP")
        or env.get("RELATED_IP")
    )
    if candidate:
        return candidate

    ddns_domain = env.get("USER_DDNS_DOMAIN", "").strip()
    if not ddns_domain:
        return ""

    try:
        return socket.gethostbyname(ddns_domain)
    except OSError:
        return ""


def ssh_run(host, command, user="root", timeout=20):
    if paramiko is not None:
        server = next((item for item in SERVERS.values() if item["host"] == host), None)
        if server:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    host,
                    username=server.get("username", user),
                    password=server.get("password", ""),
                    timeout=min(timeout, 15),
                    allow_agent=False,
                    look_for_keys=False,
                )
                stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
                stdout.channel.recv_exit_status()
                return (
                    stdout.read().decode("utf-8", "replace").strip(),
                    stderr.read().decode("utf-8", "replace").strip(),
                    0,
                )
            except Exception:
                pass
            finally:
                client.close()

    cmd = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        f"ConnectTimeout={min(timeout, 10)}",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
        f"{user}@{host}",
        command,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as exc:
        return "", str(exc), -1


def fetch_window(host, related_ip, minutes, user):
    cmd = (
        f"journalctl -u singbox --since '{minutes} min ago' --no-pager "
        f"| grep -E '{ERROR_PATTERN}|{related_ip}' | tail -n 120"
    )
    out, err, rc = ssh_run(host, cmd, user=user)
    if rc != 0 and not out:
        return [], err
    lines = [line for line in out.splitlines() if line.strip()]
    return lines, ""


def main():
    parser = argparse.ArgumentParser(description="实时观察用户公网IP相关的 sing-box 异常日志")
    parser.add_argument("--server", choices=["jp", "sg", "all"], default="all")
    parser.add_argument("--related-ip", default="", help="手动指定用户公网IP")
    parser.add_argument("--minutes", type=int, default=2, help="每轮回看最近 N 分钟日志")
    parser.add_argument("--interval", type=int, default=5, help="轮询间隔秒数")
    parser.add_argument("--rounds", type=int, default=0, help="轮询次数，0 表示无限")
    parser.add_argument("--user", default="root", help="SSH 用户名")
    args = parser.parse_args()

    related_ip = resolve_related_ip(args.related_ip)
    if not related_ip:
        print("未能解析 related IP，请使用 --related-ip 手动指定", file=sys.stderr)
        sys.exit(1)

    targets = SERVERS.keys() if args.server == "all" else [args.server]
    print(f"watch related_ip={related_ip} servers={','.join(targets)} interval={args.interval}s")

    seen = set()
    round_index = 0
    while True:
        round_index += 1
        print(f"\n=== round {round_index} ===")
        for key in targets:
            info = SERVERS[key]
            lines, err = fetch_window(info["host"], related_ip, args.minutes, args.user)
            print(f"[{info['label']}]")
            if err:
                print(f"  ssh error: {err}")
                continue
            fresh = [line for line in lines if line not in seen]
            if not fresh:
                print("  no new matching lines")
                continue
            for line in fresh:
                print(" ", line)
                seen.add(line)

        if args.rounds and round_index >= args.rounds:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
