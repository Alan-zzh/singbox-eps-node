# AI 踩坑病历

> **只保留已确认的、对后续 AI 有直接指导意义的真实 bug 记录。**
> 过时/错误/重复的结论已清理，所有铁律请优先看 [AGENTS.md](AGENTS.md)。

---

## -8. direct 健康检查覆盖全域规则，导致 JP CDN 从 101 变 400（v4.15.28）

**现象**：部署香港备用直连机后，JP 订阅仍为 200 且输出 7 节点，但公网 `/api/v1/stream`、`/api/v1/data` 同时从 WebSocket 101 变成 HTTP 400；服务端监听与部署门禁仍显示通过。

**已确认根因**：`health_check.sh` 在 direct 与 CDN 模式下都无条件执行 `cloudflare_proxy_rules.py apply`；规则脚本又按当前服务器 `CF_DOMAIN` 动态生成全域唯一 skip/origin ruleset。HKBEIYONG 的定时健康检查因此把 JP 规则覆盖为 `hkbeiyong.*`。原部署门禁只检查 Token 格式、源站服务与订阅，不回读 Cloudflare rule owner，所以产生假绿。

**修复**：
- 立即将全域 skip/origin 规则恢复为 `jp.290372913.xyz`，两条公网 WS 路径恢复 101。
- `cloudflare_proxy_rules.py apply` 必须显式获得 `DEPLOY_MODE`；direct 模式在脚本内部 fail-safe 跳过，未知模式拒绝执行。
- direct 健康检查在调用 Cloudflare 脚本前再次跳过；安装器 CDN 分支显式传 `--mode/--domain/--zone`。
- 部署门禁新增 Cloudflare 受管规则完整语义（description/action/enabled/expression/action_parameters）、TLS 1.2 与 DDoS override API 回读；模式缺失或拼错也直接阻塞，避免服务/订阅正常但 CDN 边缘已坏仍显示通过。

**关键证据**：修复前定向 full audit 两条 WS 均为 400，Cloudflare API 回读 skip/origin expression 均指向 `hkbeiyong.*`；恢复后主动运行 HKBEIYONG、HK2 健康检查均记录“direct 模式不得修改”且 ruleset `last_updated` 未变化，JP full audit 两条 WS 均为 101；JP 新部署门禁 13/13 PASS；本地回归 `87 passed, 1 skipped`。

**教训**：Cloudflare phase ruleset 是 zone 级共享状态，不能让每台服务器按自身域名覆盖。CDN 验收必须同时包含 API rule owner 回读和外部 WebSocket 101，订阅 200、源站 active 不能代替。

## -7. 订阅 200 仍导入失败、AI SOCKS5 假容错与重装破坏现场（v4.15.26）

**现象**：HKBEIYONG 的 Clash 链接可返回 200，但旧代理失效时客户端更新请求也被旧代理接管而超时；sing-box JSON 能被 JSON 解析却无法被 1.13 内核加载；AI SOCKS5 配置声称会自动切换，实际代理认证已过期且 `selector` 不会自动容错；重复安装还可能先搬走工作目录、删除旧证书或清空宿主防火墙。

**已确认根因**：
- 订阅配置没有对自身域名区域设置 DIRECT，旧节点失效后形成“必须先连旧代理才能下载新代理”的启动死锁。
- sing-box 客户端订阅残留多个已移除字段：`urltest.timeout`、`rcode` DNS、DNS outbound、`inet4_address`、FakeIP 空地址；Reality outbound 把 `short_id` 错写成数组。
- AI 代理只做端口/Google 探测，认证代理同时 offered no-auth；把 401/429 混为可用；`selector` 被误认为会自动尝试下一个出站。
- 安装器在新版本完整验收前切换 live 目录，签证书前删除旧证书，并执行 `iptables -F`/修改默认策略。

**修复**：
- Clash/sing-box 订阅把当前 zone 的订阅流量置于兜底代理前直连；公网下载后分别交给 Mihomo 与 sing-box 真实解析。
- AI 业务探测只协商正确认证方式且只接受 OpenAI 401；服务器组改为 `urltest`，全死时用运行时标记重生成 direct/WARP 降级配置。客户端订阅不再携带第三方 AI SOCKS 凭据。
- 重装使用 staging + 失败回滚；旧目录保留到最终验收完成，失败时同步恢复 sing-box 二进制、systemd unit/启停状态、crontab 与 iptables；旧证书在新证书完成 SAN/密钥校验前可恢复；防火墙只维护 `EPS_INPUT/EPS_OUTPUT` 专属链。
- AI 运行时标记使用过渡文件和配置重载事务：恢复或降级失败时撤销本次状态变更并保留下一轮重试条件，避免标记与实际配置永久错位。

**关键证据**：HKBEIYONG 外部认证 SOCKS5 经服务器 AI 分流和 JP 上游访问 OpenAI 返回 401；HKBEIYONG/JP 部署分别 10 PASS/1 SKIP 与 11 PASS；公网订阅为 5/7 节点，Mihomo 与 sing-box 1.13 均通过；JP 两个 Cloudflare WS 路径在 Windows `--http1.1` 下均为 101；本地回归 `82 passed, 1 skipped`（包含项目目录 `mv` 失败注入），Git Bash 对安装与健康脚本语法检查通过。

**教训**：HTTP 200、JSON 可解析、端口可连接和配置文件可见都不是客户端可用证据；协议组行为必须以官方语义和真实内核验证，安装器必须在最终业务验收前保留可恢复的旧生产状态。

## -6. 自定义直连新机一键安装四连失败（v4.15.25）

**现象**：香港备用机使用 `hkbeiyong.290372913.xyz` 非交互安装时，依次在 DNS、证书安装、重复签发和健康检查阶段失败；早期半成品只生成了 `.env/config.json`，服务未启动。

**已确认根因**：
- `COUNTRY_CODE` 仅识别固定域名前缀，未知 `hkbeiyong.*` 被 ipinfo 地理码覆盖为 `HK`，节点名和订阅路径错误。
- 本项目 Cloudflare 凭据是 Global API Key，但安装器只写 `CF_API_TOKEN`，漏写配套 `CF_API_EMAIL`，API 返回 `Missing X-Auth-Email header`。
- acme.sh 首次安装证书时执行 reload，但 systemd unit 尚未创建；重复执行时 `Domains not changed / Skipping` 返回非 0，两种情况都被误判为证书失败。
- `health_check.sh` 的引号拼接存在 Bash 语法错误，且固定检查 `singbox-cdn`、8443/2083，不适用于 direct 模式。

**修复**：
- 从 `CF_DOMAIN` 首标签生成经校验的大写服务器标识；`DEPLOY_MODE` 仍是 CDN/direct 唯一真相。
- 同时支持 `cfat_` Bearer Token 与 Global API Key + Email，凭据只落 `.env`，日志仅报告是否已配置。
- acme reload 改为 unit 存在才重启；确认现有 ACME 证书未变化时继续 `--install-cert`，其他签发错误继续拒绝降级。
- 健康检查按 `DEPLOY_MODE` 选择服务与端口，并修复 Bash 引号；安装包回归覆盖这些约束。

**关键证据**：最终一键安装 `RC=0`；Cloudflare API 回读 `hkbeiyong` A 记录唯一、灰云、指向新机；Let's Encrypt YE1 证书 SAN 匹配且 `Verify return code: 0`；Base64/Clash/sing-box 公网入口均 200 且各含 4 个 `HKBEIYONG-*` 直连节点；外部认证 SOCKS5 出口 IP 匹配；生产健康检查返回 0。原 HK1 同期 SSH/443/2087/2096/1080 全部超时，已与新机交付分离。

**教训**：`COUNTRY_CODE` 是服务器标识而非地理国家码；Global API Key 必须携带账户邮箱；证书签发和证书安装/reload 是不同阶段；一键脚本必须验证其后续定时巡检脚本，重复执行也必须幂等成功。

## -5. 订阅 HTTP 200 但客户端无法下载：`-k` 掩盖自签名证书（v4.15.23）

**现象**：HK2 `/sub/HK2` `/clash/HK2` `/singbox/HK2` 在原审计中均显示 HTTP 200，但用户真实订阅下载失败。

**已确认根因**：HK2 是 Cloudflare 灰云直连，客户端直接验证源站 TLS，但安装器在 Cloudflare Origin 证书失败后回退为自签名证书。原 `full_audit.py` 和部署验证使用 `curl -k`，只证明服务返回 200，未证明证书被客户端信任。

**修复**：
- HK2 签发 Let's Encrypt 证书并安装到订阅服务；严格检查同时发现 JP `sub-jp` 也被自签名证书影响，同步签发含 `jp`/`sub-jp` SAN 的公网证书。
- 一键安装在有域名时强制 acme.sh + Let's Encrypt，签发失败不允许自签名/Origin CA 降级。
- 后续复查发现首次安装把域名写入 `.env` 后，证书函数仍读取旧 shell `CF_DOMAIN`，可能跳过可信证书分支；现已统一从落盘 `.env` 读取，并在签发前自动同步/验证灰云 DNS。
- 安装最终门禁改为用系统 CA、本机 SNI 和三条真实订阅路由下载内容；Base64/JSON/YAML 内容也必须通过格式检查。
- 部署验证对本机 2087 实际 TLS 服务执行 `openssl s_client -verify_return_error -verify_hostname`；外部 full audit 移除订阅请求的 `-k`。
- `cert_manager.py` 和 `health_check.sh` 对灰云订阅域名做持续信任检查，acme.sh 完成自动续签与服务 reload。

**关键证据**：修复前 HK2 严格 curl 报 `SEC_E_UNTRUSTED_ROOT`；HK1 同命令返回 200。修复后 HK2 Base64/Clash/sing-box 三类入口无 `-k` 均返回 200，HK2 证书 issuer 为 Let's Encrypt YE1；JP 证书 issuer 为 Let's Encrypt YE2 且 SAN 覆盖两个域名。

**教训**：订阅验收不得使用 `-k` 作为成功标准；HTTP 200 不等于真实客户端可下载。新装验证必须读取最终落盘配置，并覆盖 DNS → 证书 → TLS → HTTP 路由 → 内容格式全链路。CDN 回源证书与灰云订阅证书是两个不同的信任边界。

## -4. HK2 小磁盘云镜像导致一键安装多阶段失败（v4.15.21）

**现象**：新 HK2 执行非交互一键安装时，先后遇到 DNS 无上游、Ubuntu deb822 源 suite 被写成 `UNAVAILABLE`、sudoers conffile 提示卡住和 XanMod 解包耗尽 2GB 系统盘。旧脚本在自动模式使用 `set +e`，会让前置失败继续执行，存在“安装完成”假阳性。

**已确认根因**：云镜像的 resolver/APT 模板损坏，而安装器没有对 deb822 无效 suite、dpkg 非交互 conffile 和 XanMod `Installed-Size`+安全余量做前置检查。2GB 磁盘在已有系统占用下无法安全容纳 XanMod 内核包。

**修复**：
- 自动模式仍保持 fail-fast；APT 启用 `--error-on=any`，dpkg 使用 `--force-confdef --force-confold`。
- 增加 resolver 上游 DNS 修复、`UNAVAILABLE` suite 修复、中断 dpkg 恢复和 apt cache 清理。
- XanMod 安装前根据包体积与 230MB 安全余量判定；空间不足明确跳过，保留原生内核 BBR+FQ。Swap 按可用磁盘自适应创建。
- Python 必需依赖改为 apt 优先并强制 import 验证；证书 fallback 前清理半成品；最终验证失败必须返回非 0。
- Windows 部署入口为 stdout/stderr 配置 UTF-8，避免 GBK 终端输出状态符号时在 SSH 成功后反而异常退出。

**关键证据**：HK2 最终安装返回 0；`singbox`/`singbox-sub` active，`singbox-cdn` inactive；公网 `/clash/HK2` `/sub/HK2` `/singbox/HK2` `/info/HK2` 全部 HTTP 200；外部 SOCKS5 认证与 CONNECT 成功，出口 IP 等于 HK2。`tests/full_audit.py` 最终 `ALL OK`。

**教训**：一键脚本的成功必须由最终业务验证决定，不能用“继续跑到末尾”代替；内核更换必须在下载前评估安装体积和回滚余量。

## -3. Cloudflare 高位 HTTPS 端口上传受限，CDN 节点迁移到边缘 443（v4.15.20）

**现象**：同一台电脑和同一 JP 服务器，Reality TCP 443 上传正常，而 Cloudflare CDN 的 8443/2083 WS 节点上传明显偏慢。

**已确认根因**：当前中国电信到 Cloudflare 的路径对非 443 HTTPS 端口存在明显差别化限速；不是 Clash 节点选择、爱快全局上传限速或 JP sing-box 性能问题。绕过 Clash 直接连接 Cloudflare 时，443 与 8443/2083/2096 的上传差异仍存在；迁移后同一 Clash 和同一服务器不再复现慢速。

**修复**：
- CDN 客户端端口统一为 TCP 443，协议仍为 VLESS-WS-TLS / Trojan-WS-TLS。
- Cloudflare Origin Rules 按路径分流：`/api/v1/stream → 8443`，`/api/v1/data → 2083`。
- Reality 保持源站 TCP 443；TUIC 改为源站 UDP 443。TCP/UDP 是不同监听空间，不冲突。

**关键证据**：
- Origin Rules 写入前，JP 两个 `:443` WS 路径均返回 HTTP 400；写入后两个 Cloudflare A 记录逐 IP验证均返回 101。
- 现网 JP 订阅保持原节点名称与协议，两个 CDN 节点端口均为 443，TUIC 端口为 443。
- Clash 真实 8 MiB 上传：Reality 17.84 Mbps、VLESS-WS-CDN 41.57 Mbps、Trojan-WS-CDN 33.82 Mbps、TUIC-v5 42.14 Mbps。

**教训**：客户端看到的 Cloudflare 边缘端口与源站监听端口必须拆成不同常量；否则无法在不改协议和源站监听的前提下使用边缘 443。端口迁移必须同时验证 Cloudflare 101、现网订阅字段和真实客户端上传。

---

## -2. 跨服务器流量汇总本机自拉 SSL 失败（v4.15.19）

**触发场景**：实现 `/info?summary=1` 跨服务器流量汇总端点时，需要拉取 `TRAFFIC_AGGREGATE_ENDPOINTS` 中所有服务器的 `/api/traffic` 接口。

**现象**：JP 服务器访问自己的 `https://sub-jp.290372913.xyz:2087/api/traffic` 时 SSL 握手失败，导致 `/info?summary=1` 文本端点只显示 2/3 可达（HKCEPIN/HK1 OK，JP 自身 unreachable）。

**根因**：
- 服务器自己拉自己的 CF 域名会走公网 CF 边缘再绕回源站，CF 免费版对服务器 IP 的回源行为有特殊处理
- 第一次尝试改用 `https://127.0.0.1:2087/api/traffic` + `Host: sub-jp.290372913.xyz` 头部，仍然 SSL 失败（自签证书 SAN 不包含 127.0.0.1，且禁用证书校验也不行）
- 服务器内部对 127.0.0.1:2087 的 TLS 握手与外部对 sub-jp:2087 的握手行为不同

**关键证据**：
- 外部 `curl https://sub-jp.290372913.xyz:2087/api/traffic` ✅ 200 + JSON
- 服务器内部 `curl https://127.0.0.1:2087/api/traffic` ❌ SSL 错误
- `/api/traffic-summary` JSON 端点显示 JP 自身 unreachable

**修复**（v4.15.19，[subscription_service.py:2596-2725](scripts/subscription_service.py#L2596-L2725)）：
- `_render_traffic_summary()` 函数重构：本机数据**直接调用** `get_traffic_stats()`，完全不走 HTTP
- `/api/traffic-summary` 端点同样本机数据直接构造 `local_data` 字典，仅对其他服务器做 HTTPS 拉取
- 关键代码：`remote_endpoints = [ep for ep in TRAFFIC_AGGREGATE_ENDPOINTS if ep and not ep.startswith(local_sub)]`

**教训**：
1. 服务器**永远不要通过 CF 域名或 127.0.0.1 自拉自己的 HTTP 接口**，直接调用本地函数即可
2. 跨服务器汇总端点设计时，本机数据走函数调用，远端数据走 HTTPS，两层完全分离
3. 自签证书 SAN 不含 127.0.0.1 时，即使禁用证书校验 SSL 握手仍可能失败（取决于客户端库实现）

---

## -1. install.sh 三个连环坑：非交互模式退出 + 证书残留 + WS 路径未同步（v4.15.18）

**触发场景**：JP 服务器迁移到新 IP `3.113.4.86`，按 AGENTS.md 标准化流程用 `bash install.sh < /dev/null` 远程执行一键安装。

### 坑 A：非交互模式 `read -p` 触发 `set -e` 退出

**现象**：远程 SSH 执行 `bash install.sh < /dev/null`，脚本在第一次 `read -p "..."` 处退出码 1，未完成安装。

**根因**：
- install.sh 顶部 `set -e`，且脚本内部多处 `read -p` 等待用户输入
- 当 stdin 不是 tty（SSH 非交互 / `< /dev/null`）时，`read` 立即返回非零退出码
- `set -e` 捕获到非零退出码，直接终止脚本
- 尝试用 `bash +e /tmp/install.sh` 无效：脚本内部 `set -e` 重新启用

**关键证据**：
- `bash install.sh < /dev/null` 卡在 `read -p "是否配置AI住宅代理？"`，退出码 1
- 加 `set +e` 后能继续，但 `set -e` 在子函数中重新启用又被捕获

**修复**（v4.15.18，[install.sh:25-32](install.sh#L25-L32)）:
```bash
set -e
# 非交互模式自适应（stdin 不是 tty 时自动禁用 set -e + 启用 AUTO_YES）
if [ ! -t 0 ]; then
    set +e
    export AUTO_YES="${AUTO_YES:-1}"
fi
```

**教训**：远程执行 install.sh 必须先检测 `[ -t 0 ]`，不能依赖 `bash +e` 外部参数。

### 坑 B：install.sh 重复执行导致 `fullchain.pem` 与 `cert.pem` 不匹配

**现象**：sing-box 启动失败 `FATAL initialize inbound[1]: parse x509 key pair: tls: private key does not match public key`

**根因**：
- install.sh 第一次执行（在 .env 上传前）使用旧域名生成证书：`cert.pem` + `key.pem` + `fullchain.pem` 三件套
- 第二次执行（用新 .env）只更新了 `cert.pem` + `key.pem`，`fullchain.pem` 残留旧证书
- sing-box config_generator 优先使用 `fullchain.pem`，与 `key.pem` modulus 不匹配

**关键证据**：
- `cert.pem` modulus = `9a4dbb2511e3e3c7219685482cf8e883`（新）
- `key.pem` modulus = `9a4dbb2511e3e3c7219685482cf8e883`（新，匹配 cert）
- `fullchain.pem` modulus = `4e5a5aa6...`（旧，残留）

**修复**：
```bash
rm -rf /root/singbox-eps-node/cert && mkdir -p cert && python3 scripts/cert_manager.py
```

**教训**：install.sh 重复执行或更换域名后，必须 `rm -rf cert` 强制重生，不能依赖 cert_manager.py 的增量更新。`cert_manager.py` 应在 `fullchain.pem` modulus 不匹配 cert.pem 时自动重生（待优化项）。

### 坑 C：install.sh 从 GitHub clone 的 config_generator 是旧版，WS 路径不符合 AGENTS.md 铁律

**现象**：CDN WS 握手测试 `https://jp.290372913.xyz:8443/api/v1/stream` 返回 404，期望 101。

**根因**：
- install.sh 部署项目时 `git clone https://github.com/Alan-zzh/singbox-eps-node`（仓库主线版本可能落后于本地工作区）
- 本地 `config_generator.py` 已用新路径 `/api/v1/stream` `/api/v1/data`（AGENTS.md 第 13 条铁律：WS 路径已改为非代理特征路径）
- 服务器跑的 config.json 是旧版 config_generator 生成，WS 路径是 `/vless-ws` `/trojan-ws`
- 订阅端 subscription_service.py 输出的链接用 `/api/v1/stream`，与服务端 inbound 不匹配 → 客户端连不上

**关键证据**：
- 服务器 config.json `vless-ws` inbound path = `/vless-ws`
- 本地 config_generator.py L319 path = `/api/v1/stream`
- `curl https://jp.290372913.xyz:8443/api/v1/stream` 返回 404

**修复**：`python deploy.py --fix` 同步本地最新 config_generator.py + subscription_service.py，重跑 config_generator 重启服务，CDN 握手返回 101 ✅

**教训**：install.sh 部署完必须立即跑 `deploy.py --fix` 同步本地最新代码，不能依赖 GitHub 主线版本。或考虑 install.sh 直接从本地工作区 SFTP 上传（不 git clone）。

### 坑 D：TUIC 凭据降级导致订阅端缺 TUIC 协议

**现象**：`/sub/JP` 只返回 5 协议（缺 tuic://），但服务端 config.json 有 TUIC inbound 且 UDP 端口监听中。

**根因**（凭据一致性铁律违反）：
- `config_generator.py` L54: `tuic_uuid = env_vars.get('TUIC_UUID', str(uuid.uuid4()))` — .env 无 TUIC_UUID 时随机生成 UUID 写入 config.json，但**不写回 .env**
- `config_generator.py` L53: `tuic_password = env_vars.get('TUIC_PASSWORD', random...)` — 同上
- `subscription_service.py` L522-527: `ENABLE_TUIC=true 且 TUIC_UUID/TUIC_PASSWORD 为空 → 自动 ENABLE_TUIC=False`（凭据降级保护）
- 服务端用 config.json 里的随机 UUID 跑 TUIC inbound，订阅端因 .env 无凭据降级不输出 TUIC → 客户端拿不到 TUIC 链接

**关键证据**：
- 服务器 .env: 仅有 `TUIC_PORT=29725` 和 `ENABLE_TUIC=true`，无 TUIC_UUID/TUIC_PASSWORD
- 服务器 config.json: TUIC inbound uuid = `33333333-3333-4333-8333-333333333333`, password = `REDACTED_TUIC_PASSWORD`
- `/sub/JP` 返回 5 协议（无 tuic://）

**修复**：
1. 从服务器 config.json 提取 TUIC UUID + password
2. 写入服务器 .env + 本地 .env（`TUIC_UUID=...` `TUIC_PASSWORD=...`）
3. 重启 singbox-sub
4. `/sub/JP` 验证返回 6 协议（含 tuic://） ✅

**教训**（AGENTS.md 凭据一致性铁律具体化）：
- config_generator.py 生成随机凭据后**必须写回 .env**，否则订阅端读取不到
- 涉及字段：`TUIC_UUID` / `TUIC_PASSWORD` / `ANYTLS_PASSWORD` / `REALITY_SHORT_ID` / `REALITY_PRIVATE_KEY`
- 部署后必须用 `/sub/{CC}` 协议数验证：CDN 模式预期 6 协议，直连模式预期 4 协议，缺一即为凭据降级

---

## 0. CDN 评分公式延迟区分度不足导致高延迟IP混入（v4.15.17）

**现象**: 用户反馈 Clash 中优选IP延迟很高。诊断发现 HKCEPIN 的协议IP用户路径延迟达380ms，但评分96.58分，与JP的35ms延迟IP同分（96.2分）。

**根因**: `calculate_composite_score` 评分公式延迟分档过粗：
- 用户路径延迟评分：`<150ms → 100分`，35ms 和 140ms 都是满分，无法区分
- VPS延迟评分：`100*(1-lat/500)`，100ms=80分，130ms=74分，差距仅6分（10%权重后差0.6分）
- 速度权重过高（用户路径速度35%），速度好的高延迟IP能靠速度拉回分数

**关键证据**:
- HKCEPIN 198.41.223.63: VPS延迟102ms, 用户路径380ms, 速度323Mbps → 旧评分96.58
- JP 162.159.46.54: VPS延迟129ms, 用户路径35ms, 速度270Mbps → 旧评分96.18
- 高延迟IP反而比低延迟IP评分高0.4分（完全错误）

**修复**（v4.15.17）:
1. 权重调整：VPS延迟 10%→20%，用户路径延迟 35%→40%（合计60%决定延迟）
2. 用户路径速度 35%→10%，三网均衡 5%→10%，稳定性 5%→10%
3. 延迟分档细化：`<50ms→100, <80ms→95, <100ms→85, <120ms→70, <150ms→55, <250ms→30, <400ms→10`
4. 速度分档：100Mbps即95分（用户反馈100够用），200Mbps才满分
5. 硬淘汰放宽：`user_path_latency_ms` 120→200，让评分区分而非硬砍

**修复后效果**:
- JP好IP(90ms+35ms): 96.2→94.5分
- HKCEPIN问题IP(102ms+380ms): 96.58→51.0分（降45.6分）
- 新排序：JP 94.5 > HKCEPIN 51.0（正确！低延迟优先）
- 两台服务器均选出第九批用户投喂IP作为协议IP，延迟<120ms，速度>200Mbps

**教训**:
1. 评分公式的分档不能过粗，`<150ms全满分`会让35ms和140ms无法区分
2. 速度权重不应高于延迟（用户体验主要由延迟决定，速度达标即可）
3. VPS侧延迟和用户路径延迟必须结合判断，单一维度不够
4. 硬淘汰阈值过严（120ms就砍掉）会让评分系统失去区分机会

---

## 1. CDN 优选 IP 阶段化测速漏掉用户投喂 IP（v4.15.16）

**现象**: 用户投喂 13 个本地实测低延迟 IP，加入 `CDN_PREFERRED_IPS` 静态池并 POST 到 `/api/preferred-ips` 后，重启 `singbox-cdn` 触发第一次测速，13/13 全部被淘汰，池中 0/13。

**根因**: `cdn_monitor.py` `fetch_cdn_ips()` 步骤3 阶段化测速逻辑：
1. 阶段1：所有候选IP测 TCP+TLS+HTTP 延迟，按延迟排序
2. 阶段2：**只对前30名做速度测试**（`if i < 30:`）

用户投喂的 13 个 IP VPS 侧延迟 92-107ms，在约 200 个候选中排 30 名外，未进入测速阶段，导致：
- `speed_mbps=0.0`（没做速度测试）
- `composite_score_v2=0.0`（速度为0导致评分公式输出0）
- 排序垫底 → 被 Top 15 池淘汰

**关键证据**:
- 数据库 `ip_performance` 表：13 个 IP 都是 `total_tests=1, success_count=1, fail_count=0, avg_latency=92-107ms, speed_mbps=0.0, composite_score_v2=0.0`
- 日志：只有 3 个新IP（172.64.49.197、162.159.5.104、162.159.22.242）因延迟较低进了前30做了测速，速度 326-337Mbps 都很好
- 其余 10 个新IP在日志中只有"✅ 存活"，没有"速度测试"日志

**修复**: `cdn_monitor.py` L2185-2201，阶段2条件从 `if i < 30:` 改为 `if i < 30 or is_local_source:`，让 `local` 源（`CDN_PREFERRED_IPS`）IP 无条件进入测速阶段。

**修复后结果**: JP 6/13、HKCEPIN 7/13 新IP进入 Top 15 池，跨两台共 10/13 入选。

**教训**:
1. 阶段化测速的"前N名"截断逻辑会漏掉 VPS 侧延迟高但用户侧延迟低的 IP（VPS到CF延迟 ≠ 用户到CF延迟，见 project_memory 已记录的 Lessons Learned）
2. `local` 源 IP 是用户实测投喂的，应给予测速机会而非仅按 VPS 延迟排序截断
3. `speed_mbps=0` 不代表 IP 速度为0，可能只是没做测速；评分公式对 `speed_mbps=0` 输出0分，导致连锁淘汰

---

## 1. HK1 香港直连旧路径 `/hk` 订阅 404（v4.15.15）

**现象**: 用户使用 `https://hk1.290372913.xyz:2087/clash/hk` 和 `/sub/hk` 更新香港直连订阅失败。外部复测确认 `/clash/hk`、`/sub/hk`、`/singbox/hk`、`/info/hk` 均返回 404，但标准 HK1 路径 `/clash/HK1`、`/sub/HK1`、`/singbox/HK1` 返回 200。

**根因**:
1. HK1 服务端只注册了 `COUNTRY_CODE=HK1` 对应路由，未兼容旧客户端保存的 `/hk` 路径
2. 不能通过新增 `sub-hk1` 解决：线上证书 SAN 只包含 `hk1.290372913.xyz`，`sub-hk1` 既无 DNS，又会证书名不匹配

**修复**:
1. `subscription_service.py` 仅在 `COUNTRY_CODE=HK1` 时注册 `/sub/hk`、`/clash/hk`、`/singbox/hk`、`/info/hk` 别名
2. 已上传到 HK1 `/root/singbox-eps-node/scripts/subscription_service.py` 和 `/opt/singbox-eps-node/scripts/subscription_service.py`，重启 `singbox-sub`
3. README 补充 HK1 主域名和 `/hk` 兼容说明

**证据**:
- 修复前：`curl https://hk1.290372913.xyz:2087/clash/hk` → 404；`/sub/hk` → 404
- 本地：`python -m py_compile scripts\subscription_service.py` 通过；Flask test client 验证 `/clash/hk`、`/sub/hk`、`/singbox/hk`、`/info/hk` 均 200
- 远端：HK1 `python3 -m py_compile /root/singbox-eps-node/scripts/subscription_service.py` 通过，`systemctl is-active singbox-sub` → active
- 外部：`curl https://hk1.290372913.xyz:2087/clash/hk` → 200，`/sub/hk` → 200，`/singbox/hk` → 200，`/info/hk` → 200；`/sub/hk` 解码后 4 个 HK1 直连节点

**教训**:
1. HK1 是服务器标识 `HK1`，但客户端历史配置里可能只填 `hk`；HK1 域名下可以兼容 `/hk`，其他服务器不能泛化
2. 订阅路径兼容优先在路由层做，不要新增不在证书 SAN 内的 `sub-hk1`

---

## 0. Base64 订阅默认 UA 被误降级成 Xray 兼容模式（v4.15.14）

**现象**: 用户反馈“是不是把核心换成 XRAY 了，singbox 连接不上”。外部抓取 `/sub/JP` 时，带 `sing-box/1.13.14` UA 返回 6 个节点；默认 curl UA 只返回 4 个节点，缺 anyTLS / TUIC-v5，表现为被强制降级到 Xray 兼容订阅。`/singbox/JP` JSON 仍返回 6 个 sing-box 出站，服务端核心没有换成 Xray。

**根因**:
1. `subscription_service.py` 将未知 UA、浏览器、curl、wget、python-requests 默认识别为 `xray`
2. sing-box/GUI 拉取器可能使用空 UA、通用 UA 或 `Go-http-client`，会被误降级
3. `tests/full_audit.py` 一度把“默认 UA 被识别为 xray”写成设计行为，掩盖了默认订阅不完整的问题

**修复**:
1. 默认/未知 UA 改为 `full`
2. 浏览器、curl、wget、python-requests 改为 `full`
3. 只有明确识别为 Quantumult X / Surge / Loon / v2Box 等纯 Xray 客户端，或手动加 `?client=xray` / `?client=standard`，才输出 Xray 兼容节点
4. `tests/full_audit.py` 改回默认 UA 预期 full

**证据**:
- 修改前：`curl https://sub-jp.290372913.xyz:2087/sub/JP` 解码后 4 节点；`curl -A "sing-box/1.13.14" .../sub/JP` 解码后 6 节点
- 修改前：`curl https://sub-jp.290372913.xyz:2087/singbox/JP` JSON 输出 `JP-VLESS-Reality` / `JP-Trojan-TCP` / `JP-VLESS-WS-CDN` / `JP-Trojan-WS-CDN` / `JP-anyTLS` / `JP-TUIC-v5`
- 本地：`python -m py_compile scripts\subscription_service.py tests\full_audit.py` 通过
- 本地：订阅能力回归测试 3 项通过（支持客户端 full、查询参数别名、Base64 body 无注释行）
- 部署：JP/HK/HK1/HKCEPIN 四台有效服务器 `deploy.py` 远端 py_compile、config_generator、sing-box check、服务重启和订阅验证通过
- 外部：`/sub` 默认输出 JP/HK/HKCEPIN 6 链接、HK1 4 链接；显式 `?client=xray` 仍输出 4 条标准 vless/trojan 链接
- 外部：`PYTHONUTF8=1 python tests\full_audit.py` 最终 `ALL OK`，JP/HK/HKCEPIN CDN WS 入口均 HTTP 101

**教训**:
1. 不要把“保守兼容”做成默认删节点；默认应服务项目主客户端 sing-box，全量输出
2. Xray 兼容模式只能由明确 UA 或显式 `?client=xray` 触发
3. 审计脚本不能把线上异常输出改写成“设计行为”

---

## 0. CDN 节点名后缀被误删 + CF 自愈规则假成功导致反复漂移（v4.15.13）

**现象**: 用户反馈订阅链接失败、CDN 失效，并指出 CDN 节点名被删掉 `-CDN` 后缀。线上 Clash/sing-box 订阅里 CDN 节点显示为 `JP-VLESS-WS` / `JP-Trojan-WS`，与项目既定 `{CC}-VLESS-WS-CDN` / `{CC}-Trojan-WS-CDN` 不一致。

**根因**:
1. `subscription_service.py` 的 `node_name(protocol, cdn=False)` 支持 `-CDN`，但 Base64 URI、Clash YAML、sing-box JSON、proxy-groups 和 `cdn_status_api` 调用 VLESS-WS/Trojan-WS 时未传 `cdn=True`
2. v4.15.12 的审查记录把“订阅输出无 `-CDN`”误当成统一口径，导致 `full_audit.py` 改成按无后缀匹配，掩盖了真实命名回归
3. `cloudflare_proxy_rules.py apply` 使用 delete+add 规则路径，Cloudflare Rulesets API 出现“命令返回成功但 entrypoint 仍保留旧规则”的假成功；远端 health_check 又把旧 `/vless-ws` `/trojan-ws` / 2053 / SG 表达式和 DDoS L7 override 写回

**修复**:
1. `subscription_service.py` 三种订阅格式和分组统一对 CDN WS 节点使用 `node_name(..., cdn=True)` / `share_fragment(..., cdn=True)`
2. `scripts/config.py` 兼容旧调用的 `get_node_name('vless-ws'/'trojan-ws')` 返回 `-CDN` 后缀
3. `cloudflare_proxy_rules.py` 改为 PUT phase entrypoint 稳定替换目标 skip rule，`PROXY_SUBDOMAINS` 固定为 JP/HK/HKCEPIN，删除 SG 和旧 WS 路径，正常 apply 路径确保 `ddos_l7_entrypoint=null`
4. `tests/test_cloudflare_proxy_rules.py` 和 `tests/test_disconnect_regression.py` 更新到当前 6 节点协议栈和 CDN 后缀规则
5. 临时创建的 `sub-hk1.290372913.xyz` 已删除；HK1 是 direct 模式，订阅走 `hk1.290372913.xyz:2087`，不输出 CDN 节点

**证据**:
- JP/HK/HKCEPIN 三台服务器两轮 `deploy.py --server ...`：远端 py_compile、config_generator、sing-box check、服务重启、订阅端点、凭据一致性 8 项全 PASS
- 外部订阅抓取：JP/HK/HKCEPIN Clash 和 sing-box 均输出 `{CC}-VLESS-WS-CDN` / `{CC}-Trojan-WS-CDN`
- CDN 字段检查：server 为 CF 优选 IP，Host/SNI/servername 为主域名 `jp/hk/hkcepin.290372913.xyz`，未出现 sub-* 节点降级
- 外部 WS 握手：JP/HK/HKCEPIN 的 `8443/api/v1/stream` 与 `2083/api/v1/data` 全部 HTTP 101
- Cloudflare 状态：skip rule 表达式只包含 `jp/hk/hkcepin.290372913.xyz`、端口 `2087/8443/2083`、路径 `/api/v1/stream` `/api/v1/data`，`min_tls_version=1.2`，`ddos_l7_entrypoint=null`
- `python tests/full_audit.py`：JP/HK/HKCEPIN 6 协议 + CDN 101，HK1 4 协议 direct，最终 `ALL OK`

**教训**:
1. CDN WS 节点名必须保留 `-CDN` 后缀；不能为了“统一显示”去掉，否则用户无法区分直连与 CDN
2. `sub-*` 只能是订阅入口，绝不能作为 CDN 节点 fallback；项目已有直连节点，CDN 节点必须保持真正 CDN 路径
3. Cloudflare Rulesets 修复不能只信 apply 返回值，必须立刻 `status` 验证 entrypoint 真实表达式和 `ddos_l7_entrypoint`
4. 修改 full_audit 匹配规则时不能把真实回归改成测试口径，必须以项目协议表和用户可见订阅输出为准

---

## 0. HKCEPIN/HK1 COUNTRY_CODE 错配导致订阅 404，用户误判"CDN 优选 IP 全失效"（v4.15.12）

**现象**: 用户反馈"CDN 又不行了，优选 IP 全部失效"。实际排查发现 CDN WS 全部 101 ✅，问题是 HKCEPIN/HK1 两台服务器的 `.env` 中 `COUNTRY_CODE=HK`，但订阅端点路由是 `/clash/{COUNTRY_CODE}`，所以 `/clash/HKCEPIN` `/clash/HK1` 返回 404，用户拿到空订阅误判为 CDN 故障。

**根因**:
1. `install.sh` 用 `ipinfo.io` 自动检测服务器 ISO 国家代码，HKCEPIN(aws东京)/HK1(阿里云香港) 都被检测为 `HK`，但项目用 COUNTRY_CODE 作为服务器标识（区分 HK/HK1/HKCEPIN），不是地理位置
2. 之前文档审计 agent 误判 `deploy.py` / `scripts/deploy_verify.py` 不存在（实际根目录有 deploy.py，scripts/ 有 deploy_verify.py），导致 AGENTS.md 一度被错误修改

**证据**:
- 修复前：`curl https://sub-hkcepin.290372913.xyz:2087/clash/HKCEPIN` → 404
- 修复后：`curl https://sub-hkcepin.290372913.xyz:2087/clash/HKCEPIN` → 200 + 6 节点
- `tests/full_audit.py` 重跑：JP/HK/HKCEPIN 全 6 协议 + CDN 101，HK1 4 协议（direct），ALL OK

**修复**:
1. 远程服务器 `.env`：HKCEPIN `COUNTRY_CODE=HK→HKCEPIN`，HK1 `COUNTRY_CODE=HK→HK1`
2. `install.sh` 防复发：基于 `CF_DOMAIN` 前缀推导正确 COUNTRY_CODE（`jp.*→JP` / `hk.*→HK` / `hk1.*→HK1` / `hkcepin.*→HKCEPIN`），覆盖 ipinfo.io 自动检测值
3. `tests/full_audit.py` 修复 cc 硬编码 bug（HKCEPIN/HK1 的 cc 写死为 `'HK'` 导致测试用错路径）

**教训（铁律，已写入 AGENTS.md 第 15 条扩展）**:
1. **COUNTRY_CODE 是服务器标识，不是地理位置**：多台同地区服务器必须用域名前缀区分（HK/HK1/HKCEPIN），不能依赖 ipinfo.io 自动检测
2. **install.sh 的 ipinfo.io 检测只适合单服务器场景**：多服务器部署时必须用 CF_DOMAIN 前缀推导覆盖
3. **"优选 IP 全部失效"先查订阅端点是否 404**：CDN WS 101 ✅ + 订阅 404 = COUNTRY_CODE 错配，不是 CDN 故障
4. **文档审计 agent 报告需用 Glob/Read 验证**：不能直接信任 agent 报告的"文件不存在"结论
5. **测试脚本不能硬编码 cc**：`full_audit.py` 把 HKCEPIN/HK1 的 cc 写死为 `'HK'`，掩盖了真实 bug 长达数月

---

## 1. REALITY_SHORT_ID 字面值写入 .env（v4.15.10）

**现象**: sing-box 校验失败报 `invalid byte: U+0024 '$'`，`.env` 中 `REALITY_SHORT_ID=$(openssl rand -hex 8)` 是字面值未被 shell 展开。

**根因**: 跨脚本写入 `.env` 时，shell 命令字面量未被展开。install.sh 修复只覆盖新部署，已有部署残留。

**修复**: 删旧行 → `openssl rand -hex 8` 生成实际值 → 重跑 config_generator → 校验通过。

**教训**:
1. `.env` 值写入时必须确保 shell 展开（Python/paramiko 写入时要预展开 `$(...)`）
2. `config_generator.py` 运行后必须 `sing-box check -c config.json` 验证
3. 任何 hex 值读取时做合法性校验（16 位 hex）

---

## 2. CRLF 换行导致 hex 校验失败（v4.15.10）

**现象**: deploy_verify.py 的 `grep -qE '^[0-9a-f]{16}$'` 返回 false，但值看起来正确。

**根因**: `.env` 含 CRLF（`\r\n`），`cut -d= -f2` 提取值尾部含 `\r`，实际为 `cf76f0d642c995fc\r`。Windows 编辑器写入 CRLF → sftp 上传到 Linux → 未转换。

**修复**: 所有 `.env` 读取命令加 `tr -d "\r"`。全局修复：deploy_verify.py、pre-flight check、health_check.sh。

**教训**:
1. 跨平台 `.env` 必须处理 CRLF，任何从 `.env` 提取值的脚本都要 `tr -d "\r"`
2. hex 校验必须 strip 后再检查（通用做法：`tr -d "'\"\r\n\t "`）

---

## 3. curl `-o /dev/null` 在 Windows 失效 → 假 403（v4.15.10 铁律）

**现象**: SSH 远程执行 `curl -o /dev/null -w '%{http_code}' https://jp...:8443/vless-ws` 返回 403，但同命令本地用 `-o NUL` 返回 101。CDN "故障"是测试工具误报。

**根因**: Windows curl.exe 不识别 `/dev/null`，创建名为 `null` 的文件，输出被吞 → 假 403。

**证据**:
- PowerShell: `curl -s -4 -o NUL -w '%{http_code}' https://jp.290372913.xyz:8443/vless-ws` → `101`
- 远程 SSH 同命令用 `-o /dev/null` → `403`（假阳性）
- 改用 `-D -` dump headers → 实际 101

**教训（铁律，已写入 AGENTS.md）**:
1. **Windows 上永远用 `-o NUL`，不能用 `-o /dev/null`**
2. **CDN WS 验证必须从外部执行**，不能依赖服务器自测（CF 拦服务器 IP → 假 403）
3. 单次 403 不是 CDN 损坏（CF 瞬断/重试即可）

---

## 4. 服务器端 CDN 探针假阴性导致周期性"订阅/CDN 失效"（v4.15.11 已移除）

> ⚠️ **该功能已在 v4.15.11 移除，此处记录供历史回溯。**

**现象**: CDN 通过 CF 橙云周期性不可用（中国用户 403），但订阅服务日志和 health_check 全部 OK。用户反复遇到 CDN 节点连不上。

**根因（GraphQL 防火墙事件证实）**:
1. CF L7 DDoS ML（自适应，7 日滑动窗口）周期性拦截中国 ISP（CHINANET/中国移动）到 `/*-ws` 路径的 WebSocket 升级请求
2. 服务器端 `_probe_cdn_ws()` 从 AWS/阿里云 IP 测 CF 主域名 → **永远 101（不被 ML 拦截）**
3. 探针永远假阴性 → `CDN_EDGE_FALLBACK` 从不触发 → 订阅一直吐主域名 CDN 节点 → 中国用户连 → 403

**为什么是周期性的**：
- CF L7 DDoS ML 在流量突发时 (多个中国用户同时连接) 触发封锁
- 流量下降后 ML 解封（GraphQL 证实 2-3 分钟内恢复）
- 但探针只在被订阅请求调用时才探测（缓存 TTL=300s），且从服务器测永远 OK
- 用户下次流量突发 → 再次封锁 → 无限循环

**移除原因**: 服务器端探针从错误位置测试（AWS IP vs 中国用户 IP）永远不能测到真实问题。`CDN_EDGE_FALLBACK` 写入 sub-* 直连地址到 CDN 节点，违背了 CDN 节点必须用主域名橙云代理的架构铁律。

**替代方案**: 改用非代理特征路径 `/api/v1/stream` `/api/v1/data` 降低 CF ML 误报率；优选 IP 自动选择不变；用户客户端在多协议间自动 fallback。

---

## 4. HK1 部署模式误判（v4.15.2 铁律）

**现象**: 修复脚本把 HK1（直连）当成 CDN 模式处理，添加 WS-CDN 节点导致不可用。

**根因**: 用 `COUNTRY_CODE == 'HK'` 判断部署模式，但 HK 和 HK1 地理都在香港。

**铁律（已写入 AGENTS.md 第29条）**:
- `.env` 显式 `DEPLOY_MODE=direct` 为最高优先级
- Fallback：`CF_DOMAIN.startswith('hk1.')` 才是直连
- **绝对禁止**用 `COUNTRY_CODE` 判断

---

## 5. TUIC v5 凭据不匹配静默失败（v4.15.0）

**现象**: `ENABLE_TUIC=true` 时，用户拿到节点但无法连接。

**根因**: config_generator.py 在 `TUIC_UUID` 为空时生成随机 UUID，subscription_service.py 用空字符串 → 凭据不一致。

**铁律（已写入 AGENTS.md 第24条）**:
- 订阅端实现凭据降级：`ENABLE_xxx=true` 且凭据为空时自动 `ENABLE_xxx=False`
- 服务端生成随机凭据时必须写入 `.env` 并被订阅端读取

---

## 6. sub-* 域名扩散到 CDN 节点（v4.15.1 伪 CDN 化）

**现象**: CDN 节点 server/Host 被改为 sub-* 直连域名，丧失抗 IP 封锁能力。

**铁律（已写入 AGENTS.md 第28条）**:
- CDN 代理节点（VLESS-WS/Trojan-WS）必须用主域名 `cf_domain`（橙云 `proxied=true`）
- 订阅端点（/clash /sub /singbox）用 sub-* 子域名（灰云 `proxied=false`）
- **两类用途严格分离，不能混淆**

---

> **完整项目规则见 [AGENTS.md](AGENTS.md)**。本文件仅保留历史 bug 供回溯参考，日常开发以 AGENTS.md 铁律为准。
