def test_integration_smoke():
    # Basic smoke test: ensure project root modules import
    import importlib
    modules = ['config', 'redis_state', 'exchange_client', 'data_feed', 'strategy']
    for m in modules:
        importlib.import_module(m)
