# 项目状态快照 (Project Snapshot)

## 当前版本
**v1.0.75** (CAKE内核模块主动安装+FQ-PIE降级实际应用到网卡+精确诊断)

---

## 版本历史
| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0.34 | 2026-04-20 | HTTPS订阅服务+Cloudflare正式证书+端口9443 |
| v1.0.35 | 2026-04-20 | 文档完善+CDN/SOCKS5状态确认+证书申请流程记录 |
| v1.0.36 | 2026-04-20 | CDN优选IP改为实时DNS解析+每小时自动更新 |
| v1.0.37 | 2026-04-20 | 恢复固定优选IP池（中国用户实测低延迟IP） |
| v1.0.38 | 2026-04-20 | 新增sing-box JSON配置接口，内置AI流量自动路由规则 |
| v1.0.39 | 2026-04-20 | 修复Trojan-WS链接缺少insecure=1参数 |
| v1.0.40 | 2026-04-20 | SOCKS5路由规则优化：加入aistudio.google.com，排除X/推特/groK |
| v1.0.41 | 2026-04-20 | 修复Trojan-WS协议不通：添加SSL配置+修复path参数URL编码 |
| v1.0.42 | 2026-04-21 | 修复订阅端口9443不通：防火墙放行9443+默认端口6969→9443+path编码一致性 |
| v1.0.43 | 2026-04-21 | 端口硬编码锁定+防篡改校验+防火墙全放行+健康检查自动恢复+标准操作流程 |
| v1.0.44 | 2026-04-21 | 修复V2rayN订阅更新失败：9443→2087走CDN+域名访问解决证书匹配 |
| v1.0.45 | 2026-04-21 | 全面消除硬编码+DNS优选CDN+HY2规避修复+新VPS适配 |
| v1.0.46 | 2026-04-21 | HY2双协议保障恢复+SOCKS5 AI路由文档补全+铁律10文档同步 |
| v1.0.47 | 2026-04-21 | HY2端口跳跃无感切换：sing-box配置添加hop_ports字段 |
| v1.0.48 | 2026-04-21 | 脱敏处理+一键安装脚本+GitHub仓库公开+临时脚本清理 |
| v1.0.49 | 2026-04-21 | 修复AI-SOCKS5被错误暴露为用户节点+新增铁律11 |
| v1.0.50 | 2026-04-21 | 全面排查13个隐藏坑+跨文件一致性修复 |
| v1.0.51 | 2026-04-21 | 修复HY2端口跳跃iptables规则：端口范围22000→21000+补全TCP双规则 |
| v1.0.52 | 2026-04-21 | 全面审查修复5个隐藏Bug：证书文件名统一+自动续签cron+防火墙顺序+CDN死循环+住宅重启 |
| v1.0.53 | 2026-04-21 | **全面优化与验证**：文档版本统一+代码质量审查+安装流程修复+功能模块测试 |
| v1.0.54 | 2026-04-21 | subscription_service.py安全加固：Token认证+IP验证+连接泄漏+异常脱敏+ImportError降级 |
| v1.0.60 | 2026-04-22 | 新增按月流量统计：traffic_stats表+每月14号自动归零+首页流量显示+/api/traffic接口 |
| v1.0.61 | 2026-04-22 | 优化CDN优选IP4级降级机制+完善流量统计功能+详细文档记录 |
| v1.0.62 | 2026-04-22 | 修复证书路径BUG(cert.crt→cert.pem)+sysctl防重复追加+requirements.txt+文档同步 |
| v1.0.63 | 2026-04-22 | 交互式SOCKS5配置+一键重装reset+一键优化optimize+3加速确认+注释修正 |
| v1.0.64 | 2026-04-22 | 系统更新+3加速全自动先行+无需重启+流程重构 |
| v1.0.65 | 2026-04-22 | BBR+FQ+CAKE三合一加速+CAKE持久化+BBR高丢包参数 |
| v1.0.66 | 2026-04-22 | 修复set -e导致CAKE失败脚本退出+函数定义顺序+降级保障 |
| v1.0.67 | 2026-04-22 | Singbox已安装时交互选择卸载重装/保留+版本号更新 |
| v1.0.68 | 2026-04-22 | 卸载重装=完全清除所有数据+配置+证书+服务+定时任务+防火墙 |
| v1.0.69 | 2026-04-22 | 国家代码自动检测+CF_API_TOKEN交互式填写+singbox启动诊断+NODE_PREFIX动态生成 |
| v1.0.70 | 2026-04-22 | CF配置自动从旧S-ui读取+证书缺失自动生成+singbox启动诊断 |
| v1.0.71 | 2026-04-22 | CAKE状态真实显示+一键重装reinstall无感+自动重启+密码保留 |
| v1.0.72 | 2026-04-22 | reinstall改为操作系统重装(bin456789/reinstall)+root密码双重确认+reset明确为singbox应用重装 |
| v1.0.73 | 2026-04-22 | sing-box内核升级1.11.3→1.13.9 |
| v1.0.74 | 2026-04-22 | geoip/geosite改rule_set+CAKE降级改FQ-PIE |
| v1.0.75 | 2026-04-22 | CAKE内核模块主动安装+FQ-PIE降级实际应用到网卡+精确诊断 |

---

## 最新更新内容 (v1.0.75)

### 修复：CAKE队列未启用 — 降级方案也不生效

**问题**: VPS上CAKE队列显示"未启用（降级为FQ）"，两个根因：
1. 多数VPS使用精简内核，`sch_cake`模块未安装 — 代码只尝试`modprobe`，未主动安装`linux-modules-extra`包
2. 降级时只设置sysctl参数`default_qdisc=fq_pie`，未通过`tc qdisc replace`实际应用到网卡 — 导致降级也不生效

**修复**:
- `setup_cake_qdisc()`增加主动安装`linux-modules-extra-$(uname -r)`步骤，安装后重试`modprobe sch_cake`
- 新增`setup_fq_pie_qdisc()`函数：通过`tc qdisc replace dev $MAIN_IF root fq_pie`实际应用FQ-PIE到网卡
- 降级时创建`fq-pie-qdisc@${MAIN_IF}.service` systemd持久化服务
- `CAKE_FAIL_REASON`变量追踪失败原因（no_tc_command / kernel_no_module / tc_apply_failed）
- `verify_installation()`四级精确诊断：CAKE已启用 → FQ-PIE降级已生效(✅) → tc应用失败(⚠️) → 内核缺模块(⚠️)
- `print_summary()`和`cmd_optimize()`同步更新三级显示

---

## 历史更新内容 (v1.0.74)

### 修复：geoip/geosite在sing-box 1.12+已移除，导致singbox启动失败

**问题**: 升级sing-box到1.13.9后，config_generator.py和subscription_service.py仍使用`geoip`/`geosite`内联规则格式，sing-box 1.12.0已彻底移除该格式，导致FATAL错误

**修复**: 
- config_generator.py：删除`{"geoip":"cn"}`和`{"geosite":"cn"}`规则
- subscription_service.py：DNS和路由规则改用`rule_set`远程规则集格式

### 修复：CAKE降级方案从FQ改为FQ-PIE

**问题**: 内核不支持CAKE时降级为`fq`，但`fq_pie`比`fq`更适应高丢包环境

**修复**: `net.core.default_qdisc=fq` → `net.core.default_qdisc=fq_pie`

---

## 服务器标准操作流程 (SOP)

### 启动前状态检查
```bash
systemctl status singbox singbox-sub singbox-cdn
ss -tlnp | grep -E '443|8443|2053|2083|2087'
iptables -L INPUT -n | head -1
bash /root/singbox-eps-node/scripts/health_check.sh
```

### 故障恢复流程
1. **服务挂了**: 健康检查5分钟内自动重启
2. **手动恢复**: `bash /root/singbox-eps-node/scripts/health_check.sh`
3. **重装恢复**: 
   ```bash
   cd /root/singbox-eps-node
   systemctl restart singbox singbox-sub singbox-cdn
   python3 -c "from scripts.config import save_port_lock; save_port_lock()"
   bash scripts/health_check.sh
   ```

### 新VPS部署流程
1. 克隆代码到 `/root/singbox-eps-node/`
2. 创建 `.env` 文件，填入所有环境变量（SERVER_IP会自动检测）
3. 运行 `python3 scripts/config_generator.py` 生成singbox配置
4. 运行 `python3 scripts/cert_manager.py --cf-cert` 申请证书
5. 运行 `python3 scripts/cert_manager.py --setup-iptables` 设置HY2端口跳跃
6. 启动服务: `systemctl start singbox singbox-sub singbox-cdn`
7. 验证: `bash scripts/health_check.sh`

---

## 当前服务状态
- **singbox**: active (端口443/8443/2053/2083)
- **singbox-sub**: active (HTTPS://0.0.0.0:2087，走CDN)
- **singbox-cdn**: active (每小时指定DNS解析更新优选IP)
- **iptables**: INPUT默认ACCEPT（全放行）
- **acme.sh**: 自动续期已配置 (每天8:48)
- **健康检查**: 每5分钟自动执行

## 订阅链接
- **域名（推荐，走CDN）**: https://{CF_DOMAIN}:2087/sub/{COUNTRY_CODE}
- **sing-box JSON**: https://{CF_DOMAIN}:2087/singbox/{COUNTRY_CODE}
- **证书**: Let's Encrypt正式证书（通配符域名），域名访问自动匹配
- ⚠️ **禁止用IP访问**: IP访问会导致SSL证书域名不匹配

## 节点列表（5个用户可见节点）
1. ePS-{CC}-VLESS-Reality: {SERVER_IP}:443 (直连)
2. ePS-{CC}-VLESS-WS-CDN: 优选IP:8443 (CDN)
3. ePS-{CC}-VLESS-HTTPUpgrade-CDN: 优选IP:2053 (CDN)
4. ePS-{CC}-Trojan-WS-CDN: 优选IP:2083 (CDN)
5. ePS-{CC}-Hysteria2: {SERVER_IP}:443 (直连，端口跳跃21000-21200→443，UDP+TCP)

⚠️ AI-SOCKS5不是用户可见节点，是幕后路由出站

## 核心目录
```
/root/singbox-eps-node/
├── .env                    # 环境变量
├── config.json             # singbox配置文件
├── cert/                   # SSL证书
├── data/
│   ├── singbox.db          # SQLite数据库
│   └── .port_lock          # 端口锁定文件
├── scripts/
│   ├── config.py           # 全局配置
│   ├── logger.py           # 日志管理
│   ├── cdn_monitor.py      # CDN监控
│   ├── subscription_service.py  # 订阅服务
│   ├── config_generator.py # 配置生成器
│   ├── cert_manager.py     # 证书管理
│   ├── tg_bot.py           # Telegram机器人
│   └── health_check.sh     # 健康检查
├── logs/
└── backups/
```

## 端口分配表
| 端口 | 服务 | CDN支持 | 用途 |
|------|------|---------|------|
| 443 | singbox | ✅ | VLESS-Reality + Hysteria2 |
| 2053 | singbox | ✅ | VLESS-HTTPUpgrade |
| 2083 | singbox | ✅ | Trojan-WS |
| 2087 | singbox-sub | ✅ | 订阅服务（走CDN） |
| 8443 | singbox | ✅ | VLESS-WS |
| 1080 | singbox | ❌ | SOCKS5本地代理 |
| 21000-21200 | iptables→443 | ❌ | Hysteria2端口跳跃（UDP+TCP） |

## .env 必需变量清单
```
SERVER_IP=          # 服务器公网IP（留空则自动检测）
CF_DOMAIN=          # Cloudflare域名
VLESS_UUID=         # VLESS-Reality UUID
VLESS_WS_UUID=      # VLESS-WS/HTTPUpgrade UUID
TROJAN_PASSWORD=    # Trojan-WS密码
HYSTERIA2_PASSWORD= # Hysteria2密码
REALITY_PRIVATE_KEY=# Reality私钥
REALITY_PUBLIC_KEY= # Reality公钥
CF_API_TOKEN=       # Cloudflare API Token
AI_SOCKS5_SERVER=   # AI SOCKS5服务器（可选）
AI_SOCKS5_PORT=     # AI SOCKS5端口（可选）
AI_SOCKS5_USER=     # AI SOCKS5用户名（可选）
AI_SOCKS5_PASS=     # AI SOCKS5密码（可选）
COUNTRY_CODE=       # 国家代码（安装时自动检测）
SUB_TOKEN=          # 订阅Token（可选）
```

## 下一步待办
- [ ] 部署v1.0.75到服务器并验证CAKE/FQ-PIE状态
- [ ] 开发SOCKS5自动切换功能（需要更多节点）
