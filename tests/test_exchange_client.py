def test_exchange_client_importable():
    import importlib

    mod = importlib.import_module('exchange_client')
    assert hasattr(mod, 'ExchangeClient')
