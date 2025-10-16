"""
Basic import tests for hyperlib.
"""


def test_hyperlib_import():
    """Test that hyperlib can be imported."""
    import hyperlib

    assert hyperlib is not None
    assert hyperlib.__version__ is not None


def test_submodules_import():
    """Test that all submodules can be imported."""
    from hyperlib import config, harness, logger, sampling

    assert config is not None
    assert harness is not None
    assert logger is not None
    assert sampling is not None


def test_convenience_imports():
    """Test convenience function imports."""
    from hyperlib import Application, get_logging_config, logger

    assert logger is not None
    assert get_logging_config is not None
    assert Application is not None
