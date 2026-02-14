"""Unit tests for campaign game creation in GameService."""

from kfchess.campaign.levels import get_level
from kfchess.game.board import BoardType
from kfchess.game.state import GameStatus, Speed
from kfchess.services.game_service import GameService


class TestCreateCampaignGame:
    """Tests for GameService.create_campaign_game()."""

    def test_create_campaign_game_level_0(self) -> None:
        """Test creating a campaign game for level 0."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        game_id, player_key, player_num = service.create_campaign_game(
            level=level,
            user_id=123,
        )

        assert game_id is not None
        assert len(game_id) == 8
        assert player_key.startswith("p1_")
        assert player_num == 1

        # Verify game was stored
        state = service.get_game(game_id)
        assert state is not None
        assert state.game_id == game_id
        assert state.board.board_type == BoardType.STANDARD
        assert state.speed == Speed.STANDARD

        # Game should auto-start (all players ready)
        assert state.status == GameStatus.PLAYING

    def test_create_campaign_game_lightning_speed(self) -> None:
        """Test creating a campaign game with lightning speed (belt 3)."""
        service = GameService()
        level = get_level(16)  # Belt 3 (Green) - lightning speed
        assert level is not None
        assert level.speed == "lightning"

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=456,
        )

        state = service.get_game(game_id)
        assert state is not None
        assert state.speed == Speed.LIGHTNING

    def test_create_campaign_game_stores_level_id(self) -> None:
        """Test that campaign level ID is stored in managed game."""
        service = GameService()
        level = get_level(5)
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=789,
        )

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert managed.campaign_level_id == 5

    def test_create_campaign_game_stores_user_id(self) -> None:
        """Test that campaign user ID is stored in managed game."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=999,
        )

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert managed.campaign_user_id == 999

    def test_create_campaign_game_creates_ai_opponent(self) -> None:
        """Test that an AI opponent is created for the campaign game."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=123,
        )

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert len(managed.ai_players) == 1
        assert 2 in managed.ai_players  # AI is player 2

    def test_create_campaign_game_player_1_is_user(self) -> None:
        """Test that player 1 is set to the user ID."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=123,
        )

        state = service.get_game(game_id)
        assert state is not None
        assert state.players[1] == "u:123"

    def test_create_campaign_game_player_2_is_campaign_bot(self) -> None:
        """Test that player 2 is set to campaign bot."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=123,
        )

        state = service.get_game(game_id)
        assert state is not None
        assert state.players[2] == "bot:campaign"

    def test_create_campaign_game_unique_ids(self) -> None:
        """Test that campaign game IDs are unique."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        ids = set()
        for i in range(10):
            game_id, _, _ = service.create_campaign_game(
                level=level,
                user_id=i,
            )
            ids.add(game_id)

        assert len(ids) == 10

    def test_create_campaign_game_custom_board(self) -> None:
        """Test that campaign game uses the custom board from level definition."""
        service = GameService()
        level = get_level(0)  # Level 0 has a specific board setup
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=123,
        )

        state = service.get_game(game_id)
        assert state is not None

        # Level 0 has player 2 king at (0, 4) and player 1 has full setup
        # The board should match the level definition, not standard setup
        player_1_pieces = [p for p in state.board.pieces if p.player == 1]
        player_2_pieces = [p for p in state.board.pieces if p.player == 2]

        # Player 2 should only have 1 piece (king) in level 0
        assert len(player_2_pieces) == 1
        assert player_2_pieces[0].type.value == "K"

        # Player 1 should have standard pieces
        assert len(player_1_pieces) == 16


    def test_create_campaign_game_sets_is_campaign(self) -> None:
        """Test that campaign games have is_campaign=True on the state."""
        service = GameService()
        level = get_level(0)
        assert level is not None

        game_id, _, _ = service.create_campaign_game(
            level=level,
            user_id=123,
        )

        state = service.get_game(game_id)
        assert state is not None
        assert state.is_campaign is True


class TestManagedGameCampaignFields:
    """Tests for ManagedGame campaign-related fields."""

    def test_regular_game_has_no_campaign_fields(self) -> None:
        """Test that regular games have None for campaign fields."""
        service = GameService()
        game_id, _, _ = service.create_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            opponent="bot:novice",
        )

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert managed.campaign_level_id is None
        assert managed.campaign_user_id is None
        assert managed.state.is_campaign is False

    def test_lobby_game_has_no_campaign_fields(self) -> None:
        """Test that lobby games have None for campaign fields."""
        service = GameService()
        game_id = service.create_lobby_game(
            speed=Speed.STANDARD,
            board_type=BoardType.STANDARD,
            player_keys={1: "key1", 2: "key2"},
        )

        managed = service.get_managed_game(game_id)
        assert managed is not None
        assert managed.campaign_level_id is None
        assert managed.campaign_user_id is None
