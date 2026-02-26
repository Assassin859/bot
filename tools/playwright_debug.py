from playwright.sync_api import sync_playwright
import sys

url = "http://localhost:8502"
output_png = "/tmp/dashboard_debug.png"
output_html = "/tmp/dashboard_debug.html"

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        # Allow time for the dashboard to render
        page.wait_for_timeout(2000)

        # Click through tabs using role=tab to force content render
        tabs = ["📊 Market", "💼 Position", "💰 Account", "🤖 Bot Control", "📋 Logs"]
        for t in tabs:
            try:
                page.get_by_role("tab", name=t).click()
                page.wait_for_timeout(500)
            except Exception as e:
                print(f"Could not click tab {t}: {e}")

        # Also expand sidebar Controls and click Reconfigure to render setup panel
        try:
            page.get_by_text("⚙️ Controls").click()
            page.wait_for_timeout(500)
            page.get_by_text("🔄 Reconfigure").click()
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # Capture a screenshot and page HTML for debugging
        page.screenshot(path=output_png, full_page=True)
        with open(output_html, "w", encoding="utf-8") as f:
            f.write(page.content())
        print(f"Saved {output_png} and {output_html}")
        browser.close()
except Exception as e:
    print("Error during Playwright debug run:", e)
    sys.exit(2)
