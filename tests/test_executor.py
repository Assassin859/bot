def test_executor_importable():
    import importlib

    mod = importlib.import_module('executor')
    assert hasattr(mod, 'execute_entry_plan')
