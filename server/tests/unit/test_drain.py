"""Tests for drain mode state management."""

from kfchess.drain import is_draining, set_draining


class TestDrainState:
    """Tests for drain state flag."""

    def setup_method(self) -> None:
        """Reset drain state before each test."""
        set_draining(False)

    def test_is_draining_default_false(self) -> None:
        """Drain mode is off by default."""
        assert is_draining() is False

    def test_set_draining_true(self) -> None:
        """Setting drain mode to True makes is_draining return True."""
        set_draining(True)
        assert is_draining() is True

    def test_set_draining_false(self) -> None:
        """Setting drain mode to False after True resets it."""
        set_draining(True)
        assert is_draining() is True
        set_draining(False)
        assert is_draining() is False

    def test_set_draining_default_arg(self) -> None:
        """set_draining() with no argument defaults to True."""
        set_draining()
        assert is_draining() is True

    def test_set_draining_idempotent(self) -> None:
        """Setting drain mode True multiple times is idempotent."""
        set_draining(True)
        set_draining(True)
        assert is_draining() is True
