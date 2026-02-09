"""Unit tests for campaign API models and endpoints."""

from kfchess.api.campaign import (
    CampaignProgressResponse,
    LevelResponse,
    LevelsListResponse,
    StartGameResponse,
)
from kfchess.campaign.levels import BELT_NAMES, LEVELS, MAX_BELT, get_level


class TestCampaignProgressResponse:
    """Tests for CampaignProgressResponse model."""

    def test_fields(self) -> None:
        """Test all fields are present."""
        response = CampaignProgressResponse(
            levels_completed={"0": True, "1": True},
            belts_completed={"1": True},
            current_belt=2,
            max_belt=4,
        )

        assert response.levels_completed == {"0": True, "1": True}
        assert response.belts_completed == {"1": True}
        assert response.current_belt == 2
        assert response.max_belt == 4

    def test_alias_serialization(self) -> None:
        """Test camelCase aliases work for JSON serialization."""
        response = CampaignProgressResponse(
            levels_completed={"0": True},
            belts_completed={},
            current_belt=1,
            max_belt=4,
        )

        data = response.model_dump(by_alias=True)
        assert "levelsCompleted" in data
        assert "beltsCompleted" in data
        assert "currentBelt" in data
        assert "maxBelt" in data

    def test_empty_progress(self) -> None:
        """Test empty progress response."""
        response = CampaignProgressResponse(
            levels_completed={},
            belts_completed={},
            current_belt=1,
            max_belt=4,
        )

        assert response.levels_completed == {}
        assert response.belts_completed == {}
        assert response.current_belt == 1


class TestLevelResponse:
    """Tests for LevelResponse model."""

    def test_fields(self) -> None:
        """Test all fields are present."""
        response = LevelResponse(
            level_id=0,
            belt=1,
            belt_name="White",
            title="Welcome to Kung Fu Chess",
            description="Test description",
            speed="standard",
            player_count=2,
            is_unlocked=True,
            is_completed=False,
        )

        assert response.level_id == 0
        assert response.belt == 1
        assert response.belt_name == "White"
        assert response.speed == "standard"
        assert response.player_count == 2
        assert response.is_unlocked is True
        assert response.is_completed is False

    def test_alias_serialization(self) -> None:
        """Test camelCase aliases work for JSON serialization."""
        response = LevelResponse(
            level_id=0,
            belt=1,
            belt_name="White",
            title="Test",
            description="Test",
            speed="standard",
            player_count=2,
            is_unlocked=True,
            is_completed=False,
        )

        data = response.model_dump(by_alias=True)
        assert "levelId" in data
        assert "beltName" in data
        assert "playerCount" in data
        assert "isUnlocked" in data
        assert "isCompleted" in data


class TestLevelsListResponse:
    """Tests for LevelsListResponse model."""

    def test_empty_list(self) -> None:
        """Test empty levels list."""
        response = LevelsListResponse(levels=[])
        assert response.levels == []

    def test_with_levels(self) -> None:
        """Test with multiple levels."""
        levels = [
            LevelResponse(
                level_id=i,
                belt=1,
                belt_name="White",
                title=f"Level {i}",
                description="Test",
                speed="standard",
                player_count=2,
                is_unlocked=True,
                is_completed=False,
            )
            for i in range(3)
        ]
        response = LevelsListResponse(levels=levels)
        assert len(response.levels) == 3


class TestStartGameResponse:
    """Tests for StartGameResponse model."""

    def test_fields(self) -> None:
        """Test all fields are present."""
        response = StartGameResponse(
            game_id="ABCD1234",
            player_key="p1_secret_key",
            player_number=1,
        )

        assert response.game_id == "ABCD1234"
        assert response.player_key == "p1_secret_key"
        assert response.player_number == 1

    def test_alias_serialization(self) -> None:
        """Test camelCase aliases work for JSON serialization."""
        response = StartGameResponse(
            game_id="ABCD1234",
            player_key="p1_secret_key",
            player_number=1,
        )

        data = response.model_dump(by_alias=True)
        assert "gameId" in data
        assert "playerKey" in data
        assert "playerNumber" in data


class TestLevelDefinitions:
    """Tests for level definitions used by API."""

    def test_all_72_levels_defined(self) -> None:
        """Test that all 72 levels are defined."""
        assert len(LEVELS) == 72

    def test_get_level_returns_correct_level(self) -> None:
        """Test get_level returns the correct level."""
        for i in range(32):
            level = get_level(i)
            assert level is not None
            assert level.level_id == i

    def test_get_level_returns_none_for_invalid(self) -> None:
        """Test get_level returns None for invalid level IDs."""
        assert get_level(-1) is None
        assert get_level(72) is None
        assert get_level(100) is None

    def test_max_belt_is_9(self) -> None:
        """Test MAX_BELT is 9 (currently implemented belts)."""
        assert MAX_BELT == 9

    def test_belt_names_defined(self) -> None:
        """Test belt names are defined for all implemented belts."""
        assert BELT_NAMES[1] == "White"
        assert BELT_NAMES[2] == "Yellow"
        assert BELT_NAMES[3] == "Green"
        assert BELT_NAMES[4] == "Purple"

    def test_levels_have_correct_belts(self) -> None:
        """Test levels 0-7 are belt 1, 8-15 are belt 2, etc."""
        for i, level in enumerate(LEVELS):
            expected_belt = i // 8 + 1
            assert level.belt == expected_belt, f"Level {i} has belt {level.belt}, expected {expected_belt}"

    def test_belt_3_is_lightning_speed(self) -> None:
        """Test belt 3 (levels 16-23) uses lightning speed."""
        for i in range(16, 24):
            level = get_level(i)
            assert level is not None
            assert level.speed == "lightning", f"Level {i} should be lightning speed"

    def test_belt_1_to_4_levels_are_2_player(self) -> None:
        """Test belts 1-4 levels are 2-player."""
        for level in LEVELS[:32]:
            assert level.player_count == 2

    def test_belt_5_levels_are_4_player(self) -> None:
        """Test belt 5 levels are 4-player."""
        for level in LEVELS[32:40]:
            assert level.player_count == 4

    def test_belt_6_levels_are_4_player_lightning(self) -> None:
        """Test belt 6 levels are 4-player lightning."""
        for level in LEVELS[40:48]:
            assert level.player_count == 4
            assert level.speed == "lightning"
