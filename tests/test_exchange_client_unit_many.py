import asyncio
import pytest

from exchange_client import ExchangeClient


class DummyExchangeSmall:
    def __init__(self):
        self.markets = {"BTC/USDT": {"info": {"maxLeverage": 20}}}

    async def fetch_balance(self, params=None):
        return {"USDT": {"free": 1000.0, "total": 1000.0}, "info": {"totalWalletBalance": 1000.0, "totalMarginBalance": 100.0}}

    async def fetch_positions(self, symbols=None, params=None):
        return []

    async def close(self):
        pass

    async def load_markets(self):
        return


@pytest.mark.asyncio
async def test_balance_various_amounts(monkeypatch):
    client = ExchangeClient({"exchange": {}, "governor": {}, "binance_time": {}})
    dummy = DummyExchangeSmall()
    client._exchange = dummy

    async def _noop(caller=""):
        return None
    client.governor.acquire = _noop

    # parametrized scenarios
    amounts = [0.0, 1.0, 50.5, 1000.0, 12345.67]
    for amt in amounts:
        # monkeypatch fetch_balance to return amt
        async def _fb(params=None, amt=amt):
            return {"USDT": {"free": amt, "total": amt}, "info": {"totalWalletBalance": amt, "totalMarginBalance": 0.0}}
        client.fetch_balance = _fb
        b = await client.get_account_balance()
        assert isinstance(b, float)
        assert b == pytest.approx(amt)


@pytest.mark.asyncio
async def test_leverage_fallbacks(monkeypatch):
    client = ExchangeClient({"exchange": {}, "governor": {}, "binance_time": {}})
    dummy = DummyExchangeSmall()
    client._exchange = dummy

    async def _noop(caller=""):
        return None
    client.governor.acquire = _noop

    # no positions, but market info contains maxLeverage
    lev = await client.get_account_leverage()
    assert lev == 20
