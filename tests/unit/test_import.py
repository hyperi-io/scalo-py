"""
Basic import tests for scalo.
"""


def test_scalo_import():
    """Test that scalo can be imported."""
    import scalo

    assert scalo is not None
    assert scalo.__version__ is not None


def test_submodules_import():
    """Test that all submodules can be imported."""
    from scalo import config, harness, logger

    assert config is not None
    assert harness is not None
    assert logger is not None


def test_convenience_imports():
    """Test convenience function imports."""
    from scalo import get_logging_config, logger

    assert logger is not None
    assert get_logging_config is not None
