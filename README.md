# CF Cache Checker

一个用于检测Cloudflare CDN缓存状态的Python脚本工具，支持批量检测在线或本地CSV文件中的URL缓存状态。

## 技术原理

1. **缓存检测机制**：
   - 通过HTTP HEAD请求检测`CF-Cache-Status`响应头判断缓存状态(HIT/MISS)
   - 检查`Age`响应头获取缓存存在时间(秒)
   - 自动重试机制提高检测准确性

2. **缓存预热功能**：
   - 可配置自动下载MISS资源以触发Cloudflare边缘节点缓存
   - 下载完成后等待指定时间再次检测确认缓存状态

3. **缓存清除功能**：
   - 集成Cloudflare API自动清除错误URL的缓存
   - 支持批量清除操作

> **注意事项**：
> - Cloudflare采用区域性边缘缓存，检测结果反映的是离客户端最近的边缘节点状态
> - 免费计划的`Range`请求不会被缓存

## 功能

- 检测 URL 是否被 Cloudflare 缓存（HIT/MISS）
- 支持多列批量检测
- 并发检测，默认 5 个任务同时进行
- 增加清除错误文件网址 `CF` 缓存（需要配置开启）
- 自动下载 MISS 资源以触发缓存（可配置）
- 详细的日志记录和结果输出
- 支持重试机制，提高检测准确性

## 安装与运行

### 1. 安装 Python 3

确保已安装 Python 3.7 或更高版本：

```
python3 --version
```
未安装请先安装 Python 3
### 2. 克隆仓库或下载脚本
```bash
git clone https://github.com/OFXIV/cf-cache-checker.git
cd cf-cache-checker
```
### 3. 安装依赖
```bash
pip3 install pandas aiohttp requests pyyaml aiofiles
```
### 4. 配置

编辑 `config.yaml` 文件，以下是完整的配置参数说明：

```yaml
# 必需配置
csv_url: "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0"  # 在线CSV URL或本地CSV文件路径
columns: ["url", "cover", "lrc"]  # 需要检测的URL列名列表

# 性能调优配置
max_concurrent: 5                 # 并发请求数 (1-20)
retry_times: 2                    # 失败重试次数 (0-5)
head_wait_seconds: 1              # 下载后等待检测时间(秒)

# 缓存预热配置
download_if_miss: false           # 是否下载MISS资源触发缓存
keep_downloaded_file: false       # 是否保留下载的文件
download_dir: "downloads"         # 下载文件保存目录

# Cloudflare API配置
auto_purge_cf_cache: false        # 是否自动清除错误URL的缓存
cf_api_url: "https://api.cloudflare.com/client/v4"  # API端点
cf_api_token: "your_cf_api_token_here"             # API令牌
cf_zone_id: "your_cf_zone_id_here"                 # 区域ID

# 输出配置
output_csv: "output_cache_status.csv"  # 结果输出文件名
```

#### 配置示例

1. **基本使用** (仅检测缓存状态):
```yaml
csv_url: "data/urls.csv"
columns: ["image_url", "video_url"]
max_concurrent: 3
```

2. **缓存预热** (自动下载MISS资源):
```yaml
csv_url: "https://example.com/data.csv"
columns: ["url"]
download_if_miss: true
head_wait_seconds: 3
```

3. **自动清除缓存** (需要有效API凭证):
```yaml
csv_url: "urls_to_check.csv"
columns: ["url"]
auto_purge_cf_cache: true
cf_api_token: "abc123..."
cf_zone_id: "xyz456..."
```

> **获取Cloudflare API凭证**:
> 1. 登录Cloudflare仪表盘
> 2. 进入"我的个人资料" > "API令牌"
> 3. 创建具有"Zone.Cache Purge"权限的令牌
> 4. 区域ID可在域名的概述页面找到
### 5. 运行
```bash
python3 check_cache.py
```
输出示例：
```
[ERROR] col: cover | url: https://example.com/xxx1.jpg | 尝试 3/2 | cf_status: HIT | 错误: 返回 HTML/JSON
[SUCCESS] col: cover | HIT | age: 4191 | url: https://example.com/xxx.jpg
⚠️ 检测到 1 个错误 URL，开始批量清除 CF 缓存...
✅ 自动清除 1 个 URL 缓存成功
✅ 检测完成。
```
---

## 常见问题解答

### Q1: 为什么检测结果不稳定？
- Cloudflare边缘节点缓存可能不一致
- 资源未完全预热时可能出现部分MISS
- 建议开启重试机制(retry_times)提高准确性

### Q2: 如何提高检测速度？
- 适当增加max_concurrent值(建议5-10)
- 减少head_wait_seconds(最小0.5秒)
- 关闭不需要的功能(download_if_miss=false)

### Q3: API调用失败怎么办？
- 检查API Token权限是否正确
- 验证Zone ID是否匹配当前域名
- Cloudflare API有速率限制，请勿频繁调用

### Q4: 如何验证检测准确性？
- 手动访问几个HIT/MISS的URL
- 检查响应头中的CF-Cache-Status
- 比较脚本输出与实际观察结果

## 注意事项

1. 对于大型文件，如果开启 download_if_miss: true，下载可能占用大量带宽。

2. 表格列必须存在，否则会报错。

3. 对于 Google Sheets，请使用 CSV 导出链接，确保公开访问。

4. 自行决定要不要开错误url自动清除cf缓存，免费CDN缓存清除API调用有限

## 贡献指南

欢迎通过以下方式参与项目改进：

1. **报告问题**:
   - 在GitHub Issues中描述遇到的问题
   - 提供复现步骤和环境信息

2. **功能建议**:
   - 提出清晰的功能需求描述
   - 说明使用场景和预期效果

3. **代码贡献**:
   ```bash
   # 开发环境设置
   git clone https://github.com/OFXIV/cf-cache-checker.git
   cd cf-cache-checker
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate    # Windows
   pip install -e .[dev]
   ```

4. **测试要求**:
   - 新功能需包含单元测试
   - 通过所有现有测试: `pytest tests/`

5. **代码风格**:
   - 遵循PEP 8规范
   - 使用类型注解(Type Hints)
   - 提交前运行: `flake8 .` 和 `mypy .`

## 开发说明

### 核心模块架构

```
check_cache.py
├── ConfigManager        # 配置加载与管理
├── CSVProcessor         # CSV数据处理
├── URLChecker          # URL检测核心逻辑
├── ContentValidator     # 内容验证
├── CloudflareCacheManager # CF API交互
└── CacheCheckController # 主控制流程
```

### 扩展开发建议

1. **支持更多CDN服务商**:
   - 继承基类实现新的CacheManager
   - 添加对应的检测逻辑

2. **增强结果处理**:
   - 实现结果存储到数据库
   - 添加更丰富的分析指标

3. **性能优化方向**:
   - 使用连接池管理HTTP请求
   - 实现更智能的并发控制

---
### 文件结构示例
```bash
cf_cache_checker/
├─ check_cache.py       # 脚本主文件
├─ config.yaml          # 配置文件
└─ README.md            # 使用说明
