def test_dashboard_importable():
    import importlib

    mod = importlib.import_module('dashboard')
    assert hasattr(mod, 'main')
    # new mode executors should be importable through dashboard namespace
    assert hasattr(mod, 'PaperExecutor')
    assert hasattr(mod, 'GhostEngine')
    assert hasattr(mod, 'LiveExecutor')
    assert hasattr(mod, 'RiskMonitor')
