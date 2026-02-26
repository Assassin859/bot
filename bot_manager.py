"""Bot Manager: Control subprocess execution of the trading bot.

Handles:
- Starting bot with specified mode
- Monitoring process status
- Graceful shutdown (SIGTERM -> SIGKILL)
- Log streaming and output capture
- Executor lifecycle management (paper, ghost, live modes)
"""
import asyncio
import subprocess
import signal
import os
import psutil
from typing import Optional, List, Dict, Any
from datetime import datetime
from logging_utils import log_event
from paper_executor import PaperExecutor
from ghost_engine import GhostEngine
from live_executor import LiveExecutor
from risk_monitor import RiskMonitor
import threading
import time


class BotManager:
    """Manage bot subprocess lifecycle and executor instances."""
    
    # Store output in circular buffer (last 100 lines)
    _output_buffer: List[str] = []
    _max_buffer_size = 100
    
    # Executor instances for each mode
    _current_mode: Optional[str] = None
    _paper_executor: Optional[PaperExecutor] = None
    _ghost_engine: Optional[GhostEngine] = None
    _live_executor: Optional[LiveExecutor] = None
    _risk_monitor: Optional[RiskMonitor] = None
    _current_pid: Optional[int] = None
    # In-process runner support
    _inprocess_thread: Optional[threading.Thread] = None
    _inprocess_stop_event: Optional[threading.Event] = None
    
    @classmethod
    async def start_bot(cls, mode: str) -> Optional[int]:
        """Launch bot subprocess.
        
        Args:
            mode: Trading mode (backtest, paper, ghost, live)
        
        Returns:
            Process ID if successful, None otherwise
        """
        valid_modes = ["backtest", "paper", "ghost", "live"]
        if mode not in valid_modes:
            log_event("ERROR", {
                "msg": "Invalid bot mode",
                "mode": mode,
                "valid_modes": valid_modes
            })
            return None
        
        try:
            # Initialize executor for the mode
            cls._init_executor(mode)
            cls._current_mode = mode
            
            # Clear output buffer
            cls._output_buffer.clear()
            
            # Launch bot process
            proc = await asyncio.create_subprocess_exec(
                "python", "main.py", f"--mode={mode}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd="/workspaces/bot"
            )
            
            pid = proc.pid
            cls._current_pid = pid
            
            log_event("INFO", {
                "msg": "Bot started",
                "mode": mode,
                "pid": pid,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Start background task to capture output
            asyncio.create_task(cls._capture_output(proc))
            
            return pid
        
        except Exception as e:
            log_event("ERROR", {
                "msg": "Failed to start bot",
                "error": str(e)
            })
            return None
    
    @classmethod
    def _init_executor(cls, mode: str):
        """Initialize executor for the given mode.
        
        Args:
            mode: Trading mode (paper, ghost, live)
        """
        if mode == "paper":
            cls._paper_executor = PaperExecutor(starting_capital=10000.0)
        elif mode == "ghost":
            cls._ghost_engine = GhostEngine()
        elif mode == "live":
            cls._live_executor = LiveExecutor()
            cls._risk_monitor = RiskMonitor()

    @classmethod
    def start_inprocess(cls, mode: str) -> bool:
        """Start an in-process bot runner for light-weight testing (paper/ghost).

        This does not spawn a subprocess and keeps an executor instance in memory.
        Returns True if started, False otherwise.
        """
        if cls._inprocess_thread and cls._inprocess_thread.is_alive():
            log_event("WARNING", {"msg": "In-process bot already running"})
            return False

        cls._init_executor(mode)
        cls._current_mode = mode

        stop_event = threading.Event()
        cls._inprocess_stop_event = stop_event

        def runner():
            log_event("INFO", {"msg": "In-process bot runner started", "mode": mode})
            try:
                while not stop_event.is_set():
                    # sleep briefly; executors are interacted with via dashboard
                    time.sleep(0.5)
            finally:
                log_event("INFO", {"msg": "In-process bot runner stopping", "mode": mode})

        th = threading.Thread(target=runner, daemon=True)
        cls._inprocess_thread = th
        th.start()
        return True

    @classmethod
    def stop_inprocess(cls) -> bool:
        """Stop the in-process runner and cleanup executors."""
        if cls._inprocess_stop_event:
            cls._inprocess_stop_event.set()
        if cls._inprocess_thread:
            cls._inprocess_thread.join(timeout=2)

        cls._cleanup_executor()
        cls._inprocess_thread = None
        cls._inprocess_stop_event = None
        return True
    
    @classmethod
    def get_executor(cls, mode: str) -> Optional[Any]:
        """Get executor instance for the given mode.
        
        Args:
            mode: Trading mode (paper, ghost, live)
        
        Returns:
            Executor instance or None
        """
        if mode == "paper":
            return cls._paper_executor
        elif mode == "ghost":
            return cls._ghost_engine
        elif mode == "live":
            return cls._live_executor
        return None
    
    @classmethod
    def get_risk_monitor(cls) -> Optional[RiskMonitor]:
        """Get risk monitor instance for live trading.
        
        Returns:
            RiskMonitor instance or None
        """
        return cls._risk_monitor
    
    @classmethod
    def get_current_mode(cls) -> Optional[str]:
        """Get current trading mode.
        
        Returns:
            Current mode or None
        """
        return cls._current_mode
    
    @classmethod
    async def _capture_output(cls, proc):
        """Capture subprocess output to buffer."""
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                
                decoded = line.decode().strip()
                if decoded:
                    cls._output_buffer.append(decoded)
                    # Keep circular buffer at max size
                    if len(cls._output_buffer) > cls._max_buffer_size:
                        cls._output_buffer.pop(0)
        
        except Exception as e:
            log_event("ERROR", {
                "msg": "Error capturing bot output",
                "error": str(e)
            })
    
    @classmethod
    async def stop_bot(cls, pid: int, timeout: int = 5) -> bool:
        """Stop bot process gracefully.
        
        Args:
            pid: Process ID
            timeout: Seconds to wait before force kill
        
        Returns:
            True if stopped successfully
        """
        if pid is None:
            return False
        
        try:
            process = psutil.Process(pid)
            
            # Try graceful shutdown (SIGTERM)
            process.terminate()
            
            try:
                process.wait(timeout=timeout)
                log_event("INFO", {
                    "msg": "Bot stopped gracefully",
                    "pid": pid
                })
            
            except psutil.TimeoutExpired:
                # Force kill if timeout
                process.kill()
                process.wait()
                log_event("WARNING", {
                    "msg": "Bot force killed",
                    "pid": pid
                })
            
            # Clean up executor instances
            cls._cleanup_executor()
            cls._current_pid = None
            
            return True
        
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            log_event("WARNING", {
                "msg": "Error stopping bot",
                "pid": pid,
                "error": str(e)
            })
            return False
    
    @classmethod
    def _cleanup_executor(cls):
        """Clean up executor instances."""
        cls._paper_executor = None
        cls._ghost_engine = None
        cls._live_executor = None
        cls._risk_monitor = None
        cls._current_mode = None
    
    @classmethod
    async def is_bot_running(cls, pid: Optional[int]) -> bool:
        """Check if bot process is still running.
        
        Args:
            pid: Process ID
        
        Returns:
            True if process exists and is running
        """
        if pid is None:
            return False
        
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False
    
    @classmethod
    def get_bot_output(cls, lines: int = 50) -> List[str]:
        """Get last N lines from output buffer.
        
        Args:
            lines: Number of lines to return
        
        Returns:
            List of output lines
        """
        if not cls._output_buffer:
            return ["[Waiting for output...]"]
        
        return cls._output_buffer[-lines:]
    
    @classmethod
    def clear_output_buffer(cls):
        """Clear output buffer."""
        cls._output_buffer.clear()
