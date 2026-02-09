"""Tests for campaign level definitions."""

import pytest

from kfchess.campaign.board_parser import parse_board_string
from kfchess.campaign.levels import (
    BELT_NAMES,
    LEVELS,
    MAX_BELT,
    get_belt_levels,
    get_level,
)
from kfchess.game.pieces import PieceType


class TestLevelDefinitions:
    """Tests for level data integrity."""

    def test_all_32_levels_defined(self) -> None:
        """Verify all 32 legacy levels exist."""
        assert len(LEVELS) >= 32

    def test_all_levels_have_required_fields(self) -> None:
        """Verify each level has required fields."""
        for level in LEVELS:
            assert level.level_id >= 0
            assert level.belt >= 1
            assert level.speed in ("standard", "lightning")
            assert level.board_str.strip()

    def test_level_belt_mapping(self) -> None:
        """Verify levels are in correct belts."""
        for level in LEVELS[:32]:
            expected_belt = (level.level_id // 8) + 1
            assert level.belt == expected_belt, f"Level {level.level_id} in wrong belt"

    def test_belt_1_is_standard_speed(self) -> None:
        """Verify belt 1 (tutorial) uses standard speed."""
        belt_1_levels = get_belt_levels(1)
        for level in belt_1_levels:
            assert level.speed == "standard", f"Level {level.level_id} should be standard"

    def test_belt_3_is_lightning_speed(self) -> None:
        """Verify belt 3 (green) uses lightning speed."""
        belt_3_levels = get_belt_levels(3)
        for level in belt_3_levels:
            assert level.speed == "lightning", f"Level {level.level_id} should be lightning"

    def test_all_level_boards_parse(self) -> None:
        """Verify all level board strings are parseable."""
        for level in LEVELS:
            try:
                board = parse_board_string(level.board_str, level.board_type)
                # Every level needs at least one king
                kings = [p for p in board.pieces if p.type == PieceType.KING]
                assert len(kings) >= 1, f"Level {level.level_id} has no kings"
            except Exception as e:
                pytest.fail(f"Level {level.level_id} failed to parse: {e}")

    def test_all_levels_have_player_1_king(self) -> None:
        """Verify all levels have a king for player 1."""
        for level in LEVELS:
            board = parse_board_string(level.board_str, level.board_type)
            king = board.get_king(1)
            assert king is not None, f"Level {level.level_id} missing player 1 king"

    def test_all_levels_have_titles(self) -> None:
        """Verify all levels have titles."""
        for level in LEVELS:
            assert level.title, f"Level {level.level_id} missing title"

    def test_all_levels_have_descriptions(self) -> None:
        """Verify all levels have descriptions."""
        for level in LEVELS:
            assert level.description, f"Level {level.level_id} missing description"

    def test_belt_level_property(self) -> None:
        """Verify belt_level property calculates correctly."""
        level_0 = get_level(0)
        assert level_0 is not None
        assert level_0.belt_level == 0

        level_7 = get_level(7)
        assert level_7 is not None
        assert level_7.belt_level == 7

        level_8 = get_level(8)
        assert level_8 is not None
        assert level_8.belt_level == 0  # First level of belt 2


class TestGetLevel:
    """Tests for get_level function."""

    def test_get_valid_level(self) -> None:
        """Test getting a valid level by ID."""
        level = get_level(0)
        assert level is not None
        assert level.level_id == 0
        assert level.belt == 1

    def test_get_last_level(self) -> None:
        """Test getting the last defined level."""
        level = get_level(55)
        assert level is not None
        assert level.level_id == 55
        assert level.belt == 7

    def test_get_invalid_level_returns_none(self) -> None:
        """Test getting invalid level returns None."""
        assert get_level(-1) is None
        assert get_level(999) is None


class TestGetBeltLevels:
    """Tests for get_belt_levels function."""

    def test_get_belt_1_levels(self) -> None:
        """Test getting belt 1 levels."""
        levels = get_belt_levels(1)
        assert len(levels) == 8
        for level in levels:
            assert 0 <= level.level_id < 8
            assert level.belt == 1

    def test_get_belt_3_levels(self) -> None:
        """Test getting belt 3 (lightning) levels."""
        levels = get_belt_levels(3)
        assert len(levels) == 8
        for level in levels:
            assert 16 <= level.level_id < 24
            assert level.belt == 3
            assert level.speed == "lightning"

    def test_get_belt_4_levels(self) -> None:
        """Test getting belt 4 levels."""
        levels = get_belt_levels(4)
        assert len(levels) == 8
        for level in levels:
            assert 24 <= level.level_id < 32
            assert level.belt == 4

    def test_get_belt_5_levels(self) -> None:
        """Test getting belt 5 (4-player) levels."""
        levels = get_belt_levels(5)
        assert len(levels) == 8
        for level in levels:
            assert 32 <= level.level_id < 40
            assert level.belt == 5
            assert level.player_count == 4

    def test_get_belt_6_levels(self) -> None:
        """Test getting belt 6 (4-player lightning) levels."""
        levels = get_belt_levels(6)
        assert len(levels) == 8
        for level in levels:
            assert 40 <= level.level_id < 48
            assert level.belt == 6
            assert level.player_count == 4
            assert level.speed == "lightning"

    def test_get_belt_7_levels(self) -> None:
        """Test getting belt 7 (4-player standard) levels."""
        levels = get_belt_levels(7)
        assert len(levels) == 8
        for level in levels:
            assert 48 <= level.level_id < 56
            assert level.belt == 7
            assert level.player_count == 4
            assert level.speed == "standard"

    def test_get_nonexistent_belt_returns_empty(self) -> None:
        """Test getting a belt with no levels returns empty list."""
        levels = get_belt_levels(10)
        assert levels == []


class TestConstants:
    """Tests for module constants."""

    def test_belt_names(self) -> None:
        """Verify belt names are defined."""
        assert BELT_NAMES[1] == "White"
        assert BELT_NAMES[2] == "Yellow"
        assert BELT_NAMES[3] == "Green"
        assert BELT_NAMES[4] == "Purple"

    def test_max_belt(self) -> None:
        """Verify MAX_BELT is set correctly."""
        assert MAX_BELT == 9
