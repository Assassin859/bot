def test_logging_utils_importable():
    import importlib

    mod = importlib.import_module('logging_utils')
    assert hasattr(mod, 'log_event')
