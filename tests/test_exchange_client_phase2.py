import asyncio
import pytest

from exchange_client import ExchangeClient


class DummyExchange:
    def __init__(self):
        self.markets = {"BTC/USDT": {"info": {"maxLeverage": 20}}}

    async def fetch_balance(self, params=None):
        return {"USDT": {"free": 123.45, "total": 123.45}, "info": {"totalWalletBalance": 123.45, "totalMarginBalance": 10.0}}

    async def fetch_positions(self, symbols=None, params=None):
        return [{"symbol": "BTC/USDT", "leverage": 5, "size": 0.01, "entryPrice": 30000, "unrealizedPnl": 1.23}]

    async def fetch_ticker(self, symbol):
        return {"last": 31000}

    async def close(self):
        pass

    def price_to_precision(self, symbol, price):
        return str(price)

    def amount_to_precision(self, symbol, amount):
        return str(amount)

    async def load_markets(self):
        return


@pytest.mark.asyncio
async def test_exchange_client_helpers(monkeypatch):
    # Prepare ExchangeClient with dummy config
    client = ExchangeClient({"exchange": {}, "governor": {}, "binance_time": {}})
    # Monkeypatch the internal _exchange and methods
    dummy = DummyExchange()
    client._exchange = dummy

    # Monkeypatch governor.acquire to no-op
    async def _noop(caller=""):
        return None
    client.governor.acquire = _noop

    bal = await client.get_account_balance()
    assert isinstance(bal, float) and bal == pytest.approx(123.45)

    lev = await client.get_account_leverage()
    assert isinstance(lev, int) and lev == 5

    margin = await client.get_margin_info()
    assert isinstance(margin, dict)
    assert margin["available_margin"] == pytest.approx(123.45)

    pos = await client.get_position_info()
    assert isinstance(pos, dict)
    assert pos["symbol"] == "BTC/USDT"
    assert pos["current_price"] == pytest.approx(31000)
