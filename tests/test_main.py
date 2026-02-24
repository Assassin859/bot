def test_main_importable():
    import importlib

    mod = importlib.import_module('main')
    assert hasattr(mod, 'main')
