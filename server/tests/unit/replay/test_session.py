"""Tests for the ReplaySession class."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from kfchess.game.board import BoardType
from kfchess.game.replay import Replay
from kfchess.game.state import ReplayMove, Speed
from kfchess.replay.session import ReplaySession


@pytest.fixture
def sample_replay() -> Replay:
    """Create a sample replay for testing."""
    return Replay(
        version=2,
        speed=Speed.STANDARD,
        board_type=BoardType.STANDARD,
        players={1: "player1", 2: "player2"},
        moves=[
            ReplayMove(tick=5, piece_id="P:1:6:4", to_row=4, to_col=4, player=1),
            ReplayMove(tick=10, piece_id="P:2:1:4", to_row=3, to_col=4, player=2),
        ],
        total_ticks=100,
        winner=1,
        win_reason="king_captured",
        created_at=datetime(2025, 1, 21, 12, 0, 0),
    )


@pytest.fixture
def mock_websocket() -> AsyncMock:
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestReplaySessionInit:
    """Tests for ReplaySession initialization."""

    def test_init(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test session initializes with correct state."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")

        assert session.replay == sample_replay
        assert session.websocket == mock_websocket
        assert session.game_id == "TESTGAME"
        assert session.current_tick == 0
        assert session.is_playing is False
        assert session._playback_task is None
        assert session._closed is False
        assert session._lock is not None  # Lock should be initialized


class TestReplaySessionStart:
    """Tests for ReplaySession.start()."""

    @pytest.mark.asyncio
    async def test_start_sends_replay_info(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that start() sends replay_info message."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        # Check that replay_info was sent
        calls = mock_websocket.send_json.call_args_list
        assert len(calls) >= 1

        replay_info = calls[0][0][0]
        assert replay_info["type"] == "replay_info"
        assert replay_info["game_id"] == "TESTGAME"
        assert replay_info["speed"] == "standard"
        assert replay_info["board_type"] == "standard"
        assert replay_info["players"] == {"1": "player1", "2": "player2"}
        assert replay_info["total_ticks"] == 100
        assert replay_info["winner"] == 1
        assert replay_info["win_reason"] == "king_captured"

    @pytest.mark.asyncio
    async def test_start_sends_initial_state(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that start() sends initial state at tick 0."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        # Check that state was sent
        calls = mock_websocket.send_json.call_args_list
        assert len(calls) >= 2

        state_msg = calls[1][0][0]
        assert state_msg["type"] == "state"  # Uses "state" to match live game protocol
        assert state_msg["tick"] == 0
        assert "pieces" in state_msg
        assert "active_moves" in state_msg
        assert "cooldowns" in state_msg
        assert "events" in state_msg  # Empty events array for consistency

        # Should have 32 pieces for a standard board
        assert len(state_msg["pieces"]) == 32


class TestReplaySessionPlayback:
    """Tests for play/pause/seek functionality."""

    @pytest.mark.asyncio
    async def test_play_starts_playback(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that play() starts playback."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        mock_websocket.send_json.reset_mock()

        await session.play()

        assert session.is_playing is True
        assert session._playback_task is not None

        # Clean up
        await session.close()

    @pytest.mark.asyncio
    async def test_play_sends_playback_status(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that play() sends playback_status message."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        mock_websocket.send_json.reset_mock()

        await session.play()

        # Check that playback_status was sent
        calls = mock_websocket.send_json.call_args_list
        assert len(calls) >= 1

        playback_status = calls[0][0][0]
        assert playback_status["type"] == "playback_status"
        assert playback_status["is_playing"] is True
        assert playback_status["current_tick"] == 0
        assert playback_status["total_ticks"] == 100

        await session.close()

    @pytest.mark.asyncio
    async def test_play_noop_when_already_playing(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that play() is a no-op when already playing."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        await session.play()
        first_task = session._playback_task
        mock_websocket.send_json.reset_mock()

        await session.play()

        # Task should be the same (not recreated)
        assert session._playback_task is first_task
        # No new messages should be sent
        assert mock_websocket.send_json.call_count == 0

        await session.close()

    @pytest.mark.asyncio
    async def test_play_noop_at_end(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that play() does nothing when at the end."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        session.current_tick = sample_replay.total_ticks
        await session.start()
        mock_websocket.send_json.reset_mock()

        await session.play()

        assert session.is_playing is False
        assert session._playback_task is None

        await session.close()

    @pytest.mark.asyncio
    async def test_pause_stops_playback(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that pause() stops playback."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.play()

        await session.pause()

        assert session.is_playing is False
        assert session._playback_task is None

        await session.close()

    @pytest.mark.asyncio
    async def test_pause_sends_playback_status(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that pause() sends playback_status message."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.play()
        mock_websocket.send_json.reset_mock()

        await session.pause()

        # Check that playback_status was sent
        calls = mock_websocket.send_json.call_args_list
        assert len(calls) >= 1

        playback_status = calls[0][0][0]
        assert playback_status["type"] == "playback_status"
        assert playback_status["is_playing"] is False

        await session.close()

    @pytest.mark.asyncio
    async def test_seek_changes_tick(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that seek() changes the current tick."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        mock_websocket.send_json.reset_mock()

        await session.seek(50)

        assert session.current_tick == 50

        await session.close()

    @pytest.mark.asyncio
    async def test_seek_sends_state_and_status(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that seek() sends state and playback_status."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        mock_websocket.send_json.reset_mock()

        await session.seek(50)

        calls = mock_websocket.send_json.call_args_list
        assert len(calls) >= 2

        # First call should be state
        state_msg = calls[0][0][0]
        assert state_msg["type"] == "state"
        assert state_msg["tick"] == 50

        # Second call should be playback_status
        playback_status = calls[1][0][0]
        assert playback_status["type"] == "playback_status"
        assert playback_status["current_tick"] == 50

        await session.close()

    @pytest.mark.asyncio
    async def test_seek_clamps_to_valid_range(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that seek() clamps tick to valid range."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        # Seek past end
        await session.seek(200)
        assert session.current_tick == 100

        # Seek before start
        await session.seek(-10)
        assert session.current_tick == 0

        await session.close()

    @pytest.mark.asyncio
    async def test_seek_resumes_playback_if_was_playing(
        self, sample_replay: Replay, mock_websocket: AsyncMock
    ):
        """Test that seek() resumes playback if it was playing."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.play()

        await session.seek(50)

        assert session.is_playing is True
        assert session.current_tick == 50

        await session.close()

    @pytest.mark.asyncio
    async def test_seek_doesnt_resume_if_at_end(
        self, sample_replay: Replay, mock_websocket: AsyncMock
    ):
        """Test that seek() doesn't resume if seeking to end."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.play()

        await session.seek(100)

        assert session.is_playing is False

        await session.close()


class TestReplaySessionHandleMessage:
    """Tests for handle_message()."""

    @pytest.mark.asyncio
    async def test_handle_play_message(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test handling play message."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        await session.handle_message({"type": "play"})

        assert session.is_playing is True

        await session.close()

    @pytest.mark.asyncio
    async def test_handle_pause_message(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test handling pause message."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.play()

        await session.handle_message({"type": "pause"})

        assert session.is_playing is False

        await session.close()

    @pytest.mark.asyncio
    async def test_handle_seek_message(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test handling seek message."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        await session.handle_message({"type": "seek", "tick": 75})

        assert session.current_tick == 75

        await session.close()

    @pytest.mark.asyncio
    async def test_handle_unknown_message(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test handling unknown message type."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        # Should not raise
        await session.handle_message({"type": "unknown"})

        await session.close()


class TestReplaySessionClose:
    """Tests for session cleanup."""

    @pytest.mark.asyncio
    async def test_close_stops_playback(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that close() stops playback."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.play()

        await session.close()

        assert session._closed is True
        assert session.is_playing is False
        assert session._playback_task is None

    @pytest.mark.asyncio
    async def test_close_prevents_further_messages(
        self, sample_replay: Replay, mock_websocket: AsyncMock
    ):
        """Test that close() prevents further WebSocket messages."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()
        await session.close()
        mock_websocket.send_json.reset_mock()

        # These should be no-ops
        await session.play()
        await session.pause()
        await session.seek(50)

        assert mock_websocket.send_json.call_count == 0


class TestReplaySessionPlaybackLoop:
    """Tests for the playback loop behavior."""

    @pytest.mark.asyncio
    async def test_playback_advances_tick(self, mock_websocket: AsyncMock):
        """Test that playback advances the tick."""
        # Create a very short replay
        replay = Replay(
            version=2,
            speed=Speed.LIGHTNING,  # Faster ticks
            board_type=BoardType.STANDARD,
            players={1: "p1", 2: "p2"},
            moves=[],
            total_ticks=5,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        session = ReplaySession(replay, mock_websocket, "TESTGAME")
        await session.start()
        mock_websocket.send_json.reset_mock()

        # Start playback
        await session.play()

        # Wait for a few ticks
        await asyncio.sleep(0.3)  # Lightning tick is 100ms

        # Should have advanced
        assert session.current_tick > 0

        await session.close()

    @pytest.mark.asyncio
    async def test_playback_sends_game_over_at_end(self, mock_websocket: AsyncMock):
        """Test that playback sends game_over when reaching the end."""
        # Create a very short replay
        replay = Replay(
            version=2,
            speed=Speed.LIGHTNING,
            board_type=BoardType.STANDARD,
            players={1: "p1", 2: "p2"},
            moves=[],
            total_ticks=3,
            winner=1,
            win_reason="king_captured",
            created_at=None,
        )

        session = ReplaySession(replay, mock_websocket, "TESTGAME")
        await session.start()

        # Start playback and wait for it to finish
        await session.play()
        await asyncio.sleep(0.5)  # Wait for 3 ticks (300ms) + buffer

        # Should have reached the end
        assert session.current_tick == 3
        assert session.is_playing is False

        # Check that game_over was sent
        game_over_calls = [
            call[0][0] for call in mock_websocket.send_json.call_args_list
            if call[0][0].get("type") == "game_over"
        ]
        assert len(game_over_calls) == 1
        assert game_over_calls[0]["winner"] == 1
        assert game_over_calls[0]["reason"] == "king_captured"

        await session.close()

    @pytest.mark.asyncio
    async def test_playback_handles_send_failure(self, mock_websocket: AsyncMock):
        """Test that playback loop handles WebSocket send failures gracefully."""
        replay = Replay(
            version=2,
            speed=Speed.LIGHTNING,
            board_type=BoardType.STANDARD,
            players={1: "p1", 2: "p2"},
            moves=[],
            total_ticks=10,
            winner=None,
            win_reason=None,
            created_at=None,
        )

        session = ReplaySession(replay, mock_websocket, "TESTGAME")
        await session.start()

        # Make send_json fail after a few calls
        call_count = [0]
        original_send = mock_websocket.send_json

        async def failing_send(msg):
            call_count[0] += 1
            if call_count[0] > 2:  # Fail earlier to ensure we catch it
                raise RuntimeError("WebSocket disconnected")
            return await original_send(msg)

        mock_websocket.send_json = failing_send

        # Start playback
        await session.play()

        # Wait for failure with extra buffer time
        await asyncio.sleep(0.5)

        # Session should be closed due to send failure
        assert session._closed is True
        assert session.is_playing is False


class TestReplaySessionStateFormat:
    """Tests for state message formatting."""

    @pytest.mark.asyncio
    async def test_state_format(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that state messages have correct format."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        # Get the state message
        calls = mock_websocket.send_json.call_args_list
        state_msg = calls[1][0][0]

        # Verify structure matches live game protocol
        assert state_msg["type"] == "state"
        assert "tick" in state_msg
        assert "pieces" in state_msg
        assert "active_moves" in state_msg
        assert "cooldowns" in state_msg
        assert "events" in state_msg  # Empty array for consistency

        # Verify piece format
        assert len(state_msg["pieces"]) > 0
        piece = state_msg["pieces"][0]
        assert "id" in piece
        assert "type" in piece
        assert "player" in piece
        assert "row" in piece
        assert "col" in piece
        assert "captured" in piece
        assert "moving" in piece
        assert "on_cooldown" in piece
        assert "moved" in piece

        await session.close()


class TestReplaySessionConcurrency:
    """Tests for thread safety with asyncio.Lock."""

    @pytest.mark.asyncio
    async def test_rapid_play_pause_seek(self, sample_replay: Replay, mock_websocket: AsyncMock):
        """Test that rapid play/pause/seek doesn't cause race conditions."""
        session = ReplaySession(sample_replay, mock_websocket, "TESTGAME")
        await session.start()

        # Rapidly alternate between play, pause, and seek
        for i in range(10):
            await session.play()
            await session.seek(i * 10)
            await session.pause()
            await session.play()

        # Should be in a consistent state
        assert session.is_playing is True
        await session.close()
        assert session._closed is True
        assert session.is_playing is False
