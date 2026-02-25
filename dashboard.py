"""Streamlit dashboard for BTC/USDT Futures bot.

Provides:
- 2s auto-refresh
- Automation toggle (reads/writes automation_enabled from redis_state)
- Market context with external feeds display
- Ghost metrics when automation OFF
- Emergency close button (2-step)
- Dual log panels (execution + rejection feed)
- Position details with PnL tracking
- Setup wizard for leverage configuration (first-time only)
- Live leverage metrics with margin utilization tracking
- Liquidation price meter with distance visualization
- Configuration persistence to Redis
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
from config import LeverageConfig, validate_leverage_config


# Page config and session state
st.set_page_config(page_title="Bot Dashboard", layout="wide", initial_sidebar_state="expanded")

# Initialize session state
if "emergency_confirmed" not in st.session_state:
    st.session_state.emergency_confirmed = False
if "setup_wizard_complete" not in st.session_state:
    st.session_state.setup_wizard_complete = False


async def get_leverage_config():
    """Fetch leverage configuration from Redis."""
    redis_state = RedisState()
    try:
        config_dict = await redis_state.get_leverage_config()
        if config_dict:
            return config_dict
        return None
    except Exception as e:
        st.error(f"Failed to load leverage config: {e}")
        return None
    finally:
        await redis_state.close()


async def save_leverage_config(config_dict: dict) -> bool:
    """Save leverage configuration to Redis."""
    redis_state = RedisState()
    try:
        await redis_state.set_leverage_config(config_dict)
        return True
    except Exception as e:
        st.error(f"Failed to save leverage config: {e}")
        return False
    finally:
        await redis_state.close()


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
        await redis_state.close()


async def toggle_automation(enabled: bool):
    """Update automation toggle in Redis."""
    redis_state = RedisState()
    try:
        await redis_state.set_automation_enabled(enabled)
    except Exception as e:
        st.error(f"Failed to update automation: {e}")
    finally:
        await redis_state.close()


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
        await redis_state.close()


def setup_wizard():
    """First-time setup wizard for leverage configuration."""
    st.title("⚙️ FUTURES BOT SETUP - REQUIRED")
    st.markdown("Configure your trading parameters before starting the bot.")
    
    st.markdown("---")
    st.subheader("💰 Trading Capital & Leverage")
    
    col1, col2 = st.columns(2)
    with col1:
        trading_capital = st.number_input(
            "Trading Capital (USDT)",
            min_value=100.0,
            max_value=100000.0,
            value=1000.0,
            step=100.0,
            help="How much USDT to allocate to futures positions"
        )
    with col2:
        leverage = st.slider(
            "Leverage (1x - 20x)",
            min_value=1,
            max_value=20,
            value=5,
            help="Position multiplier (Binance Futures max: 20x)"
        )
    
    st.markdown("---")
    st.subheader("⚠️ Risk Management")
    
    col1, col2 = st.columns(2)
    with col1:
        max_risk_pct = st.slider(
            "Max Risk per Trade (%)",
            min_value=0.5,
            max_value=10.0,
            value=2.0,
            step=0.5,
            help="% of account balance risked per trade"
        )
    with col2:
        max_drawdown_pct = st.slider(
            "Max Daily Drawdown (%)",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            help="Stop all trading if daily loss exceeds this %"
        )
    
    st.markdown("---")
    st.subheader("🔐 Margin Mode")
    
    margin_mode = st.radio(
        "Margin Mode",
        options=["isolated", "cross"],
        index=0,
        help="Isolated: Risk only position collateral | Cross: Risk entire wallet"
    )
    
    st.markdown("---")
    
    # Validation feedback
    config_dict = {
        "trading_capital": trading_capital,
        "leverage": leverage,
        "max_risk_pct": max_risk_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "margin_mode": margin_mode
    }
    
    try:
        config = LeverageConfig(**config_dict)
        is_valid, msg = validate_leverage_config(config)
        
        if is_valid:
            st.success(f"✅ Configuration valid: {msg}")
        else:
            st.error(f"❌ Configuration invalid: {msg}")
            st.stop()
    except Exception as e:
        st.error(f"❌ Configuration error: {e}")
        st.stop()
    
    # Summary box
    st.info(
        f"""
        **Configuration Summary:**
        - Trading Capital: ${trading_capital:,.2f}
        - Leverage: {leverage}x
        - Max Risk/Trade: {max_risk_pct}%
        - Daily Drawdown Limit: {max_drawdown_pct}%
        - Margin Mode: {margin_mode.upper()}
        
        **Implied Max Position Notional:** ${(trading_capital * leverage):,.2f}
        """
    )
    
    # Save button
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if st.button("✅ SAVE & START", type="primary", use_container_width=True):
            loop = asyncio.new_event_loop()
            try:
                success = loop.run_until_complete(save_leverage_config(config_dict))
                if success:
                    st.success("Configuration saved! Reloading dashboard...")
                    st.session_state.setup_wizard_complete = True
                    time.sleep(1)
                    st.rerun()
            finally:
                loop.close()
    
    with col2:
        st.button("📊 BACKTEST FIRST", disabled=True, help="Coming soon")
    
    with col3:
        st.markdown("*Setup takes ~1 minute. You can reconfigure anytime from the Settings tab.*")


def display_leverage_metrics(snapshot, config_dict):
    """Display real-time leverage and margin metrics."""
    if not config_dict:
        st.warning("⚠️ Leverage configuration not loaded. Please refresh.")
        return
    
    st.subheader("📊 Leverage & Margin Status")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        leverage = config_dict.get("leverage", 5)
        st.metric("Active Leverage", f"{leverage}x", help="Position multiplier")
    
    with col2:
        margin_util = snapshot.leverage_margin_utilization_pct if snapshot else 0.0
        st.metric(
            "Margin Utilization",
            f"{margin_util:.1f}%",
            help="Portion of trading capital currently in use"
        )
    
    with col3:
        liquidation_price = snapshot.leverage_liquidation_price if snapshot else 0.0
        if liquidation_price > 0:
            st.metric("Liquidation Price", f"${liquidation_price:,.2f}")
        else:
            st.metric("Liquidation Price", "N/A", help="No active position")
    
    with col4:
        max_position = snapshot.leverage_max_position_notional if snapshot else 0.0
        if max_position > 0:
            st.metric("Max Position Size", f"${max_position:,.2f}")
        else:
            trading_cap = config_dict.get("trading_capital", 1000)
            leverage_mult = config_dict.get("leverage", 5)
            max_notional = trading_cap * leverage_mult * 0.8
            st.metric("Max Position Size", f"${max_notional:,.2f}")
    
    # Danger zone warnings
    margin_util = snapshot.leverage_margin_utilization_pct if snapshot else 0.0
    
    if margin_util > 95:
        st.error(f"🚨 CRITICAL: Margin utilization {margin_util:.1f}% - AUTO-CLOSE TRIGGERED")
    elif margin_util > 90:
        st.warning(f"⚠️ DANGER: Margin utilization {margin_util:.1f}% - Manual intervention recommended")
    elif margin_util > 80:
        st.info(f"ℹ️ HIGH: Margin utilization {margin_util:.1f}% - monitor closely")


def display_liquidation_meter(snapshot, config_dict):
    """Display visual liquidation risk meter."""
    if not snapshot or not snapshot.active_position:
        st.info("📊 Liquidation Meter: No active position")
        return
    
    st.subheader("⚡ Liquidation Risk Meter")
    
    pos = snapshot.active_position
    entry_price = pos.entry_price
    liquidation_price = snapshot.leverage_liquidation_price if snapshot else entry_price
    current_price = snapshot.last_known_btc_price if snapshot else entry_price
    
    if liquidation_price <= 0 or current_price <= 0:
        st.warning("⚠️ Liquidation meter unavailable - insufficient data")
        return
    
    # Calculate distance to liquidation
    if pos.side == "long":
        distance = current_price - liquidation_price
        distance_pct = (distance / current_price) * 100 if current_price > 0 else 0
    else:  # short
        distance = liquidation_price - current_price
        distance_pct = (distance / current_price) * 100 if current_price > 0 else 0
    
    # Clamp to 0-100 for progress bar
    progress_val = min(max(distance_pct / 10, 0), 1.0)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # Color-coded progress bar
        if distance_pct < 5:
            st.error(f"🚨 EXTREME: {distance_pct:.1f}% to liquidation")
            st.progress(progress_val, text=f"Distance: ${distance:,.2f} ({distance_pct:.1f}%)")
        elif distance_pct < 10:
            st.warning(f"⚠️ DANGER ZONE: {distance_pct:.1f}% to liquidation")
            st.progress(progress_val, text=f"Distance: ${distance:,.2f} ({distance_pct:.1f}%)")
        elif distance_pct < 20:
            st.info(f"ℹ️ HIGH RISK: {distance_pct:.1f}% to liquidation")
            st.progress(progress_val, text=f"Distance: ${distance:,.2f} ({distance_pct:.1f}%)")
        else:
            st.success(f"✅ SAFE: {distance_pct:.1f}% to liquidation")
            st.progress(progress_val, text=f"Distance: ${distance:,.2f} ({distance_pct:.1f}%)")
    
    with col2:
        st.metric(
            "SL Buffer",
            f"{distance_pct:.1f}%",
            help="Distance from current price to liquidation"
        )
    
    # Detailed breakdown
    with st.expander("📋 Liquidation Details"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Entry Price", f"${entry_price:,.2f}")
        with col2:
            st.metric("Current Price", f"${current_price:,.2f}")
        with col3:
            st.metric("Liquidation Price", f"${liquidation_price:,.2f}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Stop Loss", f"${pos.sl_price:,.2f}")
        with col2:
            buffer_from_liq = abs(pos.sl_price - liquidation_price)
            st.metric("SL-to-Liquidation Buffer", f"${buffer_from_liq:,.2f}")




def main():
    """Main dashboard UI."""
    st.title("🤖 BTC/USDT Futures Bot - Dashboard")
    
    # Load leverage configuration
    loop = asyncio.new_event_loop()
    try:
        config_dict = loop.run_until_complete(get_leverage_config())
    finally:
        loop.close()
    
    # Check if setup is required
    if not config_dict:
        setup_wizard()
        return  # Stop execution if setup not complete
    
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
        
        # Configuration info (collapsible)
        with st.expander("⚙️ Current Configuration"):
            st.metric("Trading Capital", f"${config_dict.get('trading_capital', 1000):,.2f}")
            st.metric("Leverage", f"{config_dict.get('leverage', 5)}x")
            st.metric("Max Risk/Trade", f"{config_dict.get('max_risk_pct', 2)}%")
            st.metric("Max Drawdown", f"{config_dict.get('max_drawdown_pct', 10)}%")
            st.metric("Margin Mode", config_dict.get('margin_mode', 'isolated').upper())
            
            if st.button("🔄 Reconfigure", use_container_width=True):
                st.session_state.setup_wizard_complete = False
                st.rerun()
        
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
        
        # Display leverage metrics panel
        display_leverage_metrics(snapshot, config_dict)
        st.divider()
        
        # Display liquidation meter
        display_liquidation_meter(snapshot, config_dict)
        st.divider()
        
        if snapshot and snapshot.active_position:
            pos = snapshot.active_position
            
            st.subheader("Position Details")
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
