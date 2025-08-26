import pandas as pd
import aiohttp
import asyncio
import tempfile
import os
from io import StringIO
import requests
import yaml

# -------------------------
# 读取配置
# -------------------------
def load_config():
    # 默认仓库配置
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 本地配置覆盖
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

# -------------------------
# 判断 CSV_URL 是本地还是在线
# -------------------------
if CSV_URL.startswith("http"):
    try:
        r = requests.get(CSV_URL)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        print("在线表格已加载:", df.shape)
    except Exception as e:
        raise RuntimeError(f"无法获取在线 CSV: {e}")
elif os.path.exists(CSV_URL):
    try:
        df = pd.read_csv(CSV_URL)
        print("本地 CSV 已加载:", df.shape)
    except Exception as e:
        raise RuntimeError(f"无法读取本地 CSV 文件: {e}")
else:
    raise ValueError(f"CSV_URL 无效或文件不存在: {CSV_URL}")

# 确保 COLUMNS 中的列存在于表格中
for col in COLUMNS:
    if col not in df.columns:
        raise ValueError(f"列 '{col}' 在 CSV 中不存在")

# -------------------------
# 异步检测缓存
# -------------------------
async def check_cache(session, url, filename):
    try:
        async with session.head(url, timeout=15) as r:
            status = r.headers.get("cf-cache-status", "").upper()
            age = r.headers.get("age", "0")
            content_type = r.headers.get("content-type", "")
            if "text/html" in content_type:
                return "ERROR", "URL返回HTML，可能无效"

            if status == "HIT":
                return status, age
            elif status == "MISS":
                if DOWNLOAD_IF_MISS:
                    print(f"⚠️ {url} 首次 MISS，下载完整文件触发缓存...")
                    # 确保目录存在
                    if SAVE_FILE:
                        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                        file_path = os.path.join(DOWNLOAD_DIR, filename)
                    else:
                        tmp_file = tempfile.NamedTemporaryFile(delete=False)
                        file_path = tmp_file.name

                    try:
                        async with session.get(url, timeout=60) as resp:
                            with open(file_path, "wb") as f:
                                while True:
                                    try:
                                        chunk = await resp.content.read(1024*1024)
                                    except aiohttp.client_exceptions.ContentLengthError:
                                        break
                                    if not chunk:
                                        break
                                    f.write(chunk)
                        if not SAVE_FILE:
                            os.remove(file_path)

                        await asyncio.sleep(HEAD_WAIT)

                        # 再次 HEAD 检测
                        async with session.head(url, timeout=15) as r2:
                            status2 = r2.headers.get("cf-cache-status", "").upper()
                            age2 = r2.headers.get("age", "0")
                            content_type2 = r2.headers.get("content-type", "")
                            if "text/html" in content_type2:
                                return "ERROR", "URL返回HTML，可能无效"
                            return status2 or "HIT", age2
                    except Exception as e:
                        return "ERROR", str(e)
                else:
                    return status, age
            else:
                return "ERROR", f"未知状态: {status}"
    except Exception as e:
        return "ERROR", str(e)

# -------------------------
# 异步 worker
# -------------------------
async def worker(sem, session, url, col, i):
    async with sem:
        # 文件名从 URL 提取
        filename = os.path.basename(url)
        status, age = await check_cache(session, url, filename)
        df.at[i, f"{col}_cache_status"] = status
        df.at[i, f"{col}_age"] = age
        print(f"{url} → {status}, age: {age}")

# -------------------------
# 主函数
# -------------------------
async def main():
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for col in COLUMNS:
            for i, row in df.iterrows():
                url = row[col]
                if pd.notna(url):
                    tasks.append(worker(sem, session, url, col, i))
        await asyncio.gather(*tasks)

# -------------------------
# 执行
# -------------------------
asyncio.run(main())
print("✅ 检测完成")