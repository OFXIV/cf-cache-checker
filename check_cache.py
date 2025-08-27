import pandas as pd
import aiohttp
import asyncio
import tempfile
import os
from io import StringIO
import requests
import yaml
from tqdm.asyncio import tqdm_asyncio
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
DOWNLOAD_IF_MISS = config.get("download_if_miss", True)
HEAD_WAIT = config.get("head_wait_seconds", 1)
COLUMNS = config.get("columns", ["url", "cover", "lrc"])
SAVE_FILE = config.get("keep_downloaded_file", False)
DOWNLOAD_DIR = config.get("download_dir", "downloads")
AUTO_PURGE_CF_CACHE = config.get("auto_purge_cf_cache", False)
OUTPUT_CSV = config.get("output_csv", "output_cache_status.csv")

# Cloudflare API 配置
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
    print("在线表格已加载:", df.shape)
elif os.path.exists(CSV_URL):
    df = pd.read_csv(CSV_URL)
    print("本地 CSV 已加载:", df.shape)
else:
    raise ValueError(f"CSV_URL 无效或文件不存在: {CSV_URL}")

for col in COLUMNS:
    if col not in df.columns:
        raise ValueError(f"列 '{col}' 在 CSV 中不存在")

# -------------------------
# 批量 CF 清除缓存
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
# 异步检测缓存
# -------------------------
async def download_file(session, url, filename):
    async with session.get(url, timeout=60) as resp:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        async with aiofiles.open(filename, "wb") as f:
            async for chunk in resp.content.iter_chunked(1024*1024):
                await f.write(chunk)

async def check_cache(session, url, error_urls):
    try:
        async with session.head(url, timeout=15) as r:
            status = r.headers.get("cf-cache-status", "").upper()
            age = r.headers.get("age", "0")
            content_type = r.headers.get("content-type", "")

            if "text/html" in content_type:
                error_urls.append(url)
                return "⚠️ ERROR", "返回 HTML，可能无效"

            if status == "HIT":
                return "✅ SUCCESS", age

            elif status == "MISS" and DOWNLOAD_IF_MISS:
                tmp_file = None
                if SAVE_FILE:
                    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                    tmp_file = os.path.join(DOWNLOAD_DIR, os.path.basename(url))
                else:
                    tmp_file = tempfile.NamedTemporaryFile(delete=False).name

                await download_file(session, url, tmp_file)
                if not SAVE_FILE:
                    os.remove(tmp_file)
                await asyncio.sleep(HEAD_WAIT)

                async with session.head(url, timeout=15) as r2:
                    status2 = r2.headers.get("cf-cache-status", "").upper()
                    age2 = r2.headers.get("age", "0")
                    return "✅ SUCCESS", age2

            else:
                return "🟡 MISS", age

    except Exception as e:
        error_urls.append(url)
        return "⚠️ ERROR", str(e)

# -------------------------
# 异步 worker
# -------------------------
async def worker(sem, session, url, col, i, error_urls):
    async with sem:
        status, age = await check_cache(session, url, error_urls)
        df.at[i, f"{col}_cache_status"] = status
        df.at[i, f"{col}_age"] = age

# -------------------------
# 主函数
# -------------------------
async def main():
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        error_urls = []
        tasks = [
            worker(sem, session, row[col], col, i, error_urls)
            for col in COLUMNS for i, row in df.iterrows() if pd.notna(row[col])
        ]

        for f in tqdm_asyncio.as_completed(tasks, total=len(tasks), desc="检测进度"):
            await f

        if AUTO_PURGE_CF_CACHE and error_urls:
            print(f"⚠️ 检测到 {len(error_urls)} 个错误 URL，开始批量清除 CF 缓存...")
            await purge_cf_cache(error_urls)

    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"✅ 检测完成，结果已保存到 {OUTPUT_CSV}")

# -------------------------
# 执行
# -------------------------
if __name__ == "__main__":
    asyncio.run(main())
