# CF Cache Checker

一个用于检测Cloudflare CDN缓存状态的Python脚本工具，支持批量检测在线或本地CSV文件中的URL缓存状态，并提供缓存预热和自动清除功能。

> -脚本直接请求链接：无法保证 HIT，每次可能 MISS / BYPASS  
> -HIT / MISS / BYPASS 是 Cloudflare 根据请求头、源站响应头、文件类型等决定的
## 功能特点

- **高效缓存检测**：通过HTTP请求检测`CF-Cache-Status`响应头判断缓存状态(HIT/MISS)
- **批量URL处理**：支持多列批量检测CSV文件中的URL
- **并发控制**：可配置并发数量，提高检测效率
- **自动重试**：内置重试机制，提高检测准确性
- **缓存预热**：可配置自动下载MISS资源以触发Cloudflare边缘节点缓存
- **自动清除**：集成Cloudflare API自动清除错误URL的缓存
- **详细日志**：提供完整的日志记录和结果输出

## 技术原理

1. **缓存检测机制**：
   - 通过HTTP请求检测`CF-Cache-Status`响应头判断缓存状态(HIT/MISS)
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

## 快速开始

### 环境要求

- Python 3.7+
- 依赖包：pandas, aiohttp, requests, PyYAML, aiofiles

### 安装步骤

1. **安装Python 3**
   确保已安装Python 3.7或更高版本：
   ```
   python3 --version
   ```

2. **下载项目**
   ```bash
   git clone https://github.com/OFXIV/cf-cache-checker.git
   cd cf-cache-checker
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置参数**
   编辑`config.yaml`文件，配置CSV文件路径和检测参数：
   ```yaml
   # CSV文件路径（在线URL或本地路径）
   csv_url: "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0"

   # 需要检测的URL列名列表
   columns:
     - url
     - cover
     - lrc

   # 并发请求数
   max_concurrent: 5

   # 失败重试次数
   retry_times: 2
   ```

5. **运行脚本**
   ```bash
   python check_cache.py
   ```

## 配置详解

### 基础配置

```yaml
# CSV文件地址（支持在线URL或本地路径）
csv_url: "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0"

# 需要检测的URL列名列表
columns:
  - url
  - cover
  - lrc

# 输出结果文件名
output_csv: "output_cache_status.csv"
```

### 性能调优配置

```yaml
# 最大并发请求数 (1-20)
max_concurrent: 5

# 失败重试次数 (0-5)
retry_times: 2

# 下载后等待检测时间(秒)
head_wait_seconds: 1
```

### 缓存预热配置

```yaml
# 是否下载MISS资源触发缓存
download_if_miss: false

# 是否保留下载的文件（默认删除）
keep_downloaded_file: false

# 下载文件保存目录（仅当keep_downloaded_file为true时生效）
download_dir: "downloads"
```

### Cloudflare API配置

```yaml
# 是否自动清除错误URL的缓存
auto_purge_cf_cache: false

# API端点
cf_api_url: "https://api.cloudflare.com/client/v4"

# API令牌
cf_api_token: "your_cf_api_token_here"

# 区域ID
cf_zone_id: "your_cf_zone_id_here"
```

### 配置示例

1. **基本使用**（仅检测缓存状态）
   ```yaml
   csv_url: "data/urls.csv"
   columns: ["image_url", "video_url"]
   max_concurrent: 3
   ```

2. **缓存预热**（自动下载MISS资源）
   ```yaml
   csv_url: "https://example.com/data.csv"
   columns: ["url"]
   download_if_miss: true
   head_wait_seconds: 3
   ```

3. **自动清除缓存**（需要有效API凭证）
   ```yaml
   csv_url: "urls_to_check.csv"
   columns: ["url"]
   auto_purge_cf_cache: true
   cf_api_token: "abc123..."
   cf_zone_id: "xyz456..."
   ```

### 获取Cloudflare API凭证

1. 登录Cloudflare仪表盘
2. 进入"我的个人资料" > "API令牌"
3. 创建具有"Zone.Cache Purge"权限的令牌
4. 区域ID可在域名的概述页面找到

## 输出示例

```bash
2025-09-04 05:15:26,561 - INFO - [SUCCESS] col: lrc | MISS | age: 0 | url: https://example.com/xxx1.jpg
2025-09-04 05:15:33,613 - WARNING - [WARN] col: lrc | url: https://example.com/xxx.jpg | 尝试 1/2 | cf_status: N/A | 错误: 
2025-09-04 05:15:40,228 - INFO - [SUCCESS] col: lrc | MISS | age: 0 | url: https://example.com/xxx.jpg
2025-09-04 05:15:40,373 - INFO - 结果已保存到 output_cache_status.csv
2025-09-04 05:15:40,374 - INFO - 检测完成。
```

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

1. 对于大型文件，如果开启`download_if_miss: true`，下载可能占用大量带宽。

2. 表格列必须存在，否则会报错。

3. 对于Google Sheets，请使用CSV导出链接，确保公开访问。

4. 免费CDN缓存清除API调用有限，请谨慎使用自动清除功能。

## 项目结构

```
cf-cache-checker/
├─ check_cache.py       # 主程序
├─ config.yaml          # 默认配置文件
├─ config_local.yaml    # 本地配置文件（可选）
├─ requirements.txt     # 依赖包列表
└─ README.md            # 使用说明
```

## 核心模块

```
check_cache.py
├── ConfigManager        # 配置加载与管理
├── CSVProcessor         # CSV数据处理
├── URLChecker          # URL检测核心逻辑
├── ContentValidator     # 内容验证
├── CloudflareCacheManager # CF API交互
├── FileDownloader      # 文件下载器
└── CacheCheckController # 主控制流程
```

## 许可证

本项目采用MIT许可证，详情请查看LICENSE文件。


