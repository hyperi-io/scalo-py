"""
Basic import tests for hs_lib.
"""


def test_hs_lib_import():
    """Test that hs_lib can be imported."""
    import hs_lib

    assert hs_lib is not None
    assert hs_lib.__version__ is not None


def test_submodules_import():
    """Test that all submodules can be imported."""
    from hs_lib import config, harness, logger

    assert config is not None
    assert harness is not None
    assert logger is not None


def test_convenience_imports():
    """Test convenience function imports."""
    from hs_lib import Application, get_logging_config, logger

    assert logger is not None
    assert get_logging_config is not None
    assert Application is not None
