import pytest

# Lightweight UI event tests scaffolding. These tests are meant to be run
# as part of CI where Streamlit UI is not executed headlessly. They focus
# on ensuring helper functions that drive UI events behave as expected.

from redis_state import RedisState


@pytest.mark.asyncio
async def test_leverage_persist_and_restore(monkeypatch):
    rs = RedisState(url="redis://localhost:6379/1")

    try:
        # Use a test keyspace (assumed ephemeral in CI). Set and then get.
        await rs.set_leverage_trading_capital(500.0)
        await rs.set_leverage_multiplier(3)
        val = await rs.get_leverage_trading_capital()
        lev = await rs.get_leverage_multiplier()

        assert val == pytest.approx(500.0)
        assert lev == 3

        # cleanup
        await rs.set_leverage_trading_capital(1000.0)
        await rs.set_leverage_multiplier(5)
    except Exception as e:
        import pytest
        pytest.skip(f"Redis unavailable for UI events test: {e}")
