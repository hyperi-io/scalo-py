"""
Basic import tests for hs_pylib.
"""


def test_hs_pylib_import():
    """Test that hs_pylib can be imported."""
    import hs_pylib

    assert hs_pylib is not None
    assert hs_pylib.__version__ is not None


def test_submodules_import():
    """Test that all submodules can be imported."""
    from hs_pylib import config, harness, logger

    assert config is not None
    assert harness is not None
    assert logger is not None


def test_convenience_imports():
    """Test convenience function imports."""
    from hs_pylib import Application, get_logging_config, logger

    assert logger is not None
    assert get_logging_config is not None
    assert Application is not None
