import time
import httpx
import hmac
import hashlib
from urllib.parse import urlencode, quote
from loguru import logger
from pydantic import BaseModel, Field
from typing import List
import schedule

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

    def _get_server_time(self):
        endpoint = "/api/v3/time"
        response = self.public_request("get", endpoint)
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

    def public_request(self, method, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        with httpx.Client() as client:
            response = client.request(method, url, params=params)
        return response

    def sign_request(self, method, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        req_time = self._get_server_time()
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
        with httpx.Client() as client:
            response = client.request(method, url, params=params, headers=headers)
        return response

    def get_dust_assets(self):
        endpoint = "/api/v3/capital/convert/list"
        response = self.sign_request("get", endpoint)

        if response.status_code == httpx.codes.OK:
            return response.json()
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def dust_transfer(self, assets):
        endpoint = "/api/v3/capital/convert"
        params = {"asset": ','.join(assets)}
        response = self.sign_request("post", endpoint, params=params)
        if response.status_code == httpx.codes.OK:
            return response.json()
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def run(self):
        try:
            # 获取小额资产列表
            dust_assets = self.get_dust_assets()
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
            result = self.dust_transfer(convert_assets)
            logger.info("兑换结果:")
            logger.info(result)
        except Exception as e:
            logger.error(f"发生错误: {str(e)}")


def job():
    logger.info("开始执行定时任务")
    mexc = MEXCApiClient(config.api_key, config.secret_key)
    mexc.run()
    logger.info("定时任务执行完毕")


if __name__ == "__main__":
    # 配置loguru
    logger.add("mexc_dust_transfer.log", rotation="500 MB")

    # 设置定时任务，每小时过20秒运行
    schedule.every().hour.at("00:15").do(job)

    logger.info("定时任务已设置，程序开始运行")

    # 运行定时任务
    while True:
        schedule.run_pending()
        time.sleep(1)
