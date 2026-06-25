# TUIC v5 替换 Hysteria2 设计方案

**状态**: 已完成(v4.12.0 已上线,见 CHANGELOG)
**创建**: 2026-06-10
**目标版本**: v4.12.0
**关联版本**: v4.11.2 → v4.12.0(次版本号,协议替换 + 删端口跳跃架构)
**归档说明**: 本计划已于 v4.12.0 执行完成,保留作为协议替换决策记录。如需查看当前 TUIC v5 实现细节,参考 scripts/config_generator.py 与 scripts/subscription_service.py。

---

## 1. 背景与目标

### 1.1 现状
当前项目 v4.11.2 部署了 7 个入站协议，包含 Hysteria2（QUIC/UDP）。HY2 配套机制：

- 监听 443 端口（与 VLESS-Reality 共用）
- 端口跳跃：21000-21200 → 443（iptables DNAT 200 条 UDP+TCP 规则）
- 客户端 Salamander 混淆规避 QUIC 特征
- HK 服务器已禁用（`ENABLE_HY2=false`，ISP 阻断 UDP）
- cert_manager.py 维护 `setup_hysteria2_port_hopping()` 函数

### 1.2 问题
- **HY2 实际不稳定**：晚高峰 UDP QoS、GFW 主动截断、长连接掉速
- **端口跳跃无意义**：客户端 `mport` 必须严格配齐 21000-21200 全部 201 个端口，少一个就连不上；真实使用无人维护
- **HY2 协议被识别**：握手指纹已被 GFW 部分识别
- **代码债务**：cert_manager.py 200 行 iptables 规则维护成本高，HK 例外逻辑污染

### 1.3 目标
1. 用 TUIC v5 完全替换 HY2，保持 7 协议数量不变
2. 彻底删除端口跳跃架构（iptables 大清理）
3. TUIC v5 走 TCP+UDP 双栈，UDP 被 QoS 时 TCP 兜底
4. HK 服务器也启用 TUIC（实测 ISP 阻断情况）
5. 端口随机生成（10000-65535），沿用 vless-grpc/trojan-tcp 模式

---

## 2. 架构设计

### 2.1 协议矩阵（替换后）

| # | 协议 | 网络 | 端口 | 类型 | 角色 |
|---|------|------|------|------|------|
| 1 | VLESS-Reality | TCP | 443（锁定） | 直连 | 主力 |
| 2 | VLESS-gRPC | TCP+UDP | 随机（.env） | 直连 | 备选 |
| 3 | Trojan-TCP | TCP+UDP | 随机（.env） | 直连 | 备选 |
| 4 | VLESS-WS | TCP | 8443 | CDN | CDN |
| 5 | VLESS-HTTPUpgrade | TCP | 2053 | CDN | CDN |
| 6 | Trojan-WS | TCP | 2083 | CDN | CDN |
| 7 | **TUIC v5** | **TCP+UDP** | **随机（.env）** | **直连** | **UDP 加速** |

> 删除 Hysteria2（HY2），协议数保持 7 个。

### 2.2 TUIC v5 配置规范

```json
{
  "type": "tuic",
  "tag": "tuic-in",
  "listen": "::",
  "listen_port": <TUIC_PORT>,
  "users": [
    {
      "name": "tuic-user",
      "uuid": "<TUIC_UUID>",
      "password": "<TUIC_PASSWORD>"
    }
  ],
  "congestion_control": "bbr",
  "alpn": ["h3"],
  "tls": {
    "enabled": true,
    "certificate_paths": ["<BASE_DIR>/cert/fullchain.pem"],
    "key_paths": ["<BASE_DIR>/cert/key.pem"]
  }
}
```

**关键参数决策：**

| 参数 | 值 | 原因 |
|------|----|------|
| `congestion_control` | `bbr` | sing-box TUIC 默认值，抗丢包能力强 |
| `alpn` | `["h3"]` | QUIC 强制要求 |
| `tcp_fast_open` | `true` | 沿用 v4.11.0 全协议规范 |
| TCP+UDP 双栈 | 同端口 | sing-box 原生支持，减少配置复杂度 |
| 证书 | 复用 `cert/fullchain.pem` | 已有 CF 15 年证书，避免重复签发 |
| `uuid` | 新生成，不复用 VLESS_UUID | TUIC 与 VLESS 协议栈独立 |
| `password` | 64 字符 hex（`openssl rand -hex 32`） | 独立密码，区别 HY2 旧密码 |

### 2.3 ENV 变量规范

`.env` 新增/替换：

```bash
# 旧（删除）
# HYSTERIA2_PASSWORD=...
# ENABLE_HY2=true|false

# 新
TUIC_PORT=45001                    # 10000-65535 随机生成，首次安装后写入
TUIC_UUID=<uuid4>                  # install.sh 自动生成
TUIC_PASSWORD=<64hex>              # install.sh 自动生成（openssl rand -hex 32）
ENABLE_TUIC=true                   # 三台服务器默认 true（HK 也启用，实测验证）
```

`.env.example` 同步更新（不含值，仅 KEY）。

### 2.4 防火墙规则（删除与新增）

**删除（每台 200 条规则）：**
```bash
# 旧 HY2 端口跳跃（必须清理，否则占满 nat 表）
iptables -t nat -D PREROUTING -p udp --dport 21000:21200 -j DNAT --to-destination :443
# × 200 条
```

**新增（每台 1 条，TCP+UDP 合并）：**
```bash
# TUIC v5 单端口双栈
iptables -A INPUT -p tcp --dport <TUIC_PORT> -j ACCEPT
iptables -A INPUT -p udp --dport <TUIC_PORT> -j ACCEPT
# iptables-save 持久化
```

---

## 3. 代码改动清单

### 3.1 `scripts/config.py`

| 行 | 改动 |
|----|------|
| L16 | `HYSTERIA2_PORT = 443` 注释改为 `TUIC_PORT` 注释 |
| L127 | `HYSTERIA2_PORT = 443` → 删除 |
| L129 后 | 新增 `TUIC_PORT = int(os.getenv('TUIC_PORT', '0')) or 50444`（默认 fallback） |
| L139 | `LOCKED_PORTS` 中 `HYSTERIA2_PORT` → `TUIC_PORT` |
| L148 | `HYSTERIA2_UDP_PORTS = list(range(21000, 21201))` → 删除 |
| L150-160 | HY2 规避配置注释块 → 删除（30 行历史教训信息归档到 AI_DEBUG_HISTORY） |
| L575 | `get_node_name('hysteria2': ...)` → `'tuic': f'{NODE_PREFIX}-TUIC v5'` |

### 3.2 `scripts/config_generator.py`

- 删除 `generate_hysteria2_inbound()` 函数
- 新增 `generate_tuic_inbound()` 函数（参考上方 JSON 模板）
- `inbounds` 列表中 `if ENABLE_TUIC` 条件包裹 tuic 入站
- 从 `config.py` 导入 `TUIC_PORT` / `TUIC_UUID` / `TUIC_PASSWORD` / `ENABLE_TUIC`

### 3.3 `scripts/subscription_service.py`

- 删除 hysteria2 Base64 URL 生成逻辑
- 删除 hysteria2 Clash proxy 生成逻辑
- 删除 hysteria2 Sing-box JSON outbound 生成逻辑
- 新增 tuic 对应三种输出（参考 vless-grpc 模板）
- `ENABLE_TUIC=false` 时不输出 tuic 节点
- 节点名称 `get_node_name('tuic')` 统一

### 3.4 `scripts/cert_manager.py`

- 删除整个 `setup_hysteria2_port_hopping()` 函数（约 50 行）
- 删除 `if __name__ == "__main__"` 中 `sys.argv[1] == "--setup-iptables"` 分支
- 文件头注释从 "证书管理+HY2端口跳跃" → "证书管理"
- 保留 `obtain_certificate` / `renew_cert` / `generate_self_signed_cert` 等核心证书逻辑

### 3.5 `install.sh`

| 阶段 | 改动 |
|------|------|
| 依赖安装 | 不变 |
| 随机端口生成 | 新增 `TUIC_PORT` 生成（`shuf -i 10000-65535 -n 1`），与 `VLESS_GRPC_PORT`/`TROJAN_TCP_PORT` 同流程 |
| .env 写入 | 替换 `HYSTERIA2_PASSWORD` → `TUIC_PASSWORD` / `TUIC_UUID` / `ENABLE_TUIC` |
| iptables 配置 | 删除 `setup_hysteria2_port_hopping` 调用，改为 `setup_tuic_firewall`（单 TCP+UDP 规则） |
| `start_services()` | **无条件** 重跑 `python3 scripts/config_generator.py`（v4.11.1 教训：触发器不能因 config.json 存在跳过） |
| `verify_installation()` | 新增验证 `TUIC_PORT` TCP+UDP 双协议监听（`ss -tulnp \| grep $TUIC_PORT`） |

### 3.6 `deploy.py`

- `SYNC_FILES` 列表加入 `scripts/config_generator.py`（v4.11.1 教训）
- 部署完成后自动执行：
  ```python
  run_remote(ssh, 'cd /root/singbox-eps-node && python3 scripts/config_generator.py')
  run_remote(ssh, 'systemctl restart singbox')
  ```

### 3.7 `.env.example`

```bash
# 旧（删除）
# HYSTERIA2_PASSWORD=
# ENABLE_HY2=true

# 新
TUIC_PORT=
TUIC_UUID=
TUIC_PASSWORD=
ENABLE_TUIC=true
```

### 3.8 三台服务器 `.env`

每台手动更新（或 install.sh 自动生成）：
- JP: `TUIC_PORT=xxxxx` + `TUIC_PASSWORD=<64hex>` + `ENABLE_TUIC=true`
- SG: 同上
- HK: 同上（也启用，**与现状 HY2=false 不同**）

---

## 4. 部署流程

```
本地开发机
   │
   ├─ 1. 改完 8 个文件，git commit + push
   │
   ├─ 2. SFTP 同步到 JP/SG/HK
   │     └─ deploy.py SYNC_FILES 列表覆盖所有改动文件
   │
   └─ 3. 每台跑 install.sh reset
         ├─ 删 200 条 HY2 iptables 规则（先 iptables-save 备份到 /tmp/）
         ├─ 加 1 条 TUIC TCP+UDP INPUT ACCEPT 规则
         ├─ .env 生成 TUIC_PORT / TUIC_UUID / TUIC_PASSWORD / ENABLE_TUIC
         ├─ python3 scripts/config_generator.py（无条件重跑）
         ├─ sing-box check（配置语法验证）
         └─ systemctl restart singbox

   └─ 4. 验证（三台各跑）
         ├─ ss -tulnp | grep <TUIC_PORT>  → TCP+UDP 都监听
         ├─ tail -100 logs/singbox.log | grep "inbound/tuic"  → 入站启动
         └─ tail -100 logs/subscription_service.log | grep "tuic"  → 订阅生成

   └─ 5. 客户端连通性测试
         └─ Clash Meta / sing-box 客户端配置 TUIC 节点，连 Google 测速
```

---

## 5. 风险与回滚

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| HK ISP 同时阻断 HY2 和 TUIC 的 UDP | 高 | HK 无 UDP 加速 | `ENABLE_TUIC=false` 一键回退到 6 协议 |
| TUIC TCP 模式在某些客户端兼容性差 | 中 | 部分客户端连不上 | Clash Meta / sing-box 1.8+ / NekoBox 都已支持 |
| sing-box 1.13.x TUIC bug | 低 | 配置生效但流量异常 | install.sh 同步升级到 1.15.0 |
| iptables 清理脚本误删正常规则 | 低 | 服务中断 | 清理前 `iptables-save > /tmp/iptables.bak.<timestamp>` 自动备份 + install.sh 失败即回滚 |
| 订阅服务端/客户端协议层不同步 | 中 | 订阅看到节点但连不上 | v4.11.1 教训：config_generator 与 subscription_service 必须同时部署 |

**回滚方案：**
```bash
# 单台回滚（保留 5 分钟内可恢复）
cd /root/singbox-eps-node
git checkout v4.11.2 -- scripts/ install.sh
python3 scripts/config_generator.py
systemctl restart singbox
iptables-restore < /tmp/iptables.bak.<timestamp>
```

---

## 6. 测试验证标准

### 6.1 服务端验证

| 项 | 命令 | 预期 |
|----|------|------|
| 端口监听 | `ss -tulnp \| grep $TUIC_PORT` | 同时出现 tcp 和 udp 两行 |
| 入站启动 | `journalctl -u singbox -n 50 \| grep tuic` | `[INFO] inbound/tuic accepted` |
| 订阅生成 | `curl https://<domain>:2087/sub/<TOKEN>` | Base64 解码后含 `tuic://` 节点 |
| Clash 节点 | `curl https://<domain>:2087/sub/<TOKEN>?type=clash` | 含 `- { name: "...-TUIC v5", type: tuic, ... }` |
| iptables 规则 | `iptables -L INPUT -n \| grep $TUIC_PORT` | 2 行（tcp + udp ACCEPT） |
| 无残留 HY2 规则 | `iptables-save \| grep 21000` | 空 |

### 6.2 客户端验证

| 客户端 | 测试动作 | 预期 |
|--------|---------|------|
| Clash Meta for Windows | 启用 TUIC 节点 → 访问 google.com | 200 OK，延迟 <200ms |
| sing-box 桌面端 | 配置 tuic outbound → 全局代理 | 连接成功 |
| NekoBox / Shadowrocket | 扫码导入 TUIC 节点 | 自动识别协议，连接成功 |

### 6.3 性能基准

- 单线程 TCP 上传：≥80Mbps（HK→广东电信）
- 单线程 UDP 上传：≥150Mbps（同上）
- 长连接稳定性：≥24h 不掉线（QUIC keepalive 持续）

---

## 7. 文档同步清单

| 文件 | 改动 | 时机 |
|------|------|------|
| `CHANGELOG.md` | 顶部加 v4.12.0 条目（4-6 行） | 实施完成 |
| `VERSION.md` | v4.11.2 → v4.12.0 | 实施完成 |
| `README.md` | 协议表 HY2 → TUIC v5 | 实施完成 |
| `project_snapshot.md` | 7 协议列表更新 + 删除"端口跳跃" | 实施完成 |
| `docs/technical/technical-doc.md` | HY2 章节替换为 TUIC v5 章节 | 实施完成 |
| `AI_DEBUG_HISTORY.md` | 新增 3 条病历 | 实施完成 |
| `docs/plans/2026-06-10-tuic-v5-replace-hy2-design.md` | 本文档 | ✅ 已创建 |

---

## 8. 实施顺序（高层级）

1. **本地代码改动**（8 个文件）
2. **本地语法验证**：`python3 -c "import scripts.config_generator"` 之类
3. **本地生成 dry-run**：`python3 scripts/config_generator.py --dry-run`（如有支持）
4. **Git commit + push**
5. **JP 服务器部署**（最熟的一台先验证）
6. **JP 实测通过 → SG 部署**
7. **SG 实测通过 → HK 部署**
8. **HK 实测**：若 UDP 被阻断 → `ENABLE_TUIC=false` 现场回退
9. **CHANGELOG / VERSION / snapshot 同步**
10. **AGENTS.md 禁忌条目**（如发现新踩坑点）

---

**审核人**: Alan
**下一步**: 等用户确认本文档 → 调用 writing-plans skill 出实施计划
