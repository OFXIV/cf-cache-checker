# CF Cache Checker(适用于免费CDN)

一个用于检测 Cloudflare 缓存状态的小脚本，支持在线 CSV 或本地 CSV 输入

---

## 功能

- 检测 URL 是否被 Cloudflare 缓存（HIT/MISS）。
- MISS 时可下载文件触发缓存（可配置保留或删除）。
- 支持多列批量检测（如音乐文件 URL、封面、歌词）。
- 并发检测，默认 5 个任务同时进行。
- 清除错误文件网址缓存

---

## 安装与运行

### 1. 安装 Python 3

```bash
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
pip3 install pandas aiohttp requests pyyaml tqdm
```
### 4. 配置
编辑 `config.yaml`：

```yaml
csv_url: "https://docs.google.com/spreadsheets/d/.../export?format=csv&gid=0"
max_concurrent: 5
download_if_miss: true
head_wait_seconds: 1
columns: ["url", "cover", "lrc"]
keep_downloaded_file: false
download_dir: "downloads"
output_csv: "output_cache_status.csv"
auto_purge_cf_cache: false 
cf_api_url: "https://api.cloudflare.com/client/v4"  
cf_api_token: "your_cf_api_token_here"             
cf_zone_id: "your_cf_zone_id_here"                 
```
- csv_url：在线 CSV 或本地 CSV 文件路径
- max_concurrent：并发数量
- download_if_miss：MISS 时是否下载完整文件触发缓存
- head_wait_seconds：下载后等待多久再进行 HEAD 检测 (秒)
- keep_downloaded_file：下载文件是否保留
- download_dir：下载文件的存放目录（仅当 keep_downloaded_file 为 true 时生效）
- columns：表格中需要检测的列
- output_csv：输出结果文件名
- auto_purge_cf_cache：是否开启自动清除 CF 缓存
- cf_api_url：cf缓存清除默认 API 地址
- cf_api_token：cf实际 API Token
- cf_zone_id：托管在cf上域名的Zone ID
### 5. 运行
```bash
python3 check_cache.py
```
输出示例：
```arduino
在线表格已加载: (98, 6)
检测进度: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████| 294/294 [00:00<00:00, 771.75it/s]✅ 检测完成，结果已保存到 output_cache_status.csv
```
---
## 注意事项

1. 对于大型文件，如果开启 download_if_miss: true，下载可能占用大量带宽。

2. 表格列必须存在，否则会报错。

3. 对于 Google Sheets，请使用 CSV 导出链接，确保公开访问。

4. 自行决定要不要开错误url自动清除cf缓存，免费CDN缓存清除API调用有限
---
### 文件结构示例
```bash
cf_cache_checker/
├─ check_cache.py       # 脚本主文件
├─ config.yaml          # 配置文件
└─ README.md            # 使用说明

```

