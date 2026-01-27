"""Unit tests for leaderboard API endpoints."""

from kfchess.api.leaderboard import (
    VALID_MODES,
    LeaderboardEntry,
    LeaderboardResponse,
    MyRankResponse,
)


class TestLeaderboardModels:
    """Tests for leaderboard data models."""

    def test_valid_modes_contains_all_combinations(self):
        """Valid modes should include all 2p/4p and standard/lightning combos."""
        assert "2p_standard" in VALID_MODES
        assert "2p_lightning" in VALID_MODES
        assert "4p_standard" in VALID_MODES
        assert "4p_lightning" in VALID_MODES
        assert len(VALID_MODES) == 4

    def test_leaderboard_entry_fields(self):
        """LeaderboardEntry should have all required fields."""
        entry = LeaderboardEntry(
            rank=1,
            user_id=123,
            username="TestUser",
            rating=1500,
            belt="orange",
            games_played=50,
            wins=30,
        )
        assert entry.rank == 1
        assert entry.user_id == 123
        assert entry.username == "TestUser"
        assert entry.rating == 1500
        assert entry.belt == "orange"
        assert entry.games_played == 50
        assert entry.wins == 30

    def test_leaderboard_response_fields(self):
        """LeaderboardResponse should have all required fields."""
        response = LeaderboardResponse(
            mode="2p_standard",
            entries=[],
            total_count=100,
        )
        assert response.mode == "2p_standard"
        assert response.entries == []
        assert response.total_count == 100

    def test_my_rank_response_fields(self):
        """MyRankResponse should have all required fields."""
        response = MyRankResponse(
            mode="2p_standard",
            rank=42,
            rating=1350,
            belt="purple",
            games_played=20,
            wins=12,
            percentile=85.5,
        )
        assert response.mode == "2p_standard"
        assert response.rank == 42
        assert response.rating == 1350
        assert response.belt == "purple"
        assert response.games_played == 20
        assert response.wins == 12
        assert response.percentile == 85.5

    def test_my_rank_response_nullable_fields(self):
        """MyRankResponse should allow null rank and percentile for new users."""
        response = MyRankResponse(
            mode="2p_standard",
            rank=None,
            rating=1200,
            belt="green",
            games_played=0,
            wins=0,
            percentile=None,
        )
        assert response.rank is None
        assert response.percentile is None


class TestLeaderboardModeValidation:
    """Tests for mode validation patterns."""

    def test_valid_2p_standard_mode(self):
        """2p_standard should be a valid mode."""
        assert "2p_standard" in VALID_MODES

    def test_valid_2p_lightning_mode(self):
        """2p_lightning should be a valid mode."""
        assert "2p_lightning" in VALID_MODES

    def test_valid_4p_standard_mode(self):
        """4p_standard should be a valid mode."""
        assert "4p_standard" in VALID_MODES

    def test_valid_4p_lightning_mode(self):
        """4p_lightning should be a valid mode."""
        assert "4p_lightning" in VALID_MODES
