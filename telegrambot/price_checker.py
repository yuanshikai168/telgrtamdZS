"""
OKX 币价查询模块
"""
import requests
import logging

logger = logging.getLogger(__name__)

OKX_BUY_URL = "https://www.okx.com/v3/c2c/tradingOrders/books?quoteCurrency=cny&baseCurrency=usdt&side=buy&paymentMethod="
OKX_SELL_URL = "https://www.okx.com/v3/c2c/tradingOrders/books?quoteCurrency=cny&baseCurrency=usdt&side=sell&paymentMethod="


class PriceChecker:
    """欧易 OTC 市场价格查询"""

    HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    def _fetch(self, payment_method: str) -> dict:
        """获取指定支付方式的买卖价格"""
        result = {"buy": "0", "sell": "0"}
        try:
            session = requests.Session()

            # 买入价 (买家出价 - 我们买 USDT 的价格)
            buy_resp = session.get(
                OKX_BUY_URL + payment_method, headers=self.HEADERS, timeout=10
            )
            if buy_resp.ok:
                buy_data = buy_resp.json()
                sells = buy_data.get("data", {}).get("sell", [])
                if sells:
                    result["buy"] = sells[0].get("price", "0")

            # 卖出价 (卖家出价 - 我们卖 USDT 的价格)
            sell_resp = session.get(
                OKX_SELL_URL + payment_method, headers=self.HEADERS, timeout=10
            )
            if sell_resp.ok:
                sell_data = sell_resp.json()
                buys = sell_data.get("data", {}).get("buy", [])
                if buys:
                    result["sell"] = buys[0].get("price", "0")

        except Exception as e:
            logger.error(f"获取价格失败: {e}")

        return result

    def get_bank_card_price(self) -> dict:
        return self._fetch("bank")

    def get_alipay_price(self) -> dict:
        return self._fetch("alipay")

    def get_wechat_price(self) -> dict:
        return self._fetch("wxpay")

    def get_all_prices(self) -> dict:
        return {
            "bank": self.get_bank_card_price(),
            "alipay": self.get_alipay_price(),
            "wechat": self.get_wechat_price(),
        }