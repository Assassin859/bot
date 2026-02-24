def test_dashboard_importable():
    import importlib

    mod = importlib.import_module('dashboard')
    assert hasattr(mod, 'main')
