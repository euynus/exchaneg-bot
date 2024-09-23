import time
import httpx
import hmac
import hashlib
from urllib.parse import urlencode, quote
from loguru import logger
from pydantic import BaseModel, Field
from typing import List
import schedule
import asyncio
import json
import telegram

import config


class Asset(BaseModel):
    """
    小额资产
    """

    asset: str
    convert_mx: str = Field()


class MEXCApiClient:
    def __init__(self, api_key: str, secret_key: str, base_url: str = config.mexc_host):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        # 需要忽略的资产，不要要兑换
        self.ignore_assets: List[str] = ["USDC"]
        self.bot = telegram.Bot(token=config.telegram_bot_token)

    async def _get_server_time(self):
        endpoint = "/api/v3/time"
        response = await self.public_request("get", endpoint)
        if response.status_code == httpx.codes.OK:
            return response.json()["serverTime"]
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def _sign_v3(self, req_time, sign_params=None):
        if sign_params:
            sign_params = urlencode(sign_params, quote_via=quote)
            to_sign = f"{sign_params}&timestamp={req_time}"
        else:
            to_sign = f"timestamp={req_time}"
        sign = hmac.new(
            self.secret_key.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return sign

    async def public_request(self, method, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, params=params)
        return response

    async def sign_request(self, method, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        req_time = await self._get_server_time()
        if params:
            params["signature"] = self._sign_v3(req_time=req_time, sign_params=params)
        else:
            params = {}
            params["signature"] = self._sign_v3(req_time=req_time)
        params["timestamp"] = req_time
        headers = {
            "x-mexc-apikey": self.api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, params=params, headers=headers)
        return response

    async def get_dust_assets(self):
        endpoint = "/api/v3/capital/convert/list"
        response = await self.sign_request("get", endpoint)

        if response.status_code == httpx.codes.OK:
            return response.json()
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    async def dust_transfer(self, assets):
        endpoint = "/api/v3/capital/convert"
        params = {"asset": ",".join(assets)}
        response = await self.sign_request("post", endpoint, params=params)
        if response.status_code == httpx.codes.OK:
            result = response.json()
            await self.send_telegram_message(result)
            return result
        else:
            await self.send_telegram_message(response.json())
            raise Exception(f"Error: {response.status_code}, {response.text}")

    async def send_telegram_message(self, result):
        message = f"小额资产兑换结果:\n```\n{json.dumps(result, indent=2)}\n```"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{config.telegram_host}/bot{config.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": config.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                },
            )
        if response.status_code == httpx.codes.OK:
            logger.info("Telegram message sent!")
        else:
            logger.error(f"Error: {response.status_code}, {response.text}")

    async def run(self):
        try:
            # 获取小额资产列表
            dust_assets = await self.get_dust_assets()
            logger.info(f"获取到的小额资产: {dust_assets}")
            # 排除部分资产
            convert_assets = [
                item["asset"]
                for item in dust_assets
                if item["asset"] not in self.ignore_assets
            ]

            if not dust_assets:
                logger.info("没有可兑换小额资产")
                return
            logger.info(f"准备兑换资产: {convert_assets}")

            # 进行小额资产兑换
            result = await self.dust_transfer(convert_assets)
            logger.info("兑换结果:")
            logger.info(result)
        except Exception as e:
            logger.error(f"{str(e)}")


def job():
    logger.info("开始执行定时任务")
    mexc = MEXCApiClient(config.api_key, config.secret_key)
    asyncio.run(mexc.run())
    logger.info("定时任务执行完毕")


if __name__ == "__main__":
    # 配置loguru
    logger.add("mexc_dust_transfer.log", rotation="500 MB")

    # 设置定时任务，每小时过20秒运行
    schedule.every().hour.at("00:10").do(job)

    logger.info("定时任务已设置，程序开始运行")

    # 运行定时任务
    while True:
        schedule.run_pending()
        time.sleep(1)
