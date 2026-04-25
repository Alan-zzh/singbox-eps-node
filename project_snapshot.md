# Singbox EPS Node 项目快照

**版本**: v3.0.1 | **更新**: 2026-04-26

---

## 当前状态

### 服务状态
| 服务 | 状态 | 说明 |
|------|------|------|
| singbox | ✅ | 代理内核，5个入站协议 |
| singbox-sub | ✅ | HTTPS订阅服务，端口2087 |
| singbox-cdn | ✅ | CDN优选IP学习系统，每小时自动测试+评分+择优 |

### 核心功能
- ✅ 5个代理协议：VLESS-Reality, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, Hysteria2
- ✅ CDN优选IP：v3.0学习系统（用户投喂+自动验证+历史评分+自动淘汰）
- ✅ CDN每小时自动更新：cdn_monitor.py while循环 + 进程锁防重复
- ✅ CDN IP自动同步：cdn_monitor写数据库 → subscription_service实时读取 → 用户更新订阅即可
- ✅ IP性能数据库：每个IP独立记录历史延迟/成功率/连续失败次数
- ✅ 综合评分算法：平均延迟40% + 成功率30% + 稳定性20% + 新鲜度10%
- ✅ 自动淘汰机制：连续5次失败降权，连续3天不达标移出优选池
- ✅ 用户投喂通道：config.py的IP池作为候选池，脚本自动验证后入库
- ✅ 黑名单机制：用户手动标记不好的IP直接跳过
- ✅ 不依赖IP段前缀：完全基于历史表现数据，越用越准
- ✅ SOCKS5 AI路由：13个AI域名走住宅代理，X/推特/groK排除
- ✅ 故障转移：AI-SOCKS5不可用时自动fallback到direct
- ✅ HY2端口跳跃：21000-21200→443，UDP+TCP双协议
- ✅ SSL证书：fullchain.pem优先，降级cert.pem
- ✅ 按月流量统计：SQLite持久化，每月14号归零
- ✅ BBR+FQ+CAKE三合一加速
- ✅ 旧面板彻底卸载：S-UI/JSUI/x-ui/marzban/3x-ui
- ✅ 一键诊断脚本：diagnose.sh 14项检查，覆盖服务/端口/证书/防火墙/DNS/CDN等

### CDN优选IP学习系统（v3.0）
**工作流：**
```
用户每天投喂新IP → 加入config.py候选池
                          ↓
                    脚本每小时自动执行
                          ↓
        所有候选IP TCP连通测试 → 写入性能数据库
                          ↓
  综合评分(延迟40%+成功率30%+稳定性20%+新鲜度10%)
                          ↓
          自动淘汰不达标IP（连续5次失败/3天无成功）
                          ↓
              取评分最高的前5个
                          ↓
            更新订阅，用户无感知切换
```

**评分算法：**
| 维度 | 权重 | 说明 |
|------|------|------|
| 平均延迟 | 40% | 0-100ms满分，>500ms为0分 |
| 成功率 | 30% | 成功次数/总测试次数 |
| 稳定性 | 20% | 连续失败次数扣分（每次-20分） |
| 新鲜度 | 10% | 最近3天有成功记录得满分，否则递减 |

**淘汰规则：**
- 连续5次失败 → 降权
- 成功率<20%（测试>10次后）→ 淘汰
- 连续3天无成功记录（测试>5次后）→ 淘汰
- 用户手动加入黑名单 → 直接跳过

**数据来源：**
- 用户投喂候选池（config.py的CDN_PREFERRED_IPS）
- 外部API补充（vvhan/090227/001315/WeTest/IPDB）
- 全部统一测试、统一评分、公平竞争

### 定时任务
| 任务 | 频率 | 说明 |
|------|------|------|
| health_check.sh | 每5分钟 | config.json自愈+端口/服务/订阅/防火墙/证书/磁盘 |
| cert_manager.py --renew | 每月1号凌晨3点 | SSL证书自动续签 |

### 三层自愈机制（v3.0.1新增）
| 层级 | 机制 | 触发条件 | 恢复动作 |
|------|------|----------|----------|
| 第1层 | systemd ExecStartPre | singbox启动时config.json不存在 | 自动运行config_generator.py |
| 第2层 | health_check.sh | 每5分钟crontab检查 | config.json缺失→自动生成+重启singbox |
| 第3层 | StartLimitBurst=5 | singbox连续崩溃 | 60秒内最多重启5次 |

### 路由规则顺序（客户端）
1. DNS规则
2. 私有地址直连
3. 国内直连（rule_set）
4. X/推特/groK排除（走ePS-Auto，不走SOCKS5）
5. AI网站（走ai-residential→AI-SOCKS5，故障转移direct）
6. final: ePS-Auto

### 路由规则顺序（服务端）
1. X/推特/groK排除（走direct）
2. AI网站（走ai-residential→AI-SOCKS5，故障转移direct）
3. final: direct

---

## 近期Bug修复

| Bug# | 版本 | 问题 | 修复 |
|------|------|------|------|
| #28 | v1.0.82 | AI规则含google.com导致延迟高 | 移除通用google域名 |
| #29 | v1.0.82 | CDN返回104段高延迟 | 001315优先+104段严格过滤 |
| #30 | v1.0.82 | config_generator与sub不同步 | 两个文件必须同步更新 |
| #31 | v1.0.82 | CDN更新服务卡住 | crontab每小时重启singbox-cdn |
| #32 | v1.0.83 | config_generator缺DNS和final | 添加DNS+final:direct |
| #33 | v1.0.83 | S-UI残留进程和目录 | 删服务文件+目录+杀进程 |
| #34 | v1.0.84 | CDN重启crontab未写入install.sh | install.sh加crontab兜底 |
| #35 | v1.0.85 | CDN本地池混入104.x.x.x高延迟IP | 移除104段，替换为162.159/172.64段 |
| #36 | v1.0.85 | cert_manager续签后漏重启singbox-cdn | restart_singbox()加singbox-cdn |
| #37 | v1.0.85 | health_check漏检UDP端口(HY2) | 增加UDP 443检查 |
| #38 | v1.0.85 | cdn_monitor数据库连接泄漏 | init_db()改try/finally |
| #39 | v1.0.85 | 414MB内存无Swap，OOM killer杀进程 | 创建2GB Swap+禁用fwupd |
| #40 | v1.0.85 | HUNAN_CT_OPTIMAL_PREFIXES含未验证段 | 移除8.39/8.35，001315也加过滤 |
| #43 | v2.2.0 | CDN外部API高分IP实际延迟高(50-68ms) | HTTP真实延迟测试为主排序，外部API仅作候选收集 |
| #44 | v3.0.0 | CDN评分依赖理论值，不反映真实表现 | 重构为学习系统：IP性能数据库+综合评分+自动淘汰+用户投喂 |
| #45 | v3.0.1 | health_check.sh无执行权限，健康检查完全失效 | install.sh添加chmod +x |
| #46 | v3.0.1 | fwupd-refresh.timer未禁用，fwupd反复重启触发OOM | mask service+timer |
| #47 | v3.0.1 | api.vvhan.com DNS失效(NXDOMAIN) | 已有降级处理，无需代码修改 |
| #48 | v3.0.1 | config.json不存在导致singbox重启46次 | 重新生成+修复health_check权限 |
| #49 | v3.0.1 | Windows CRLF换行符导致shell脚本无法执行 | sed -i 's/\r$//' 转换 |
| #50 | v3.0.1 | systemd ExecStartPre中cd+相对路径解析错误 | 改用绝对路径 |
| #51 | v3.0.1 | cdn_monitor.py进程泄漏，5个孤儿进程浪费80MB | 加进程锁+删crontab重启 |
| #52 | v3.0.1 | VPS系统服务浪费60MB+内存 | 禁用multipathd/caddy/ModemManager等 |

---

## 关键避坑记录

1. DNS服务器detour必须为direct，不能走代理（Bug #23）
2. AI规则禁止包含通用域名如google.com（Bug #28）
3. 排除规则必须在AI规则之前（Bug #25）
4. 104.x.x.x段必须严格过滤，不能"全部保留"（Bug #29）
5. ~~CDN服务必须crontab兜底重启~~ 已废弃：cdn_monitor.py加进程锁后不再需要crontab重启（Bug #31→#51）
6. 修改subscription_service.py必须同步修改config_generator.py（Bug #30）
7. 修复服务器问题必须同步更新install.sh（Bug #34）
8. 卸载旧面板必须彻底：stop+disable+删服务文件+删目录+杀进程+daemon-reload（Bug #33）
9. CDN本地IP池也必须过滤104.x.x.x段，不能因为"本地池"就放松过滤标准（Bug #35）
10. 服务重启必须覆盖所有相关服务：singbox + singbox-sub + singbox-cdn，包括cert_manager续签场景（Bug #36）
11. 健康检查必须覆盖UDP端口，HY2/QUIC使用UDP 443（Bug #37）
12. 数据库连接必须在finally中关闭，即使init_db()这种简单函数也不能例外（Bug #38）
13. 414MB小内存VPS必须配Swap（2GB），否则OOM killer会杀掉singbox进程导致掉线（Bug #39）
14. fwupd服务在小内存VPS上必须mask，它占用144MB会触发OOM（Bug #39）
15. singbox日志必须配logrotate，否则日志膨胀占满磁盘（运维#1）
16. HUNAN_CT_OPTIMAL_PREFIXES只包含实测确认的优质段：162.159/172.64/108.162/198.41/173.245，001315 API返回的非优质段IP也必须过滤（Bug #40修正）
17. CDN优选IP必须以真实HTTP延迟测试为准，外部API仅提供候选IP，不直接给高分（Bug #43）
18. CDN优选IP不能依赖IP段前缀打分，必须基于历史表现数据（Bug #44）
19. CDN学习系统必须记录每个IP的性能历史，否则无法做综合评分和自动淘汰（Bug #44）
20. 安装脚本添加crontab前必须先chmod +x，Git上传的脚本文件默认无执行权限（Bug #45）
21. 禁用服务时必须同时禁用其timer，否则timer会重新拉起service。systemctl mask要覆盖service+timer（Bug #46）
22. 外部API随时可能失效（如vvhan），必须有降级方案。多数据源+本地池冗余设计是正确的（Bug #47）
23. config.json被删时health_check应能自动重新生成，部署操作后必须验证config.json存在（Bug #48）
24. 从Windows上传shell脚本到Linux后必须转换换行符：sed -i 's/\r$//' （Bug #49）
25. systemd服务文件中所有路径必须使用绝对路径，禁止cd+相对路径组合（Bug #50）
26. 守护进程必须加进程锁（fcntl.flock），防止多实例运行导致内存泄漏（Bug #51）
27. VPS部署后必须禁用无用系统服务：multipathd/ModemManager/udisks2/caddy/unattended-upgrades（Bug #52）
