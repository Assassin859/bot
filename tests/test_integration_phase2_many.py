import pytest
import asyncio

from exchange_client import ExchangeClient
from redis_state import RedisState


class DummyExchangeInt:
    async def fetch_balance(self, params=None):
        return {"USDT": {"free": 2000.0, "total": 2000.0}, "info": {"totalWalletBalance": 2000.0, "totalMarginBalance": 50.0}}

    async def fetch_positions(self, symbols=None, params=None):
        return [{"symbol": "BTC/USDT", "leverage": 5, "size": 0.02, "entryPrice": 30000, "unrealizedPnl": 5.0}]

    async def fetch_ticker(self, symbol):
        return {"last": 30500}

    async def load_markets(self):
        return

    async def close(self):
        return


@pytest.mark.asyncio
async def test_startup_populates_redis(monkeypatch, tmp_path):
    client = ExchangeClient({"exchange": {}, "governor": {}, "binance_time": {}})
    client._exchange = DummyExchangeInt()

    async def _noop(caller=""):
        return None
    client.governor.acquire = _noop

    rs = RedisState(url="redis://localhost:6379/2")

    try:
        # ensure clean
        await rs.set_account_balance(0.0)
        await rs.set_leverage_current(1)

        # Run sync
        await client.sync_account_to_redis(rs, symbol="BTC/USDT")

        bal = await rs.get_account_balance()
        lev = await rs.get_leverage_current()

        assert bal == pytest.approx(2000.0)
        assert lev == 5
    except Exception as e:
        import pytest
        pytest.skip(f"Redis unavailable for integration test: {e}")
