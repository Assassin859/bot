def test_data_feed_importable():
    import importlib

    mod = importlib.import_module('data_feed')
    assert hasattr(mod, 'DataFeed')
