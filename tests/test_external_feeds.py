import asyncio


def test_external_feeds_importable():
    import importlib

    mod = importlib.import_module('external_feeds')
    assert hasattr(mod, 'fetch_binance_futures_structure')
