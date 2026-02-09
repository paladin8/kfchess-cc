"""Tests for CampaignService."""

from unittest.mock import AsyncMock

import pytest

from kfchess.campaign.service import CampaignProgressData, CampaignService


class TestCampaignProgressData:
    """Tests for CampaignProgressData class."""

    def test_is_level_unlocked_first_level(self) -> None:
        """First level is always unlocked."""
        progress = CampaignProgressData(levels_completed={}, belts_completed={})
        assert progress.is_level_unlocked(0) is True

    def test_is_level_unlocked_sequential(self) -> None:
        """Level unlocks after previous is completed."""
        progress = CampaignProgressData(
            levels_completed={"0": True, "1": True},
            belts_completed={},
        )
        assert progress.is_level_unlocked(2) is True
        assert progress.is_level_unlocked(3) is False

    def test_is_level_unlocked_first_of_belt(self) -> None:
        """First level of each belt is unlocked when belt is available."""
        progress = CampaignProgressData(
            levels_completed={},
            belts_completed={"1": True},
        )
        # Level 8 is first of belt 2
        assert progress.is_level_unlocked(8) is True
        # Level 9 is not unlocked yet (need to complete 8 first)
        assert progress.is_level_unlocked(9) is False

    def test_is_level_unlocked_locked_belt(self) -> None:
        """Levels in locked belts are not accessible."""
        progress = CampaignProgressData(
            levels_completed={},
            belts_completed={},
        )
        # Belt 2 not unlocked, so level 8 is locked
        assert progress.is_level_unlocked(8) is False

    def test_is_level_completed(self) -> None:
        """Check level completion status."""
        progress = CampaignProgressData(
            levels_completed={"0": True, "5": True},
            belts_completed={},
        )
        assert progress.is_level_completed(0) is True
        assert progress.is_level_completed(5) is True
        assert progress.is_level_completed(1) is False

    def test_current_belt_no_progress(self) -> None:
        """Current belt is 1 with no progress."""
        progress = CampaignProgressData(
            levels_completed={},
            belts_completed={},
        )
        assert progress.current_belt == 1

    def test_current_belt_one_completed(self) -> None:
        """Current belt is 2 after belt 1 completed."""
        progress = CampaignProgressData(
            levels_completed={},
            belts_completed={"1": True},
        )
        assert progress.current_belt == 2

    def test_current_belt_capped_at_max(self) -> None:
        """Current belt is capped at MAX_BELT."""
        progress = CampaignProgressData(
            levels_completed={},
            belts_completed={
                "1": True, "2": True, "3": True,
                "4": True, "5": True, "6": True,
                "7": True, "8": True,
            },
        )
        # MAX_BELT is 9, so current_belt should be 9 (not 10)
        assert progress.current_belt == 9


class TestCampaignService:
    """Tests for CampaignService."""

    @pytest.mark.asyncio
    async def test_get_progress_empty(self) -> None:
        """Test getting progress with no data."""
        mock_repo = AsyncMock()
        mock_repo.get_progress.return_value = {}

        service = CampaignService(mock_repo)
        progress = await service.get_progress(123)

        assert progress.levels_completed == {}
        assert progress.belts_completed == {}
        mock_repo.get_progress.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_get_progress_with_data(self) -> None:
        """Test getting progress from repository."""
        mock_repo = AsyncMock()
        mock_repo.get_progress.return_value = {
            "levelsCompleted": {"0": True, "1": True},
            "beltsCompleted": {},
        }

        service = CampaignService(mock_repo)
        progress = await service.get_progress(123)

        assert progress.levels_completed == {"0": True, "1": True}
        assert progress.belts_completed == {}

    @pytest.mark.asyncio
    async def test_complete_level_simple(self) -> None:
        """Test completing a single level."""
        mock_repo = AsyncMock()
        mock_repo.get_progress.return_value = {
            "levelsCompleted": {"0": True},
            "beltsCompleted": {},
        }

        service = CampaignService(mock_repo)
        new_belt = await service.complete_level(123, 1)

        assert new_belt is False
        mock_repo.update_progress.assert_called_once()
        call_args = mock_repo.update_progress.call_args
        assert call_args[0][0] == 123
        assert "1" in call_args[0][1]["levelsCompleted"]

    @pytest.mark.asyncio
    async def test_complete_level_completes_belt(self) -> None:
        """Test completing a level that finishes a belt."""
        mock_repo = AsyncMock()
        # All levels 0-6 completed, completing 7 will finish belt 1
        mock_repo.get_progress.return_value = {
            "levelsCompleted": {
                "0": True,
                "1": True,
                "2": True,
                "3": True,
                "4": True,
                "5": True,
                "6": True,
            },
            "beltsCompleted": {},
        }

        service = CampaignService(mock_repo)
        new_belt = await service.complete_level(123, 7)

        assert new_belt is True
        call_args = mock_repo.update_progress.call_args
        progress = call_args[0][1]
        assert "7" in progress["levelsCompleted"]
        assert "1" in progress["beltsCompleted"]

    @pytest.mark.asyncio
    async def test_complete_level_already_completed_belt(self) -> None:
        """Test completing level when belt already marked complete."""
        mock_repo = AsyncMock()
        mock_repo.get_progress.return_value = {
            "levelsCompleted": {str(i): True for i in range(8)},
            "beltsCompleted": {"1": True},
        }

        service = CampaignService(mock_repo)
        # Re-completing level 0 shouldn't mark belt as "newly completed"
        new_belt = await service.complete_level(123, 0)

        assert new_belt is False
