import subprocess
import time
import socket
import pytest

@ pytest.fixture(scope="module", autouse=True)
def streamlit_server():
    """Start Streamlit dashboard for the duration of E2E tests."""
    # launch headless streamlit
    proc = subprocess.Popen(
        ["python", "-m", "streamlit", "run", "dashboard.py", "--server.port", "8502", "--server.headless", "true"],
        cwd="/workspaces/bot",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # wait for server to open port
    for _ in range(30):
        try:
            s = socket.socket()
            s.settimeout(1.0)
            s.connect(("localhost", 8502))
            s.close()
            break
        except Exception:
            time.sleep(1)
    yield
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
