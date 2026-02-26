import pytest
pytest.importorskip("playwright")


def test_start_inprocess_and_place_paper_trade(page):
    """Start the bot in-process, open Paper Mode and place a sample trade."""
    url = "http://localhost:8502"
    page.goto(url, timeout=60000)

    # Open Bot Control tab and enable run in-process
    page.get_by_role("tab", name="🤖 Bot Control").click()
    page.wait_for_selector("text=Bot Control Panel", timeout=10000)

    # Check the run-inprocess checkbox and start
    page.check("text=Run in-process (no subprocess)")
    page.click("text=▶️ START")

    # Wait for running indicator
    page.wait_for_selector("text=Bot Running", timeout=5000)

    # Switch to Paper Mode and place a sample trade
    page.get_by_role("tab", name="📄 Paper Mode").click()
    page.wait_for_selector("text=Paper Trading Simulation", timeout=5000)

    # Click generate sample trade and assert success toast appears
    page.click("text=▶️ Generate Sample Trade")
    page.wait_for_selector("text=Sample buy order placed", timeout=5000)

    # Stop the in-process bot
    page.get_by_role("tab", name="🤖 Bot Control").click()
    page.click("text=⏹️ STOP")
    page.wait_for_selector("text=Bot Stopped", timeout=5000)
