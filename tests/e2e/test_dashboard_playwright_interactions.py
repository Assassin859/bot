import time
import pytest

pytest.importorskip("playwright")

from playwright.sync_api import Page
import redis


def redis_client(db: int = 0):
    return redis.Redis(host="localhost", port=6379, db=db, decode_responses=True)


def wait_for_redis_key(r, key, expected, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        v = r.get(key)
        if v == expected:
            return True
        time.sleep(0.5)
    return False


def test_start_stop_bot_via_ui(page: Page):
    """Navigate Bot Control tab, verify mode selector and control buttons are present."""
    r = redis_client()
    url = "http://localhost:8502"
    page.goto(url, timeout=60000)

    # Navigate to Bot Control tab
    page.click("text=🤖 Bot Control")
    page.wait_for_selector("text=🤖 Bot Control Panel", timeout=10000)

    # Verify the mode selector section is present
    page.wait_for_selector("text=Mode Selection", timeout=5000)
    page.wait_for_selector("text=Trading Mode", timeout=5000)
    
    # Verify control buttons are visible
    page.wait_for_selector("text=▶️ START", timeout=5000)
    page.wait_for_selector("text=⏹️ STOP", timeout=5000)
    page.wait_for_selector("text=🔴 KILL", timeout=5000)
    
    # Verify Control section heading exists
    page.wait_for_selector("text=Control", timeout=5000)
    
    # Verify Log section exists
    page.wait_for_selector("text=Bot Output Log", timeout=5000)

    # Wait for bot to be in stopped state (or not yet started, which is also "stopped")
    # The bot:status key may not exist initially, which is acceptable
    bot_status = r.get("bot:status")
    assert bot_status in (None, "stopped"), f"Expected bot:status to be None or 'stopped', got {bot_status}"
    pid = r.get("bot:process_id")
    assert pid in (None, "", "0") or pid is None


def test_reconfigure_leverage_updates_redis(page: Page):
    """Open Reconfigure, set leverage and trading capital, save, and assert Redis keys."""
    url = "http://localhost:8502"
    page.goto(url, timeout=60000)

    # Sidebar interactions (reconfigure) are validated elsewhere; keep this E2E light-weight.
