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
from paper_executor import PaperExecutor
from ghost_engine import GhostEngine
from live_executor import LiveExecutor
from risk_monitor import RiskMonitor


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
        external_data = await fetch_all_external_data()
        return external_data
    except Exception as e:
        st.error(f"External feeds error: {e}")
        return {}


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
            try:
                loop.run_until_complete(redis_state_sync.close())
            except Exception:
                pass
            loop.close()
        
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
    tab_market, tab_position, tab_account, tab_paper, tab_ghost, tab_live, tab_bot, tab_logs = st.tabs(["📊 Market", "💼 Position", "💰 Account", "📄 Paper Mode", "👻 Ghost Mode", "🟡 Live Mode", "🤖 Bot Control", "📋 Logs"])
    
    # === MARKET TAB ===
    with tab_market:
        st.subheader("Market Context & External Feeds")
        
        # Fetch external data
        loop = asyncio.new_event_loop()
        try:
            external_data = loop.run_until_complete(get_external_context())
        finally:
            loop.close()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            fear_greed_data = external_data.get("fear_greed", {})
            fear_greed = fear_greed_data.get("value", -1) if isinstance(fear_greed_data, dict) else -1
            if fear_greed >= 0:
                st.metric("Fear & Greed", f"{fear_greed:.0f}", 
                         help="0=Extreme Fear, 100=Extreme Greed")
        
        with col2:
            binance_data = external_data.get("binance_structure", {})
            funding_rate = binance_data.get("funding_rate", -999) if isinstance(binance_data, dict) else -999
            if funding_rate != -999:
                st.metric("Funding Rate", f"{funding_rate:.3f}%",
                         help="Positive=Longs pay shorts")
        
        with col3:
            ls_ratio = binance_data.get("ls_ratio", -1) if isinstance(binance_data, dict) else -1
            if ls_ratio >= 0:
                st.metric("Long/Short Ratio", f"{ls_ratio:.3f}",
                         help=">1.0 = More longs")
        
        with col4:
            st.metric("Timestamp", datetime.now().strftime("%H:%M:%S"),
                     help="Dashboard refresh time")
        
        # Market structure
        if external_data:
            with st.expander("📈 Market Structure"):
                st.json(external_data)
    
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
            if snapshot and snapshot.rolling_24h_pnl:
                st.metric("24h PnL", f"${snapshot.rolling_24h_pnl:,.2f}")
        
        # Account summary
        if snapshot:
            st.divider()
            st.subheader("Account Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Account Balance", f"${snapshot.account_balance:,.2f}")
            with col2:
                daily_pnl = snapshot.rolling_24h_pnl if snapshot else 0
                st.metric("24h PnL", f"${daily_pnl:,.2f}")
            with col3:
                pct = (daily_pnl / max(snapshot.account_balance, 1)) * 100
                st.metric("24h Return", f"{pct:.2f}%")
    
    # === PAPER MODE TAB ===
    with tab_paper:
        st.subheader("📄 Paper Trading Simulation")
        st.info("💡 Trade with simulated capital to validate strategy before live trading")
        
        from bot_manager import BotManager

        # Prefer executor managed by BotManager, fall back to session or local instance
        paper_executor = None
        manager_exec = BotManager.get_executor("paper")
        if "paper_executor" in st.session_state and st.session_state.get("paper_executor") is not None:
            paper_executor = st.session_state.get("paper_executor")
        elif manager_exec is not None:
            paper_executor = manager_exec
            st.session_state.paper_executor = manager_exec
        else:
            paper_executor = PaperExecutor(starting_capital=10000.0)
            st.session_state.paper_executor = paper_executor
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶️ Generate Sample Trade", key="paper_sample"):
                asyncio.run(paper_executor.place_order(
                    "BTC/USDT", "buy", 0.1, 45000.0
                ))
                st.success("✅ Sample buy order placed")
        
        with col2:
            if st.button("🗑️ Reset Portfolio", key="paper_reset"):
                asyncio.run(paper_executor.reset_portfolio())
                st.info("✅ Portfolio reset")
        
        st.divider()
        
        # Portfolio snapshot
        snapshot_data = asyncio.run(paper_executor.get_portfolio_summary())
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Starting Capital", f"${snapshot_data.starting_capital:,.0f}")
        with col2:
            st.metric("Current Value", f"${snapshot_data.current_value:,.2f}")
        with col3:
            st.metric("Total P&L", f"${snapshot_data.total_pnl:,.2f}",
                     delta=f"{(snapshot_data.total_pnl/snapshot_data.starting_capital*100):.2f}%")
        with col4:
            st.metric("Win Rate", f"{snapshot_data.win_rate:.1f}%")
        
        st.divider()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Closed Trades", int(snapshot_data.closed_trades_count))
        with col2:
            st.metric("Open Positions", int(snapshot_data.open_positions_count))
        with col3:
            st.metric("Wins", int(snapshot_data.win_count))
        with col4:
            st.metric("Losses", int(snapshot_data.loss_count))
        
        # Recent trades
        st.divider()
        st.subheader("Recent Trades")
        history = asyncio.run(paper_executor.get_trade_history(limit=10))
        if history:
            for trade in history:
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.caption(f"📊 {trade['symbol']}")
                    with col2:
                        st.caption(f"Entry: ${trade['entry_price']:.2f}")
                    with col3:
                        st.caption(f"Exit: ${trade['exit_price']:.2f}")
                    with col4:
                        pnl_color = "🟢" if trade['realized_pnl'] > 0 else "🔴"
                        st.caption(f"{pnl_color} ${trade['realized_pnl']:.2f}")
        else:
            st.text("No trades yet")
    
    # === GHOST MODE TAB ===
    with tab_ghost:
        st.subheader("👻 Ghost Mode - Signal Validation")
        st.info("💡 Generate trading signals without execution to validate strategy accuracy")
        
        from bot_manager import BotManager

        # Prefer executor managed by BotManager, fall back to session or local instance
        ghost_engine = None
        manager_ghost = BotManager.get_executor("ghost")
        if "ghost_engine" in st.session_state and st.session_state.get("ghost_engine") is not None:
            ghost_engine = st.session_state.get("ghost_engine")
        elif manager_ghost is not None:
            ghost_engine = manager_ghost
            st.session_state.ghost_engine = manager_ghost
        else:
            ghost_engine = GhostEngine()
            st.session_state.ghost_engine = ghost_engine
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Generate Signal")
            signal_type = st.selectbox("Signal Type", ["buy", "sell"])
            price = st.number_input("Price", value=45000.0, step=100.0)
            confidence = st.slider("Confidence", 0.0, 1.0, 0.5, step=0.1)
            
            if st.button("📡 Generate Signal"):
                success, signal_id = asyncio.run(ghost_engine.generate_signal(
                    "BTC/USDT", signal_type, price, confidence, "Manual test signal"
                ))
                if success:
                    st.success(f"✅ Signal generated: {signal_id}")
                    st.session_state.last_signal_id = signal_id
        
        with col2:
            st.subheader("Trace Signal Outcome")
            active_signals = asyncio.run(ghost_engine.get_active_signals())
            if active_signals:
                signal_options = {s['signal_id']: f"{s['signal_type'].upper()} @ ${s['price']:.2f}" for s in active_signals}
                selected_signal = st.selectbox("Select Signal", list(signal_options.keys()), format_func=lambda x: signal_options[x])
                close_price = st.number_input("Close Price", value=45500.0, step=100.0)
                
                if st.button("✓ Trace Outcome"):
                    success, details = asyncio.run(ghost_engine.trace_signal(selected_signal, close_price))
                    if success:
                        pnl = details.get('hypothetical_pnl', 0)
                        is_profit = pnl > 0
                        emoji = "🟢" if is_profit else "🔴"
                        st.success(f"{emoji} Signal traced - P&L: ${pnl:.2f}")
        
        st.divider()
        
        # Signal metrics
        metrics = asyncio.run(ghost_engine.calculate_metrics())
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Signals", metrics.total_signals)
        with col2:
            st.metric("Accuracy", f"{metrics.accuracy_rate:.1f}%")
        with col3:
            st.metric("Avg Win", f"${metrics.avg_win:.2f}")
        with col4:
            st.metric("Avg Loss", f"${metrics.avg_loss:.2f}")
        
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Profit Factor", f"{metrics.profit_factor:.2f}" if metrics.profit_factor != float('inf') else "∞")
        with col2:
            st.metric("Expectancy", f"${metrics.expectancy:.2f}")
        with col3:
            st.metric("Max Drawdown", f"${metrics.max_drawdown:.2f}")
        
        # Signal history
        st.divider()
        st.subheader("Signal History")
        history = asyncio.run(ghost_engine.get_signal_history(limit=15))
        if history:
            for signal in history:
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        signal_emoji = "🔼" if signal['signal_type'] == 'buy' else "🔽"
                        st.caption(f"{signal_emoji} {signal['signal_type'].upper()}")
                    with col2:
                        st.caption(f"Entry: ${signal['price']:.2f}")
                    with col3:
                        st.caption(f"Close: ${signal.get('close_price', 'N/A')}")
                    with col4:
                        if signal.get('hypothetical_pnl'):
                            pnl_color = "🟢" if signal['is_profitable'] else "🔴"
                            st.caption(f"{pnl_color} ${signal['hypothetical_pnl']:.2f}")
        else:
            st.text("No signals yet")
    
    # === LIVE MODE TAB ===
    with tab_live:
        st.subheader("🟡 Live Trading Mode")
        st.warning("🚨 Operates with real capital – use extreme caution and obtain approval")
        
        # maintain executor and risk monitor in session state
        if "live_executor" not in st.session_state:
            st.session_state.live_executor = LiveExecutor()
            st.session_state.risk_monitor = RiskMonitor()
        live_executor = st.session_state.live_executor
        risk_monitor = st.session_state.risk_monitor
        
        # approval controls
        if st.button("📝 Request Live Approval"):
            approved, msg = asyncio.run(live_executor.request_live_approval(user_confirmation=True))
            if approved:
                st.success(msg)
            else:
                st.error(msg)
        st.write(f"Approval status: **{live_executor.approval_status.value}**")
        
        st.divider()
        
        # order placement form
        st.subheader("Place Live Order")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            symbol = st.selectbox("Symbol", ["BTC/USDT", "ETH/USDT"])
        with col2:
            side = st.selectbox("Side", ["buy", "sell"])
        with col3:
            quantity = st.number_input("Qty", value=0.001, step=0.001)
        with col4:
            price = st.number_input("Price", value=45000.0, step=100.0)
        
        if st.button("▶️ Execute Live Order"):
            success, order_id, details = asyncio.run(live_executor.place_order(symbol, side, quantity, price))
            if success:
                st.success(f"Order executed: {order_id}")
            else:
                st.error(f"Order rejected: {details}")
        
        st.divider()
        
        # summary and risk tools
        summary = asyncio.run(live_executor.get_summary())
        st.subheader("Live Summary")
        st.json(summary)
        
        st.divider()
        margin = st.slider("Margin Utilization (%)", 0.0, 100.0, 0.0)
        if st.button("Check Margin Safety"):
            status = asyncio.run(live_executor.check_margin_safety(margin))
            st.json(status)
        
        if st.button("📊 Generate Risk Report"):
            report = asyncio.run(risk_monitor.generate_risk_report(
                account_balance=summary['account_balance'],
                account_equity=summary['account_balance'],
                margin_utilization=margin,
                daily_loss=summary['daily_pnl'],
                max_daily_loss=summary['max_daily_loss'],
                open_positions=summary['open_positions'],
                equity_history=[summary['account_balance'], summary['account_balance']+10],
            ))
            st.json(report)
    
    # === BOT CONTROL TAB ===
    with tab_bot:
        st.subheader("🤖 Bot Control Panel")
        
        # Import bot manager
        from bot_manager import BotManager
        
        # Get current state
        loop = asyncio.new_event_loop()
        try:
            bot_pid = loop.run_until_complete(redis_state_sync.get_bot_process_id())
            current_mode = loop.run_until_complete(redis_state_sync.get_mode())
            bot_status = loop.run_until_complete(redis_state_sync.get_bot_status())
        finally:
            try:
                loop.run_until_complete(redis_state_sync.close())
            except Exception:
                pass
            loop.close()
        
        # Check if bot is actually running
        bot_running = asyncio.run(BotManager.is_bot_running(bot_pid)) if bot_pid else False
        
        # Mode selector
        st.subheader("Mode Selection")
        col1, col2 = st.columns([2, 1])
        
        with col1:
            selected_mode = st.selectbox(
                "Trading Mode",
                ["Backtest", "Paper", "Ghost", "Live"],
                index=["backtest", "paper", "ghost", "live"].index(current_mode.lower()),
                help="Select the trading mode to run"
            )
        with col2:
            run_inprocess = st.checkbox("Run in-process (no subprocess)", value=False, help="Run the bot inside the dashboard process for quick testing")
        
        mode_map = {"Backtest": "backtest", "Paper": "paper", "Ghost": "ghost", "Live": "live"}
        selected_mode_lower = mode_map[selected_mode]
        
        # Status indicator
        if bot_running:
            st.success(f"🟢 **Bot Running** | Mode: **{selected_mode}** | PID: {bot_pid}")
        else:
            st.info(f"🔴 **Bot Stopped** | Ready to start")
        
        # Control buttons
        st.subheader("Control")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("▶️ START", use_container_width=True, disabled=bot_running):
                with st.spinner(f"Starting bot in {selected_mode} mode..."):
                    try:
                        if run_inprocess:
                            ok = BotManager.start_inprocess(selected_mode_lower)
                            pid = None
                            if ok:
                                # indicate running via session state
                                st.session_state.bot_inprocess = True
                        else:
                            pid = asyncio.run(BotManager.start_bot(selected_mode_lower))
                        if pid or (run_inprocess and st.session_state.get("bot_inprocess")):
                            # Store PID in Redis
                            write_loop = asyncio.new_event_loop()
                            try:
                                if pid:
                                    write_loop.run_until_complete(redis_state_sync.set_bot_process_id(pid))
                                write_loop.run_until_complete(redis_state_sync.set_mode(selected_mode_lower))
                                write_loop.run_until_complete(redis_state_sync.set_bot_status("running"))
                                write_loop.run_until_complete(redis_state_sync.set_bot_started_at(datetime.utcnow().isoformat()))
                            finally:
                                try:
                                    write_loop.run_until_complete(redis_state_sync.close())
                                except Exception:
                                    pass
                                write_loop.close()
                            # Sync executor instance from BotManager into session_state when available
                            try:
                                exec_inst = BotManager.get_executor(selected_mode_lower)
                                if exec_inst is not None:
                                    st.session_state.executor = exec_inst
                            except Exception:
                                pass

                            st.success(f"✅ Bot started with PID {pid}")
                        else:
                            st.error("❌ Failed to start bot")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        with col2:
            if st.button("⏹️ STOP", use_container_width=True, disabled=not bot_running):
                with st.spinner("Stopping bot..."):
                    try:
                        # choose stop method depending on in-process flag
                        if st.session_state.get("bot_inprocess"):
                            success = BotManager.stop_inprocess()
                            st.session_state.bot_inprocess = False
                        else:
                            success = asyncio.run(BotManager.stop_bot(bot_pid))
                        if success:
                            # Clear PID in Redis
                            clear_loop = asyncio.new_event_loop()
                            try:
                                clear_loop.run_until_complete(redis_state_sync.clear_bot_process_id())
                                clear_loop.run_until_complete(redis_state_sync.set_bot_status("stopped"))
                            finally:
                                try:
                                    clear_loop.run_until_complete(redis_state_sync.close())
                                except Exception:
                                    pass
                                clear_loop.close()
                            # clear any in-memory executor refs
                            if "executor" in st.session_state:
                                try:
                                    del st.session_state["executor"]
                                except Exception:
                                    pass
                            # also clear mode-specific session entries
                            for k in ("paper_executor", "ghost_engine", "live_executor", "risk_monitor"):
                                if k in st.session_state:
                                    try:
                                        del st.session_state[k]
                                    except Exception:
                                        pass

                            st.success("✅ Bot stopped")
                        else:
                            st.error("❌ Failed to stop bot")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        with col3:
            if st.button("🔴 KILL", use_container_width=True, disabled=not bot_running):
                with st.spinner("Force killing bot..."):
                    try:
                        import signal
                        import os
                        if bot_pid:
                            try:
                                os.kill(bot_pid, signal.SIGKILL)
                                # Clear PID in Redis
                                kill_loop = asyncio.new_event_loop()
                                try:
                                    kill_loop.run_until_complete(redis_state_sync.clear_bot_process_id())
                                    kill_loop.run_until_complete(redis_state_sync.set_bot_status("stopped"))
                                finally:
                                    try:
                                        kill_loop.run_until_complete(redis_state_sync.close())
                                    except Exception:
                                        pass
                                    kill_loop.close()
                                st.success("🔴 Bot force killed")
                            except ProcessLookupError:
                                st.warning("Process already terminated")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        # Output log viewer
        st.subheader("Bot Output Log")
        output_lines = BotManager.get_bot_output(lines=50)
        
        log_container = st.container(border=True)
        with log_container:
            log_text = "\n".join(output_lines)
            st.code(log_text, language="", line_numbers=True)
        
        # Auto-refresh indicator
        st.caption("💡 Output updates every dashboard refresh")
    
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

    # === ACCOUNT TAB ===
    with tab_account:
        st.subheader("💰 Live Account Info")

        # Attempt to create exchange client and fetch account info
        try:
            from exchange_client import ExchangeClient
            from config import cfg

            if cfg is None:
                st.warning("Exchange config not loaded; unable to fetch live account info.")
            else:
                # Build a minimal config dict for ExchangeClient
                exch_conf = {"exchange": cfg.exchange.dict() if hasattr(cfg, 'exchange') else {},
                             "governor": cfg.governor.dict() if hasattr(cfg, 'governor') else {},
                             "binance_time": cfg.binance_time.dict() if hasattr(cfg, 'binance_time') else {}}

                client = ExchangeClient(exch_conf)
                loop = asyncio.new_event_loop()
                try:
                    balance = loop.run_until_complete(client.get_account_balance())
                    leverage = loop.run_until_complete(client.get_account_leverage())
                    margin = loop.run_until_complete(client.get_margin_info())
                    position = loop.run_until_complete(client.get_position_info())
                finally:
                    try:
                        loop.run_until_complete(client.close())
                    except Exception:
                        pass
                    loop.close()

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("💰 Balance", f"${balance:,.2f}")
                with col2:
                    st.metric("📊 Leverage", f"{leverage}x")
                with col3:
                    st.metric("📈 Margin Used", f"{margin.get('utilization_pct', 0.0):.1f}%")
                with col4:
                    st.metric("✅ Available", f"${margin.get('available_margin', 0.0):,.2f}")

                st.markdown("---")
                if position:
                    st.subheader("Open Position")
                    st.write(position)
                else:
                    st.info("No open position detected")

        except Exception as e:
            st.error(f"Failed to fetch account info: {e}")


if __name__ == "__main__":
    main()
