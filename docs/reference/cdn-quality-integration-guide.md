# CDN质量筛选器 - 集成指南

## 文件清单

```
scripts/
├── cdn_quality_filter.py      # 新增：CDN质量筛选器类
├── test_cdn_quality_filter.py # 新增：基础测试脚本
└── test_cdn_extreme_conditions.py  # 新增：极端网络波动测试
```

## 集成步骤

### 1. 修改配置文件 `.env.example` / `.env`

```env
# 用户DDNS域名（用于锚定用户位置和网络状态）
USER_DDNS_DOMAIN=
# 用户预期运营商（用于验证IP归属地）
USER_EXPECTED_ISP=电信
```

### 2. 部署时配置 install.sh（已自动完成）

install.sh 已包含：
- 创建数据库表 user_network_state
- 配置环境变量
- 启动服务

### 3. 订阅服务已集成（已完成）

subscription_service.py 已自动集成：
- 全局单例 `get_cdn_quality_filter()`
- 硬淘汰检查（`hard_reject_current`）
- 自动筛选（`filter_and_rank`）

## 使用说明

### 硬淘汰阈值（config.py 中）

```python
CDN_IP_HARD_REJECT = {
    'latency_ms': 100,           # VPS→CF延时>100ms → 淘汰
    'user_path_latency_ms': 100, # 用户路径延时>100ms → 淘汰
    'packet_loss_rate': 0.1,     # 失败率>10% → 淘汰
    'download_speed_mbps': 20,   # 下载速度<20Mbps → 淘汰
}
```

### 用户质量阈值（config.py 中）

```python
USER_QUALITY_THRESHOLD = {
    'latency_ms': 100,
    'packet_loss_rate': 0.05,
    'download_speed_mbps': 20,
}
```

## 验证方法

### 1. 本地运行测试

```bash
# 基础测试
python scripts/test_cdn_quality_filter.py

# 极端网络波动测试
python scripts/test_cdn_extreme_conditions.py
```

### 2. 部署后验证

在服务器上查看日志：

```bash
# 订阅服务日志
journalctl -u singbox-sub -f

# CDN监控日志
journalctl -u singbox-cdn -f
```

## 注意事项

### 1. 数据库兼容性

- CdnQualityFilter 使用现有数据库：`data/singbox.db`
- 自动创建所需表：`user_network_state`（如果不存在）
- 不会影响现有数据

### 2. 性能开销

- 筛选器有5分钟缓存
- `filter_and_rank` 对100个IP约65ms
- 建议CDN IP池保持在20-50个IP

### 3. 降级逻辑

- 如果 `CdnQualityFilter` 初始化失败，自动降级到现有随机选IP
- 如果配置缺失，使用默认阈值

### 4. CDN监控集成

建议在 `cdn_monitor.py` 中也集成 `CdnQualityFilter`（可选）：
- 筛选候选IP时应用硬淘汰
- 评分排序时使用七维评分

## API接口

```python
from cdn_quality_filter import CdnQualityFilter

# 初始化
cqf = CdnQualityFilter(
    db_path='data/singbox.db',
    ddns_domain='your.domain.com',
)

# 硬淘汰检查
rejected, reason = cqf.hard_reject(ip='162.159.1.1')

# 筛选并排序
ranked = cqf.filter_and_rank(['162.159.1.1', '172.64.1.1'])

# 选最优3个（从Top5随机）
best = cqf.select_best_ips(ip_list, count=3)
```
