def test_risk_importable():
    import importlib

    mod = importlib.import_module('risk')
    assert hasattr(mod, 'compute_position_size')
