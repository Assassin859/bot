def test_indicators_importable():
    import importlib

    mod = importlib.import_module('indicators')
    assert hasattr(mod, 'bid_ask_spread')
