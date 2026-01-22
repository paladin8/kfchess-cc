"""Tests for the ReplayRepository."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kfchess.db.models import GameReplay
from kfchess.db.repositories.replays import ReplayRepository
from kfchess.game.board import BoardType
from kfchess.game.replay import Replay
from kfchess.game.state import ReplayMove, Speed


class TestReplayRepositoryRecordConversion:
    """Tests for _record_to_replay conversion."""

    def test_valid_record_conversion(self):
        """Test converting a valid database record to Replay."""
        record = MagicMock(spec=GameReplay)
        record.id = "TESTGAME"
        record.speed = "standard"
        record.board_type = "standard"
        record.players = {"1": "player1", "2": "player2"}
        record.moves = [
            {"tick": 5, "piece_id": "P:1:6:4", "to_row": 4, "to_col": 4, "player": 1},
            {"tick": 10, "piece_id": "P:2:1:4", "to_row": 3, "to_col": 4, "player": 2},
        ]
        record.total_ticks = 100
        record.winner = 1
        record.win_reason = "king_captured"
        record.created_at = datetime(2025, 1, 21, 12, 0, 0)

        session = MagicMock()
        repository = ReplayRepository(session)
        replay = repository._record_to_replay(record)

        assert replay.version == 2
        assert replay.speed == Speed.STANDARD
        assert replay.board_type == BoardType.STANDARD
        assert replay.players == {1: "player1", 2: "player2"}
        assert len(replay.moves) == 2
        assert replay.moves[0].tick == 5
        assert replay.moves[0].piece_id == "P:1:6:4"
        assert replay.total_ticks == 100
        assert replay.winner == 1

    def test_invalid_players_data(self):
        """Test that invalid players data raises ValueError."""
        record = MagicMock(spec=GameReplay)
        record.id = "BADGAME"
        record.players = {"not_a_number": "player1"}  # Invalid key

        session = MagicMock()
        repository = ReplayRepository(session)

        with pytest.raises(ValueError, match="Corrupt players data"):
            repository._record_to_replay(record)

    def test_invalid_move_data_missing_field(self):
        """Test that moves with missing fields raise ValueError."""
        record = MagicMock(spec=GameReplay)
        record.id = "BADGAME"
        record.speed = "standard"
        record.board_type = "standard"
        record.players = {"1": "player1", "2": "player2"}
        record.moves = [
            {"tick": 5, "piece_id": "P:1:6:4"},  # Missing to_row, to_col, player
        ]

        session = MagicMock()
        repository = ReplayRepository(session)

        with pytest.raises(ValueError, match="Corrupt move data at index 0"):
            repository._record_to_replay(record)

    def test_invalid_speed_value(self):
        """Test that invalid speed raises ValueError."""
        record = MagicMock(spec=GameReplay)
        record.id = "BADGAME"
        record.speed = "invalid_speed"
        record.board_type = "standard"
        record.players = {"1": "player1", "2": "player2"}
        record.moves = []
        record.total_ticks = 0
        record.winner = None
        record.win_reason = None
        record.created_at = None

        session = MagicMock()
        repository = ReplayRepository(session)

        with pytest.raises(ValueError, match="Invalid speed or board_type"):
            repository._record_to_replay(record)

    def test_invalid_board_type_value(self):
        """Test that invalid board_type raises ValueError."""
        record = MagicMock(spec=GameReplay)
        record.id = "BADGAME"
        record.speed = "standard"
        record.board_type = "invalid_board"
        record.players = {"1": "player1", "2": "player2"}
        record.moves = []
        record.total_ticks = 0
        record.winner = None
        record.win_reason = None
        record.created_at = None

        session = MagicMock()
        repository = ReplayRepository(session)

        with pytest.raises(ValueError, match="Invalid speed or board_type"):
            repository._record_to_replay(record)


class TestReplayRepositorySave:
    """Tests for save operations."""

    @pytest.mark.asyncio
    async def test_save_creates_record(self):
        """Test that save creates a database record."""
        # Mock get_by_id to return None (no existing record)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = mock_result
        # session.add is not async, so use MagicMock
        session.add = MagicMock()

        repository = ReplayRepository(session)

        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "player1", 2: "player2"},
            moves=[
                ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
            ],
            total_ticks=100,
            winner=1,
            win_reason="king_captured",
            created_at=datetime(2025, 1, 21, 12, 0, 0),
        )

        result = await repository.save("TESTGAME", replay)

        # Verify session.add was called with a GameReplay
        session.add.assert_called_once()
        added_record = session.add.call_args[0][0]
        assert isinstance(added_record, GameReplay)
        assert added_record.id == "TESTGAME"
        assert added_record.speed == "standard"
        assert added_record.board_type == "standard"
        assert added_record.players == {"1": "player1", "2": "player2"}
        assert len(added_record.moves) == 1
        assert added_record.total_ticks == 100

        # Verify flush was called
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_idempotent_skips_existing(self):
        """Test that save is idempotent - skips if replay already exists."""
        # Create mock existing record
        existing_record = MagicMock(spec=GameReplay)
        existing_record.id = "TESTGAME"
        existing_record.speed = "standard"
        existing_record.board_type = "standard"
        existing_record.players = {"1": "player1", "2": "player2"}
        existing_record.moves = []
        existing_record.total_ticks = 100
        existing_record.winner = 1
        existing_record.win_reason = "king_captured"
        existing_record.created_at = datetime(2025, 1, 21, 12, 0, 0)

        # Mock get_by_id to return existing record (converted to Replay)
        # Then mock the second execute to return the GameReplay record
        mock_result_get = MagicMock()
        mock_result_get.scalar_one_or_none.return_value = existing_record

        mock_result_fetch = MagicMock()
        mock_result_fetch.scalar_one.return_value = existing_record

        session = AsyncMock()
        # First call is get_by_id, second is fetch for return
        session.execute.side_effect = [mock_result_get, mock_result_fetch]

        repository = ReplayRepository(session)

        replay = Replay(
            version=2,
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            players={1: "player1", 2: "player2"},
            moves=[],
            total_ticks=100,
            winner=1,
            win_reason="king_captured",
            created_at=datetime(2025, 1, 21, 12, 0, 0),
        )

        result = await repository.save("TESTGAME", replay)

        # Verify session.add was NOT called (skipped)
        session.add.assert_not_called()
        # Verify flush was NOT called
        session.flush.assert_not_called()
        # Verify we got back the existing record
        assert result == existing_record


class TestReplayRepositoryGet:
    """Tests for get operations."""

    @pytest.mark.asyncio
    async def test_get_by_id_found(self):
        """Test getting a replay that exists."""
        # Create a mock record
        record = MagicMock(spec=GameReplay)
        record.id = "TESTGAME"
        record.speed = "standard"
        record.board_type = "standard"
        record.players = {"1": "player1", "2": "player2"}
        record.moves = []
        record.total_ticks = 100
        record.winner = 1
        record.win_reason = "king_captured"
        record.created_at = datetime(2025, 1, 21, 12, 0, 0)

        # Mock the session execute to return our record
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record

        session = AsyncMock()
        session.execute.return_value = mock_result

        repository = ReplayRepository(session)
        replay = await repository.get_by_id("TESTGAME")

        assert replay is not None
        assert replay.speed == Speed.STANDARD
        assert replay.total_ticks == 100

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self):
        """Test getting a replay that doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = mock_result

        repository = ReplayRepository(session)
        replay = await repository.get_by_id("NONEXISTENT")

        assert replay is None

    @pytest.mark.asyncio
    async def test_exists_true(self):
        """Test exists returns True for existing replay."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "TESTGAME"

        session = AsyncMock()
        session.execute.return_value = mock_result

        repository = ReplayRepository(session)
        exists = await repository.exists("TESTGAME")

        assert exists is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        """Test exists returns False for non-existing replay."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = mock_result

        repository = ReplayRepository(session)
        exists = await repository.exists("NONEXISTENT")

        assert exists is False


class TestReplayRepositoryDelete:
    """Tests for delete operations."""

    @pytest.mark.asyncio
    async def test_delete_found(self):
        """Test deleting a replay that exists."""
        record = MagicMock(spec=GameReplay)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record

        session = AsyncMock()
        session.execute.return_value = mock_result

        repository = ReplayRepository(session)
        deleted = await repository.delete("TESTGAME")

        assert deleted is True
        session.delete.assert_called_once_with(record)
        session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """Test deleting a replay that doesn't exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.return_value = mock_result

        repository = ReplayRepository(session)
        deleted = await repository.delete("NONEXISTENT")

        assert deleted is False
        session.delete.assert_not_called()
