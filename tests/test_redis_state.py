def test_redis_state_module_exists():
    import importlib

    mod = importlib.import_module('redis_state')
    assert mod is not None
