"""
Basic import tests for hyperi_pylib.
"""


def test_hyperi_pylib_import():
    """Test that hyperi_pylib can be imported."""
    import hyperi_pylib

    assert hyperi_pylib is not None
    assert hyperi_pylib.__version__ is not None


def test_submodules_import():
    """Test that all submodules can be imported."""
    from hyperi_pylib import config, harness, logger

    assert config is not None
    assert harness is not None
    assert logger is not None


def test_convenience_imports():
    """Test convenience function imports."""
    from hyperi_pylib import get_logging_config, logger

    assert logger is not None
    assert get_logging_config is not None
