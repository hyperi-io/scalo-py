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
    from hyperlib import config, container, logger, sampling, timeout

    assert config is not None
    assert logger is not None
    assert timeout is not None
    assert container is not None
    assert sampling is not None


def test_convenience_imports():
    """Test convenience function imports."""
    from hyperlib import get_logger, get_logging_config, setup_logger

    assert get_logger is not None
    assert get_logging_config is not None
    assert setup_logger is not None
