"""Unit tests for WebSocket protocol messages."""

from kfchess.ws.protocol import (
    RatingChangeData,
    RatingUpdateMessage,
    ServerMessageType,
)


class TestServerMessageTypes:
    """Tests for server message type enumeration."""

    def test_rating_update_type_exists(self):
        """RATING_UPDATE should be a valid server message type."""
        assert ServerMessageType.RATING_UPDATE.value == "rating_update"

    def test_all_server_message_types(self):
        """All expected server message types should exist."""
        types = [t.value for t in ServerMessageType]
        assert "joined" in types
        assert "state" in types
        assert "game_started" in types
        assert "game_over" in types
        assert "rating_update" in types
        assert "move_rejected" in types
        assert "pong" in types
        assert "error" in types


class TestRatingChangeData:
    """Tests for RatingChangeData model."""

    def test_basic_rating_change(self):
        """RatingChangeData should capture old/new rating and belt."""
        change = RatingChangeData(
            old_rating=1200,
            new_rating=1216,
            old_belt="green",
            new_belt="green",
            belt_changed=False,
        )
        assert change.old_rating == 1200
        assert change.new_rating == 1216
        assert change.old_belt == "green"
        assert change.new_belt == "green"
        assert change.belt_changed is False

    def test_rating_change_with_belt_promotion(self):
        """RatingChangeData should track belt changes."""
        change = RatingChangeData(
            old_rating=1290,
            new_rating=1310,
            old_belt="green",
            new_belt="purple",
            belt_changed=True,
        )
        assert change.old_belt == "green"
        assert change.new_belt == "purple"
        assert change.belt_changed is True

    def test_rating_change_negative(self):
        """RatingChangeData should handle rating decreases."""
        change = RatingChangeData(
            old_rating=1500,
            new_rating=1484,
            old_belt="orange",
            new_belt="orange",
        )
        assert change.new_rating < change.old_rating


class TestRatingUpdateMessage:
    """Tests for RatingUpdateMessage model."""

    def test_message_type(self):
        """RatingUpdateMessage should have correct type."""
        msg = RatingUpdateMessage(ratings={})
        assert msg.type == "rating_update"

    def test_message_with_two_player_ratings(self):
        """RatingUpdateMessage should serialize 2-player game ratings."""
        msg = RatingUpdateMessage(
            ratings={
                "1": RatingChangeData(
                    old_rating=1200,
                    new_rating=1216,
                    old_belt="green",
                    new_belt="green",
                ),
                "2": RatingChangeData(
                    old_rating=1200,
                    new_rating=1184,
                    old_belt="green",
                    new_belt="green",
                ),
            }
        )
        assert "1" in msg.ratings
        assert "2" in msg.ratings
        assert msg.ratings["1"].new_rating == 1216
        assert msg.ratings["2"].new_rating == 1184

    def test_message_serialization(self):
        """RatingUpdateMessage should serialize to JSON correctly."""
        msg = RatingUpdateMessage(
            ratings={
                "1": RatingChangeData(
                    old_rating=1200,
                    new_rating=1216,
                    old_belt="green",
                    new_belt="green",
                    belt_changed=False,
                ),
            }
        )
        data = msg.model_dump()
        assert data["type"] == "rating_update"
        assert "ratings" in data
        assert "1" in data["ratings"]
        assert data["ratings"]["1"]["old_rating"] == 1200
        assert data["ratings"]["1"]["new_rating"] == 1216

    def test_message_with_four_player_ratings(self):
        """RatingUpdateMessage should handle 4-player game ratings."""
        msg = RatingUpdateMessage(
            ratings={
                "1": RatingChangeData(old_rating=1200, new_rating=1220, old_belt="green", new_belt="green"),
                "2": RatingChangeData(old_rating=1300, new_rating=1280, old_belt="purple", new_belt="purple"),
                "3": RatingChangeData(old_rating=1100, new_rating=1095, old_belt="green", new_belt="green"),
                "4": RatingChangeData(old_rating=1400, new_rating=1395, old_belt="purple", new_belt="purple"),
            }
        )
        assert len(msg.ratings) == 4
        # Winner (player 1) should gain rating
        assert msg.ratings["1"].new_rating > msg.ratings["1"].old_rating
