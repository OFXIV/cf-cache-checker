import pandas as pd
import aiohttp
import asyncio
import tempfile
import os
from io import StringIO
import requests
import yaml
import aiofiles

# -------------------------
# 读取配置
# -------------------------
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if os.path.exists("config_local.yaml"):
        with open("config_local.yaml", "r", encoding="utf-8") as f:
            local_config = yaml.safe_load(f)
            config.update(local_config)
    return config

config = load_config()

CSV_URL = config.get("csv_url")
MAX_CONCURRENT = config.get("max_concurrent", 5)
DOWNLOAD_IF_MISS = config.get("download_if_miss", False)
RETRY_TIMES = config.get("retry_times", 2)
COLUMNS = config.get("columns", ["url", "cover", "lrc"])
SAVE_FILE = config.get("keep_downloaded_file", False)
DOWNLOAD_DIR = config.get("download_dir", "downloads")
AUTO_PURGE_CF_CACHE = config.get("auto_purge_cf_cache", False)

CF_API_URL = config.get("cf_api_url")
CF_API_TOKEN = config.get("cf_api_token")
CF_ZONE_ID = config.get("cf_zone_id")

# -------------------------
# 读取 CSV
# -------------------------
if CSV_URL.startswith("http"):
    r = requests.get(CSV_URL)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
elif os.path.exists(CSV_URL):
    df = pd.read_csv(CSV_URL)
else:
    raise ValueError(f"CSV_URL 无效或文件不存在: {CSV_URL}")

for col in COLUMNS:
    if col not in df.columns:
        raise ValueError(f"列 '{col}' 在 CSV 中不存在")

# -------------------------
# 判断内容是否是错误页面
# -------------------------
def is_error_content(chunk: bytes) -> bool:
    text = chunk.lower()
    return b"<html" in text or b"{\"code\"" in text or b"failed" in text

# -------------------------
# 异步下载文件
# -------------------------
async def download_file(session, url, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    async with session.get(url, timeout=60) as resp:
        async with aiofiles.open(filename, "wb") as f:
            async for chunk in resp.content.iter_chunked(1024 * 1024):
                await f.write(chunk)

# -------------------------
# 批量 CF 清理缓存
# -------------------------
async def purge_cf_cache(urls):
    if not all([CF_API_URL, CF_API_TOKEN, CF_ZONE_ID]):
        print("⚠️ CF API 配置不完整，无法清除缓存")
        return
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
        payload = {"files": urls}
        async with session.post(f"{CF_API_URL}/zones/{CF_ZONE_ID}/purge_cache", json=payload, headers=headers) as resp:
            if resp.status == 200:
                print(f"✅ 自动清除 {len(urls)} 个 URL 缓存成功")
            else:
                text = await resp.text()
                print(f"⚠️ 自动清除缓存失败: {text}")

# -------------------------
# 异步检测 URL（多轮 HIT/MISS）
# -------------------------
async def check_url(session, url, col, error_urls):
    for attempt in range(RETRY_TIMES + 1):
        try:
            async with session.get(url, timeout=30) as resp:
                cf_status = resp.headers.get("cf-cache-status", "").upper() or "HIT"
                age = resp.headers.get("age", "0")
                content_type = resp.headers.get("content-type", "")

                # HTML/JSON/错误返回视为失败
                if "text/html" in content_type.lower() or "application/json" in content_type.lower():
                    raise ValueError("返回 HTML/JSON")

                # 尝试读取前几个字节，验证能获取内容
                try:
                    chunk = await resp.content.read(64)
                    if is_error_content(chunk):
                        raise ValueError("前几个字节判定为错误内容")
                except Exception:
                    pass

                print(f"[SUCCESS] col: {col} | {cf_status} | age: {age} | url: {url}")
                return "SUCCESS"

        except Exception as e:
            if attempt < RETRY_TIMES:
                print(f"[WARN] col: {col} | url: {url} | 尝试 {attempt + 1}/{RETRY_TIMES} | cf_status: {cf_status if 'cf_status' in locals() else 'N/A'} | 错误: {e}")
                await asyncio.sleep(0.5)
            else:
                print(f"[ERROR] col: {col} | url: {url} | 尝试 {attempt + 1}/{RETRY_TIMES} | cf_status: {cf_status if 'cf_status' in locals() else 'N/A'} | 错误: {e}")
                error_urls.append(url)
                return "ERROR"

# -------------------------
# 异步 worker
# -------------------------
async def worker(sem, session, url, col, error_urls):
    async with sem:
        result = await check_url(session, url, col, error_urls)
        if result == "ERROR" and DOWNLOAD_IF_MISS:
            tmp_file = os.path.join(DOWNLOAD_DIR, os.path.basename(url)) if SAVE_FILE else tempfile.NamedTemporaryFile(delete=False).name
            await download_file(session, url, tmp_file)
            if not SAVE_FILE:
                os.remove(tmp_file)

# -------------------------
# 主函数
# -------------------------
async def main():
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        error_urls = []
        tasks = [
            worker(sem, session, row[col], col, error_urls)
            for col in COLUMNS for _, row in df.iterrows() if pd.notna(row[col])
        ]
        await asyncio.gather(*tasks)

        if AUTO_PURGE_CF_CACHE and error_urls:
            print(f"⚠️ 检测到 {len(error_urls)} 个错误 URL，开始批量清除 CF 缓存...")
            await purge_cf_cache(error_urls)
        elif error_urls:
            print(f"⚠️ 检测到 {len(error_urls)} 个错误 URL")

    print("✅ 检测完成。")

if __name__ == "__main__":
    asyncio.run(main())
