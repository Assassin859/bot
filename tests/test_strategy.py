def test_strategy_importable():
    import importlib

    mod = importlib.import_module('strategy')
    assert hasattr(mod, 'evaluate_signal')
