# Singbox EPS Node 项目快照

**版本**: v1.0.85 | **更新**: 2026-04-25

---

## 当前状态

### 服务状态
| 服务 | 状态 | 说明 |
|------|------|------|
| singbox | ✅ | 代理内核，5个入站协议 |
| singbox-sub | ✅ | HTTPS订阅服务，端口2087 |
| singbox-cdn | ✅ | CDN优选IP监控，每小时更新，crontab兜底重启 |

### 核心功能
- ✅ 5个代理协议：VLESS-Reality, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, Hysteria2
- ✅ CDN优选IP：4级降级保障（001315→WeTest→IPDB→本地池）
- ✅ CDN每小时自动更新：cdn_monitor.py while循环 + crontab每小时重启兜底
- ✅ CDN IP自动同步：cdn_monitor写数据库 → subscription_service实时读取 → 用户更新订阅即可
- ✅ SOCKS5 AI路由：13个AI域名走住宅代理，X/推特/groK排除
- ✅ 故障转移：AI-SOCKS5不可用时自动fallback到direct
- ✅ HY2端口跳跃：21000-21200→443，UDP+TCP双协议
- ✅ SSL证书：fullchain.pem优先，降级cert.pem
- ✅ 按月流量统计：SQLite持久化，每月14号归零
- ✅ BBR+FQ+CAKE三合一加速
- ✅ 旧面板彻底卸载：S-UI/JSUI/x-ui/marzban/3x-ui
- ✅ 一键诊断脚本：diagnose.sh 14项检查，覆盖服务/端口/证书/防火墙/DNS/CDN等

### CDN优选IP获取策略（规则8）
1. cf.001315.xyz/ct电信API（返回173.245等优质段，优先）
2. WeTest.vip电信优选DNS（DoH解析，104段严格过滤后丢弃）
3. IPDB API bestcf（补充）
4. 本地实测IP池（兜底，162.159.x.x/172.64.x.x段）

### 定时任务
| 任务 | 频率 | 说明 |
|------|------|------|
| health_check.sh | 每5分钟 | 端口/服务/订阅/防火墙/证书/磁盘 |
| singbox-cdn重启 | 每小时0分 | Bug #31兜底，防止time.sleep卡住 |
| cert_manager.py --renew | 每月1号凌晨3点 | SSL证书自动续签 |

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

---

## 关键避坑记录

1. DNS服务器detour必须为direct，不能走代理（Bug #23）
2. AI规则禁止包含通用域名如google.com（Bug #28）
3. 排除规则必须在AI规则之前（Bug #25）
4. 104.x.x.x段必须严格过滤，不能"全部保留"（Bug #29）
5. CDN服务必须crontab兜底重启，time.sleep会卡住（Bug #31）
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
