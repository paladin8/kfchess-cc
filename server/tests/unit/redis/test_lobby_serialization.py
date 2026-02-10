"""Tests for lobby model Redis serialization round-trips."""

from __future__ import annotations

from datetime import datetime, timedelta

from kfchess.lobby.models import Lobby, LobbyPlayer, LobbySettings, LobbyStatus


class TestLobbyPlayerSerialization:
    """Round-trip tests for LobbyPlayer Redis serialization."""

    def test_basic_human_player(self) -> None:
        player = LobbyPlayer(slot=1, user_id=42, username="Alice", player_id="u:42")
        data = player.to_redis_dict()
        restored = LobbyPlayer.from_redis_dict(data)

        assert restored.slot == 1
        assert restored.user_id == 42
        assert restored.username == "Alice"
        assert restored.player_id == "u:42"
        assert restored.is_ai is False
        assert restored.is_connected is True
        assert restored._is_ready is False

    def test_ai_player(self) -> None:
        player = LobbyPlayer(
            slot=2, user_id=None, username="AI (novice)",
            is_ai=True, ai_type="bot:novice",
        )
        data = player.to_redis_dict()
        restored = LobbyPlayer.from_redis_dict(data)

        assert restored.is_ai is True
        assert restored.ai_type == "bot:novice"
        assert restored.is_ready is True  # AI always ready

    def test_ready_player(self) -> None:
        player = LobbyPlayer(slot=1, user_id=1, username="Bob")
        player.is_ready = True
        data = player.to_redis_dict()
        restored = LobbyPlayer.from_redis_dict(data)

        assert restored._is_ready is True
        assert restored.is_ready is True

    def test_disconnected_player(self) -> None:
        now = datetime.utcnow()
        player = LobbyPlayer(
            slot=1, user_id=1, username="Carol",
            is_connected=False, disconnected_at=now,
        )
        data = player.to_redis_dict()
        restored = LobbyPlayer.from_redis_dict(data)

        assert restored.is_connected is False
        assert restored.disconnected_at is not None
        assert abs((restored.disconnected_at - now).total_seconds()) < 1

    def test_guest_player(self) -> None:
        player = LobbyPlayer(
            slot=1, user_id=None, username="Guest",
            player_id="guest:abc123",
        )
        data = player.to_redis_dict()
        restored = LobbyPlayer.from_redis_dict(data)

        assert restored.user_id is None
        assert restored.player_id == "guest:abc123"

    def test_picture_url(self) -> None:
        player = LobbyPlayer(
            slot=1, user_id=1, username="Dave",
            picture_url="https://example.com/pic.jpg",
        )
        data = player.to_redis_dict()
        restored = LobbyPlayer.from_redis_dict(data)

        assert restored.picture_url == "https://example.com/pic.jpg"


class TestLobbySettingsSerialization:
    """Round-trip tests for LobbySettings Redis serialization."""

    def test_default_settings(self) -> None:
        settings = LobbySettings()
        data = settings.to_redis_dict()
        restored = LobbySettings.from_redis_dict(data)

        assert restored.is_public is True
        assert restored.speed == "standard"
        assert restored.player_count == 2
        assert restored.is_ranked is False

    def test_custom_settings(self) -> None:
        settings = LobbySettings(
            is_public=False, speed="lightning",
            player_count=4, is_ranked=True,
        )
        data = settings.to_redis_dict()
        restored = LobbySettings.from_redis_dict(data)

        assert restored.is_public is False
        assert restored.speed == "lightning"
        assert restored.player_count == 4
        assert restored.is_ranked is True


class TestLobbySerialization:
    """Round-trip tests for Lobby Redis serialization."""

    def test_basic_lobby(self) -> None:
        lobby = Lobby(
            id=1, code="ABC123", host_slot=1,
            settings=LobbySettings(),
        )
        lobby.players[1] = LobbyPlayer(
            slot=1, user_id=42, username="Host", player_id="u:42",
        )

        data = lobby.to_redis_dict()
        restored = Lobby.from_redis_dict(data)

        assert restored.id == 1
        assert restored.code == "ABC123"
        assert restored.host_slot == 1
        assert restored.status == LobbyStatus.WAITING
        assert 1 in restored.players
        assert restored.players[1].username == "Host"

    def test_lobby_with_ai(self) -> None:
        lobby = Lobby(
            id=2, code="XYZ789", host_slot=1,
            settings=LobbySettings(),
        )
        lobby.players[1] = LobbyPlayer(slot=1, user_id=1, username="Host")
        lobby.players[2] = LobbyPlayer(
            slot=2, user_id=None, username="AI (novice)",
            is_ai=True, ai_type="bot:novice",
        )

        data = lobby.to_redis_dict()
        restored = Lobby.from_redis_dict(data)

        assert len(restored.players) == 2
        assert restored.players[2].is_ai is True
        assert restored.players[2].ai_type == "bot:novice"

    def test_lobby_in_game(self) -> None:
        lobby = Lobby(
            id=3, code="GAME01", host_slot=1,
            settings=LobbySettings(),
            status=LobbyStatus.IN_GAME,
            current_game_id="GAME-ABC",
            games_played=2,
        )
        lobby.players[1] = LobbyPlayer(slot=1, user_id=1, username="P1")

        data = lobby.to_redis_dict()
        restored = Lobby.from_redis_dict(data)

        assert restored.status == LobbyStatus.IN_GAME
        assert restored.current_game_id == "GAME-ABC"
        assert restored.games_played == 2

    def test_lobby_finished(self) -> None:
        now = datetime.utcnow()
        lobby = Lobby(
            id=4, code="FIN001", host_slot=1,
            settings=LobbySettings(),
            status=LobbyStatus.FINISHED,
            game_finished_at=now,
        )
        lobby.players[1] = LobbyPlayer(slot=1, user_id=1, username="P1")

        data = lobby.to_redis_dict()
        restored = Lobby.from_redis_dict(data)

        assert restored.status == LobbyStatus.FINISHED
        assert restored.game_finished_at is not None
        assert abs((restored.game_finished_at - now).total_seconds()) < 1

    def test_four_player_lobby(self) -> None:
        lobby = Lobby(
            id=5, code="FOUR01", host_slot=1,
            settings=LobbySettings(player_count=4),
        )
        for i in range(1, 5):
            lobby.players[i] = LobbyPlayer(
                slot=i, user_id=i, username=f"Player{i}",
            )

        data = lobby.to_redis_dict()
        restored = Lobby.from_redis_dict(data)

        assert len(restored.players) == 4
        assert restored.settings.player_count == 4
        for i in range(1, 5):
            assert restored.players[i].username == f"Player{i}"

    def test_player_dict_keys_are_strings_in_json(self) -> None:
        """Player dict keys must be strings for JSON compatibility."""
        lobby = Lobby(
            id=1, code="ABC123", host_slot=1,
            settings=LobbySettings(),
        )
        lobby.players[1] = LobbyPlayer(slot=1, user_id=1, username="P1")

        data = lobby.to_redis_dict()
        # Keys should be strings
        assert "1" in data["players"]
        assert 1 not in data["players"]

    def test_disconnected_player_in_lobby(self) -> None:
        now = datetime.utcnow()
        lobby = Lobby(
            id=6, code="DISC01", host_slot=1,
            settings=LobbySettings(),
        )
        lobby.players[1] = LobbyPlayer(
            slot=1, user_id=1, username="P1",
            is_connected=False,
            disconnected_at=now - timedelta(seconds=15),
        )

        data = lobby.to_redis_dict()
        restored = Lobby.from_redis_dict(data)

        p1 = restored.players[1]
        assert p1.is_connected is False
        assert p1.disconnected_at is not None
        assert p1.is_ready is False  # Disconnected players are not ready
