def test_backtest_importable():
    import importlib

    mod = importlib.import_module('backtest')
    assert hasattr(mod, 'run_backtest')
