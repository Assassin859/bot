"""External data layer: async fetchers for Binance structure, fear/greed, on-chain data.

Provides async functions to fetch external market data with timeouts and fallbacks.
All functions return neutral defaults on failure (logged as INFO: EXTERNAL_FEED_FALLBACK).
TTL caching is handled by redis_state.py.
"""
from __future__ import annotations
import asyncio
import time
from typing import Dict, Any, Optional
import aiohttp
from logging_utils import log_event


FETCH_TIMEOUT = 5.0  # Timeout for all external fetches (seconds)


async def fetch_binance_futures_structure(
    symbol: str = "BTCUSDT",
) -> Dict[str, Any]:
    """Fetch Binance Futures market structure: funding rate, OI, LS ratio.
    
    Returns on success:
        {
            "funding_rate": float (e.g., 0.0001),
            "oi": float (open interest in USD),
            "ls_ratio": float (long/short ratio, 1.0 = balanced),
            "timestamp": int (ms),
        }
    
    Returns on failure (neutral defaults):
        {"funding_rate": 0.0, "oi": 0.0, "ls_ratio": 1.0, "timestamp": 0}
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch funding rate from Binance
            url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=1"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)) as resp:
                if resp.status != 200:
                    raise Exception(f"Binance API returned {resp.status}")
                
                data = await resp.json()
                if not data:
                    raise Exception("Empty response from funding rate API")
                
                funding_rate = float(data[0].get("fundingRate", 0.0))
                timestamp = int(data[0].get("fundingTime", int(time.time() * 1000)))
        
        # Fetch OI and LS ratio (from Taapi or similar - for now use placeholder)
        # In production, integrate with Taapi.io or CoinGlass API
        oi = 1000000000.0  # Placeholder: 1B USD
        ls_ratio = 1.0  # Placeholder: balanced
        
        return {
            "funding_rate": funding_rate,
            "oi": oi,
            "ls_ratio": ls_ratio,
            "timestamp": timestamp,
        }
    
    except asyncio.TimeoutError:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "binance_futures_structure", "reason": "timeout"})
        return {"funding_rate": 0.0, "oi": 0.0, "ls_ratio": 1.0, "timestamp": 0}
    except Exception as e:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "binance_futures_structure", "reason": str(e)})
        return {"funding_rate": 0.0, "oi": 0.0, "ls_ratio": 1.0, "timestamp": 0}


async def fetch_fear_greed_index() -> Dict[str, Any]:
    """Fetch Crypto Fear & Greed Index from alternative.me API.
    
    Returns on success:
        {
            "value": int (0-100, 0=max fear, 100=max greed),
            "timestamp": int (seconds since epoch),
        }
    
    Returns on failure (neutral):
        {"value": 50, "timestamp": 0}
    """
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.alternative.me/fng/?limit=1&format=json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)) as resp:
                if resp.status != 200:
                    raise Exception(f"API returned {resp.status}")
                
                data = await resp.json()
                if not data.get("data"):
                    raise Exception("Empty data in Fear & Greed response")
                
                entry = data["data"][0]
                value = int(entry.get("value", 50))
                timestamp = int(entry.get("timestamp", int(time.time())))
        
        return {
            "value": value,
            "timestamp": timestamp,
        }
    
    except asyncio.TimeoutError:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "fear_greed_index", "reason": "timeout"})
        return {"value": 50, "timestamp": 0}
    except Exception as e:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "fear_greed_index", "reason": str(e)})
        return {"value": 50, "timestamp": 0}


async def fetch_onchain_flow(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Fetch on-chain Bitcoin flow data.
    
    Requires CryptoQuant API key. Without it, returns neutral default.
    
    Args:
        api_key: CryptoQuant API key (set from environment)
    
    Returns on success:
        {
            "value": float (on-chain flow in BTC or USD),
            "timestamp": int (ms),
        }
    
    Returns on failure or missing API key:
        {"value": 0.0, "timestamp": 0}
    """
    if not api_key:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "onchain_flow", "reason": "no_api_key"})
        return {"value": 0.0, "timestamp": 0}
    
    try:
        async with aiohttp.ClientSession() as session:
            # CryptoQuant API endpoint for exchange flow (placeholder)
            url = "https://api.cryptoquant.com/v1/btc/exchange-flows/exchange-outflow"
            headers = {"Authorization": f"Bearer {api_key}"}
            
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"CryptoQuant API returned {resp.status}")
                
                data = await resp.json()
                if not data or "data" not in data:
                    raise Exception("Invalid CryptoQuant response format")
                
                flow_data = data["data"]
                # Assume flow_data is a list with most recent entry first
                if isinstance(flow_data, list) and flow_data:
                    value = float(flow_data[0].get("value", 0.0))
                    timestamp = int(flow_data[0].get("timestamp", int(time.time() * 1000)))
                else:
                    value = float(flow_data.get("value", 0.0))
                    timestamp = int(flow_data.get("timestamp", int(time.time() * 1000)))
        
        return {
            "value": value,
            "timestamp": timestamp,
        }
    
    except asyncio.TimeoutError:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "onchain_flow", "reason": "timeout"})
        return {"value": 0.0, "timestamp": 0}
    except Exception as e:
        log_event("INFO", {"msg": "EXTERNAL_FEED_FALLBACK", "feed": "onchain_flow", "reason": str(e)})
        return {"value": 0.0, "timestamp": 0}


async def fetch_all_external_data(api_key: Optional[str] = None) -> Dict[str, Any]:
    """Fetch all external data in parallel.
    
    Args:
        api_key: CryptoQuant API key for on-chain data
    
    Returns:
        Dictionary with keys:
            - binance_structure: Dict with funding_rate, oi, ls_ratio, timestamp
            - fear_greed: Dict with value, timestamp
            - onchain_flow: Dict with value, timestamp
    """
    results = await asyncio.gather(
        fetch_binance_futures_structure(),
        fetch_fear_greed_index(),
        fetch_onchain_flow(api_key),
        return_exceptions=False,
    )
    
    return {
        "binance_structure": results[0],
        "fear_greed": results[1],
        "onchain_flow": results[2],
    }
