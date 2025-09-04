import pandas as pd
import aiohttp
import asyncio
import tempfile
import os
from io import StringIO
import requests
import yaml
import aiofiles
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

# -------------------------
# 配置日志
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# -------------------------
# 数据类定义
# -------------------------
@dataclass
class Config:
    url: str
    max_concurrent: int = 5
    download_if_miss: bool = False
    retry_times: int = 2
    keep_downloaded_file: bool = False
    download_dir: str = "downloads"
    output_csv: str = "output_cache_status.csv"
    auto_purge_cf_cache: bool = False
    cf_api_url: Optional[str] = None
    cf_api_token: Optional[str] = None
    cf_zone_id: Optional[str] = None
    head_wait_seconds: int = 1

# -------------------------
# 配置管理
# -------------------------
class ConfigManager:
    @staticmethod
    def load_config() -> Config:
        with open("config.yaml", "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        
        if os.path.exists("config_local.yaml"):
            with open("config_local.yaml", "r", encoding="utf-8") as f:
                local_config = yaml.safe_load(f)
                config_data.update(local_config)
        
        return Config(**config_data)

# -------------------------
# JSON 处理器
# -------------------------
class JSONProcessor:
    def __init__(self, config: Config):
        self.config = config
    
    def load_dataframe(self) -> pd.DataFrame:
        url = self.config.url
        if url.startswith("http"):
            r = requests.get(url)
            r.raise_for_status()
            data = r.json()
        elif os.path.exists(url):
            with open(url, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            raise ValueError(f"JSON 文件无效或不存在: {url}")

        df = pd.DataFrame(data)

        # 过滤空行或非 http 开头字段
        def is_http(val):
            return isinstance(val, str) and val.lower().startswith("http")
        
        df_filtered = df[df.apply(lambda row: any(is_http(v) for v in row), axis=1)]

        return df_filtered

# -------------------------
# 内容验证器
# -------------------------
class ContentValidator:
    @staticmethod
    def is_error_content(chunk: bytes) -> bool:
        return b"<html" in chunk.lower() or b"{\"code\"" in chunk.lower() or b"failed" in chunk.lower()

# -------------------------
# Cloudflare 缓存管理器
# -------------------------
class CloudflareCacheManager:
    def __init__(self, config: Config):
        self.config = config
        self.session = None
    
    async def __aenter__(self):
        if self.config.auto_purge_cf_cache:
            self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def purge_cache(self, urls: List[str]):
        if not all([self.config.cf_api_url, self.config.cf_api_token, self.config.cf_zone_id]):
            logger.warning("CF API 配置不完整，无法清除缓存")
            return False
        
        try:
            headers = {
                "Authorization": f"Bearer {self.config.cf_api_token}", 
                "Content-Type": "application/json"
            }
            payload = {"files": urls}
            
            async with self.session.post(
                f"{self.config.cf_api_url}/zones/{self.config.cf_zone_id}/purge_cache", 
                json=payload, 
                headers=headers
            ) as resp:
                text = await resp.text()
                if resp.status == 200:
                    logger.info(f"自动清除 {len(urls)} 个 URL 缓存成功")
                    return True
                else:
                    logger.warning(f"自动清除缓存失败: {text}")
                    return False
        except Exception as e:
            logger.error(f"清除缓存时发生错误: {e}")
            return False

# -------------------------
# URL 检查器
# -------------------------
class URLChecker:
    def __init__(self, config: Config):
        self.config = config
        self.validator = ContentValidator()
    
    async def check_url(self, session: aiohttp.ClientSession, url: str, col: str) -> Dict[str, Any]:
        result = {"url": url, "column": col, "status": None, "cf_cache_status": None, "age": None, "error": None}
        
        for attempt in range(self.config.retry_times + 1):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    cf_status = resp.headers.get("cf-cache-status", "N/A").upper()
                    age = resp.headers.get("age", "0")
                    content_type = resp.headers.get("content-type", "")
                    
                    # HTML/JSON/错误返回视为失败
                    if "text/html" in content_type.lower() or "application/json" in content_type.lower():
                        raise ValueError("返回 HTML/JSON")
                    
                    chunk = await resp.content.read(64)
                    if self.validator.is_error_content(chunk):
                        raise ValueError("前几个字节判定为错误内容")
                    
                    result.update({"status": "SUCCESS", "cf_cache_status": cf_status, "age": age})
                    logger.info(f"[SUCCESS] col: {col} | {cf_status} | age: {age} | url: {url}")
                    return result
                    
            except Exception as e:
                if attempt < self.config.retry_times:
                    logger.warning(f"[WARN] col: {col} | url: {url} | 尝试 {attempt + 1}/{self.config.retry_times} | 错误: {e}")
                    await asyncio.sleep(0.5)
                else:
                    result.update({"status": "ERROR", "error": str(e)})
                    logger.error(f"[ERROR] col: {col} | url: {url} | 尝试 {attempt + 1}/{self.config.retry_times} | 错误: {e}")
                    return result

# -------------------------
# 文件下载器
# -------------------------
class FileDownloader:
    def __init__(self, config: Config):
        self.config = config
    
    async def download_file(self, session: aiohttp.ClientSession, url: str, filename: str):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            async with aiofiles.open(filename, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    await f.write(chunk)

# -------------------------
# 主控制器
# -------------------------
class CacheCheckController:
    def __init__(self, config: Config):
        self.config = config
        self.json_processor = JSONProcessor(config)
        self.url_checker = URLChecker(config)
        self.downloader = FileDownloader(config)
        self.cf_manager = CloudflareCacheManager(config)
        self.results = []
    
    async def worker(self, sem: asyncio.Semaphore, session: aiohttp.ClientSession, url: str, col: str):
        async with sem:
            result = await self.url_checker.check_url(session, url, col)
            self.results.append(result)
            
            # 如果检测失败且配置了下载功能
            if result["status"] == "ERROR" and self.config.download_if_miss:
                try:
                    if self.config.keep_downloaded_file:
                        filename = os.path.join(self.config.download_dir, os.path.basename(url))
                    else:
                        tmp_file = tempfile.NamedTemporaryFile(delete=False)
                        filename = tmp_file.name
                        tmp_file.close()
                    
                    await self.downloader.download_file(session, url, filename)
                    await asyncio.sleep(self.config.head_wait_seconds)
                    if not self.config.keep_downloaded_file:
                        os.remove(filename)
                except Exception as e:
                    logger.error(f"下载文件时出错 {url}: {e}")
    
    async def run(self):
        df = self.json_processor.load_dataframe()
        
        sem = asyncio.Semaphore(self.config.max_concurrent)
        async with aiohttp.ClientSession() as session:
            tasks = []
            for _, row in df.iterrows():
                for col, val in row.items():
                    if isinstance(val, str) and val.lower().startswith("http"):
                        tasks.append(self.worker(sem, session, val, col))
            await asyncio.gather(*tasks)
        
        # 保存结果到 CSV
        results_df = pd.DataFrame(self.results)
        results_df.to_csv(self.config.output_csv, index=False)
        logger.info(f"结果已保存到 {self.config.output_csv}")
        
        # 清除 CF 缓存
        error_urls = [r["url"] for r in self.results if r["status"] == "ERROR"]
        if self.config.auto_purge_cf_cache and error_urls:
            logger.info(f"检测到 {len(error_urls)} 个错误 URL，开始批量清除 CF 缓存...")
            async with self.cf_manager as cf_manager:
                await cf_manager.purge_cache(error_urls)
        elif error_urls:
            logger.info(f"检测到 {len(error_urls)} 个错误 URL")
        
        logger.info("检测完成。")

# -------------------------
# 主函数
# -------------------------
async def main():
    try:
        config = ConfigManager.load_config()
        controller = CacheCheckController(config)
        await controller.run()
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
