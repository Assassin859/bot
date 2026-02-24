"""Streamlit dashboard for BTC/USDT Futures bot.

Provides:
- 2s auto-refresh
- Automation toggle (reads/writes automation_enabled from redis_state)
- Market context with external feeds display
- Ghost metrics when automation OFF
- Emergency close button (2-step)
- Dual log panels (execution + rejection feed)
- Position details with PnL tracking
"""
from __future__ import annotations
import streamlit as st
import asyncio
import json
from datetime import datetime
from typing import Optional
import time

from redis_state import RedisState
from external_feeds import fetch_all_external_data


# Page config and session state
st.set_page_config(page_title="Bot Dashboard", layout="wide", initial_sidebar_state="expanded")

# Initialize session state
if "emergency_confirmed" not in st.session_state:
    st.session_state.emergency_confirmed = False


async def get_redis_snapshot():
    """Fetch current Redis snapshot."""
    redis_state = RedisState()
    try:
        snapshot = await redis_state.get_snapshot()
        return snapshot
    except Exception as e:
        st.error(f"Redis error: {e}")
        return None
    finally:
        redis_state.close()


async def toggle_automation(enabled: bool):
    """Update automation toggle in Redis."""
    redis_state = RedisState()
    try:
        await redis_state.set_automation_enabled(enabled)
    except Exception as e:
        st.error(f"Failed to update automation: {e}")
    finally:
        redis_state.close()


async def get_external_context():
    """Fetch external feeds data."""
    try:
        external_scores, external_meta = await fetch_all_external_data()
        return external_scores, external_meta
    except Exception as e:
        st.error(f"External feeds error: {e}")
        return {}, {}


def get_event_log() -> list[dict]:
    """Retrieve recent event log from Redis cache (last 50 events)."""
    redis_state = RedisState()
    try:
        loop = asyncio.new_event_loop()
        log_json = loop.run_until_complete(redis_state.get_log_buffer())
        loop.close()
        if log_json:
            return json.loads(log_json)
    except Exception:
        pass
    return []


def get_rejection_feed() -> list[dict]:
    """Retrieve rejection events (circuit breaker trips, strategy rejections)."""
    redis_state = RedisState()
    try:
        loop = asyncio.new_event_loop()
        rejections_json = loop.run_until_complete(redis_state.get_rejection_feed())
        loop.close()
        if rejections_json:
            return json.loads(rejections_json)
    except Exception:
        pass
    return []


async def execute_emergency_close():
    """Trigger emergency market close order."""
    redis_state = RedisState()
    try:
        snapshot = await redis_state.get_snapshot()
        if snapshot and snapshot.active_position:
            # Signal emergency close by writing position close flag
            await redis_state.set_emergency_close_flag(True)
            st.success("Emergency close initiated. Market order will execute next cycle.")
        else:
            st.info("No active position to close.")
    except Exception as e:
        st.error(f"Emergency close failed: {e}")
    finally:
        redis_state.close()


def main():
    """Main dashboard UI."""
    st.title("🤖 BTC/USDT Futures Bot - Dashboard")
    
    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ Controls")
        
        # Automation toggle
        redis_state_sync = RedisState()
        loop = asyncio.new_event_loop()
        try:
            snapshot = loop.run_until_complete(redis_state_sync.get_snapshot())
            current_auto = snapshot.automation_enabled if snapshot else False
        except Exception:
            current_auto = False
        finally:
            loop.close()
            redis_state_sync.close()
        
        automation_enabled = st.toggle(
            "🟢 Automation Enabled",
            value=current_auto,
            help="Enable/disable automated signal generation and execution"
        )
        
        if automation_enabled != current_auto:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(toggle_automation(automation_enabled))
                st.success(f"Automation {'enabled' if automation_enabled else 'disabled'}")
            except Exception as e:
                st.error(f"Toggle failed: {e}")
            finally:
                loop.close()
        
        st.divider()
        
        # Emergency close (2-step confirmation)
        st.subheader("⚠️ Emergency Controls")
        if st.button("Mark for Emergency Close", use_container_width=True):
            st.session_state.emergency_confirmed = True
        
        if st.session_state.emergency_confirmed:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✓ CONFIRM", use_container_width=True, type="primary"):
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(execute_emergency_close())
                    finally:
                        loop.close()
                    st.session_state.emergency_confirmed = False
            with col2:
                if st.button("✗ CANCEL", use_container_width=True):
                    st.session_state.emergency_confirmed = False
    
    # Main tabs
    tab_market, tab_position, tab_logs = st.tabs(["📊 Market", "💼 Position", "📋 Logs"])
    
    # === MARKET TAB ===
    with tab_market:
        st.subheader("Market Context & External Feeds")
        
        # Fetch external data
        loop = asyncio.new_event_loop()
        try:
            external_scores, external_meta = loop.run_until_complete(get_external_context())
        finally:
            loop.close()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            fear_greed = external_scores.get("fear_greed_index", -1)
            if fear_greed >= 0:
                st.metric("Fear & Greed", f"{fear_greed:.0f}", 
                         help="0=Extreme Fear, 100=Extreme Greed")
        
        with col2:
            funding_rate = external_scores.get("funding_rate_pct", -999)
            if funding_rate != -999:
                st.metric("Funding Rate", f"{funding_rate:.3f}%",
                         help="Positive=Longs pay shorts")
        
        with col3:
            spot_futures_ratio = external_scores.get("spot_futures_ratio", -1)
            if spot_futures_ratio >= 0:
                st.metric("Spot/Futures Ratio", f"{spot_futures_ratio:.3f}",
                         help=">1.0 = More volume on spot")
        
        with col4:
            st.metric("Timestamp", datetime.now().strftime("%H:%M:%S"),
                     help="Dashboard refresh time")
        
        # Market structure
        if external_meta:
            with st.expander("📈 Market Structure"):
                st.json(external_meta)
    
    # === POSITION TAB ===
    with tab_position:
        st.subheader("Active Position & Performance")
        
        loop = asyncio.new_event_loop()
        try:
            snapshot = loop.run_until_complete(get_redis_snapshot())
        finally:
            loop.close()
        
        if snapshot and snapshot.active_position:
            pos = snapshot.active_position
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Side", pos.side.upper(), help="Long or Short")
            with col2:
                st.metric("Entry Price", f"${pos.entry_price:,.2f}")
            with col3:
                st.metric("Amount", f"{pos.amount:.6f} BTC")
            with col4:
                st.metric("Notional", f"${pos.notional_usd:,.2f}")
            
            st.divider()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Stop Loss", f"${pos.sl_price:,.2f}")
            with col2:
                st.metric("Take Profit", f"${pos.tp_price:,.2f}")
            with col3:
                elapsed_min = (datetime.now() - pos.entry_time).total_seconds() / 60
                st.metric("Hold Time", f"{elapsed_min:.1f} min")
            
            # Ghost metrics (when automation OFF)
            if snapshot and not snapshot.automation_enabled:
                st.warning("📊 Ghost Mode Metrics (Automation OFF)")
                col1, col2, col3 = st.columns(3)
                with col1:
                    ghost_pnl = snapshot.ghost_metrics.get("cumulative_pnl_usd", 0) if snapshot.ghost_metrics else 0
                    st.metric("Simulated PnL", f"${ghost_pnl:,.2f}")
                with col2:
                    ghost_win_pct = snapshot.ghost_metrics.get("win_rate_pct", 0) if snapshot.ghost_metrics else 0
                    st.metric("Win Rate", f"{ghost_win_pct:.1f}%")
                with col3:
                    trades_sim = snapshot.ghost_metrics.get("total_trades", 0) if snapshot.ghost_metrics else 0
                    st.metric("Simulated Trades", int(trades_sim))
        else:
            st.info("❌ No active position")
            if snapshot and snapshot.last_closed_position:
                lcpos = snapshot.last_closed_position
                st.metric("Last Trade PnL", f"${lcpos.get('pnl_usd', 0):,.2f}")
                st.metric("Last Trade Win Rate", f"{lcpos.get('win_pct', 0):.1f}%")
        
        # Account summary
        if snapshot:
            st.divider()
            st.subheader("Account Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Account Balance", f"${snapshot.account_balance_usd:,.2f}")
            with col2:
                daily_pnl = snapshot.daily_rolled_pnl_usd if snapshot else 0
                st.metric("24h PnL", f"${daily_pnl:,.2f}")
            with col3:
                pct = (daily_pnl / max(snapshot.account_balance_usd, 1)) * 100
                st.metric("24h Return", f"{pct:.2f}%")
    
    # === LOGS TAB ===
    with tab_logs:
        st.subheader("Event & Rejection Logs")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Execution Events (Last 50)**")
            events = get_event_log()
            if events:
                for event in events[-50:]:
                    ts = event.get("timestamp", "")
                    msg = event.get("msg", "")
                    level = event.get("level", "INFO")
                    
                    # Color code by level
                    if level == "ERROR":
                        st.error(f"[{ts}] {msg}")
                    elif level == "WARNING":
                        st.warning(f"[{ts}] {msg}")
                    else:
                        st.info(f"[{ts}] {msg}")
            else:
                st.text("No events yet")
        
        with col2:
            st.write("**Rejection Feed (Circuit Breaker Trips)**")
            rejections = get_rejection_feed()
            if rejections:
                for rejection in rejections[-50:]:
                    ts = rejection.get("timestamp", "")
                    reason = rejection.get("reason", "")
                    breaker = rejection.get("breaker", "")
                    st.warning(f"[{ts}] {breaker}: {reason}")
            else:
                st.text("No rejections yet")
    
    # Auto-refresh every 2 seconds
    st.markdown("---")
    st.caption(f"🔄 Refreshing every 2s | Last update: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    time.sleep(2)
    st.rerun()


if __name__ == "__main__":
    main()
