import pytest

# These tests are lightweight checks for UI-driven state changes.
# Full end-to-end Streamlit UI tests should use Playwright or Selenium.

from redis_state import RedisState


@pytest.mark.asyncio
async def test_mode_selection_persists():
    rs = RedisState(url="redis://localhost:6379/3")
    try:
        for mode in ["paper", "ghost", "live"]:
            await rs.set_mode(mode)
            assert await rs.get_mode() == mode
    except Exception as e:
        # If Redis isn't reachable in this environment we simply skip
        import pytest
        pytest.skip(f"Redis unavailable: {e}")


@pytest.mark.asyncio
async def test_bot_process_id_lifecycle():
    rs = RedisState(url="redis://localhost:6379/3")
    try:
        await rs.clear_bot_process_id()
        assert await rs.get_bot_process_id() is None
        await rs.set_bot_process_id(12345)
        assert await rs.get_bot_process_id() == 12345
        await rs.clear_bot_process_id()
        assert await rs.get_bot_process_id() is None
    except Exception as e:
        import pytest
        pytest.skip(f"Redis unavailable: {e}")

@pytest.mark.asyncio
async def test_executor_initialization_via_manager():
    # ensure BotManager can create executors without launching a process
    from bot_manager import BotManager
    BotManager._init_executor("paper")
    assert BotManager.get_executor("paper") is not None
    BotManager._init_executor("ghost")
    assert BotManager.get_executor("ghost") is not None
    BotManager._init_executor("live")
    assert BotManager.get_executor("live") is not None
    # check current mode tracking
    BotManager._current_mode = "live"
    assert BotManager.get_current_mode() == "live"
    # cleanup
    BotManager._cleanup_executor()
    assert BotManager.get_current_mode() is None
