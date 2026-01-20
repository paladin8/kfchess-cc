"""Core game engine for Kung Fu Chess.

This module provides the main game logic. State is mutated in place
for performance. Use GameState.copy() if you need to preserve state
(e.g., for AI lookahead).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from kfchess.game.board import Board, BoardType
from kfchess.game.collision import (
    detect_collisions,
    get_interpolated_position,
    is_piece_moving,
    is_piece_on_cooldown,
)
from kfchess.game.moves import (
    Cooldown,
    Move,
    check_castling,
    compute_move_path,
    should_promote_pawn,
)
from kfchess.game.pieces import PieceType
from kfchess.game.state import (
    GameState,
    GameStatus,
    ReplayMove,
    Speed,
)


class GameEventType(Enum):
    """Types of events that occur during a game."""

    MOVE_STARTED = "move_started"
    MOVE_COMPLETED = "move_completed"
    CAPTURE = "capture"
    PROMOTION = "promotion"
    COOLDOWN_STARTED = "cooldown_started"
    COOLDOWN_ENDED = "cooldown_ended"
    GAME_STARTED = "game_started"
    GAME_OVER = "game_over"
    DRAW = "draw"


@dataclass
class GameEvent:
    """An event that occurred during a game tick.

    Attributes:
        type: Type of event
        tick: Tick when event occurred
        data: Event-specific data
    """

    type: GameEventType
    tick: int
    data: dict


class GameEngine:
    """Core game logic for Kung Fu Chess.

    All methods are static and mutate state in place for performance.
    Methods return the same state object along with any events generated.
    Use GameState.copy() before calling if you need to preserve state.
    """

    @staticmethod
    def create_game(
        speed: Speed,
        players: dict[int, str],
        board_type: BoardType = BoardType.STANDARD,
        game_id: str | None = None,
    ) -> GameState:
        """Create a new game with initial board state.

        Args:
            speed: Game speed setting
            players: Map of player number to player ID
            board_type: Type of board layout
            game_id: Optional game ID (generated if not provided)

        Returns:
            New GameState instance
        """
        if game_id is None:
            game_id = str(uuid.uuid4())[:8].upper()

        if board_type == BoardType.STANDARD:
            if len(players) != 2:
                raise ValueError("Standard board requires exactly 2 players")
            board = Board.create_standard()
        else:
            if len(players) < 2 or len(players) > 4:
                raise ValueError("4-player board requires 2-4 players")
            board = Board.create_4player()

        return GameState(
            game_id=game_id,
            board=board,
            speed=speed,
            players=players,
            status=GameStatus.WAITING,
        )

    @staticmethod
    def create_game_from_board(
        speed: Speed,
        players: dict[int, str],
        board: Board,
        game_id: str | None = None,
    ) -> GameState:
        """Create a game with a custom board (for campaigns/tests).

        Args:
            speed: Game speed setting
            players: Map of player number to player ID
            board: Custom board configuration
            game_id: Optional game ID

        Returns:
            New GameState instance
        """
        if game_id is None:
            game_id = str(uuid.uuid4())[:8].upper()

        return GameState(
            game_id=game_id,
            board=board,
            speed=speed,
            players=players,
            status=GameStatus.WAITING,
        )

    @staticmethod
    def set_player_ready(state: GameState, player: int) -> tuple[GameState, list[GameEvent]]:
        """Mark a player as ready. Mutates state in place.

        Args:
            state: Game state (will be mutated)
            player: Player number to mark as ready

        Returns:
            Tuple of (state, events)
        """
        events: list[GameEvent] = []

        if state.status != GameStatus.WAITING:
            return state, events

        if player not in state.players:
            return state, events

        state.ready_players.add(player)

        # For games with bots, bots are always "ready"
        for player_num, player_id in state.players.items():
            if player_id.startswith("bot:") or player_id.startswith("c:"):
                state.ready_players.add(player_num)

        # Check if all players are ready
        all_ready = all(p in state.ready_players for p in state.players.keys())

        if all_ready and len(state.players) >= 2:
            state.status = GameStatus.PLAYING
            state.started_at = datetime.now(UTC)
            state.current_tick = 0
            state.last_move_tick = 0
            state.last_capture_tick = 0
            events.append(
                GameEvent(
                    type=GameEventType.GAME_STARTED,
                    tick=0,
                    data={"players": state.players},
                )
            )

        return state, events

    @staticmethod
    def validate_move(
        state: GameState,
        player: int,
        piece_id: str,
        to_row: int,
        to_col: int,
    ) -> Move | None:
        """Validate and compute a move.

        Args:
            state: Current game state
            player: Player number attempting the move
            piece_id: ID of the piece to move
            to_row: Destination row
            to_col: Destination column

        Returns:
            Move object if valid, None if invalid
        """
        if state.status != GameStatus.PLAYING:
            return None

        # Find the piece
        piece = state.board.get_piece_by_id(piece_id)
        if piece is None:
            return None

        # Check piece belongs to player
        if piece.player != player:
            return None

        # Check piece is not captured
        if piece.captured:
            return None

        # Check piece is not already moving
        if is_piece_moving(piece_id, state.active_moves):
            return None

        # Check piece is not on cooldown
        if is_piece_on_cooldown(piece_id, state.cooldowns, state.current_tick):
            return None

        # Check for castling
        castling = check_castling(
            piece,
            state.board,
            to_row,
            to_col,
            state.active_moves,
            cooldowns=state.cooldowns,
            current_tick=state.current_tick,
        )
        if castling is not None:
            king_move, rook_move = castling
            # Move starts on NEXT tick (compensates for network delay)
            king_move.start_tick = state.current_tick + 1
            rook_move.start_tick = state.current_tick + 1
            return king_move

        # Compute the move path
        path = compute_move_path(piece, state.board, to_row, to_col, state.active_moves)
        if path is None:
            return None

        return Move(
            piece_id=piece_id,
            path=path,
            # Move starts on NEXT tick (compensates for network delay)
            start_tick=state.current_tick + 1,
        )

    @staticmethod
    def apply_move(state: GameState, move: Move) -> tuple[GameState, list[GameEvent]]:
        """Apply a validated move to the game state. Mutates state in place.

        Args:
            state: Game state (will be mutated)
            move: The move to apply

        Returns:
            Tuple of (state, events)
        """
        events: list[GameEvent] = []

        state.active_moves.append(move)
        state.last_move_tick = state.current_tick

        # Record for replay
        piece = state.board.get_piece_by_id(move.piece_id)
        if piece is not None:
            end_row, end_col = move.end_position
            state.replay_moves.append(
                ReplayMove(
                    tick=state.current_tick,
                    piece_id=move.piece_id,
                    to_row=int(end_row),
                    to_col=int(end_col),
                    player=piece.player,
                )
            )

        # Handle castling (extra rook move)
        if move.extra_move is not None:
            state.active_moves.append(move.extra_move)
            rook = state.board.get_piece_by_id(move.extra_move.piece_id)
            if rook is not None:
                end_row, end_col = move.extra_move.end_position
                state.replay_moves.append(
                    ReplayMove(
                        tick=state.current_tick,
                        piece_id=move.extra_move.piece_id,
                        to_row=int(end_row),
                        to_col=int(end_col),
                        player=rook.player,
                    )
                )

        events.append(
            GameEvent(
                type=GameEventType.MOVE_STARTED,
                tick=state.current_tick,
                data={
                    "piece_id": move.piece_id,
                    "path": move.path,
                },
            )
        )

        # Emit event for extra move (e.g., rook during castling)
        if move.extra_move is not None:
            events.append(
                GameEvent(
                    type=GameEventType.MOVE_STARTED,
                    tick=state.current_tick,
                    data={
                        "piece_id": move.extra_move.piece_id,
                        "path": move.extra_move.path,
                    },
                )
            )

        return state, events

    @staticmethod
    def tick(state: GameState) -> tuple[GameState, list[GameEvent]]:
        """Advance the game by one tick. Mutates state in place.

        This processes:
        1. Collision detection (captures)
        2. Move completion
        3. Pawn promotion
        4. Cooldown expiration
        5. Win/draw conditions

        Args:
            state: Game state (will be mutated)

        Returns:
            Tuple of (state, events that occurred)
        """
        if state.status != GameStatus.PLAYING:
            return state, []

        events: list[GameEvent] = []
        state.current_tick += 1

        config = state.config

        # 1. Detect and process collisions
        captures = detect_collisions(
            state.board.pieces,
            state.active_moves,
            state.current_tick,
            config.ticks_per_square,
        )

        for capture in captures:
            captured_piece = state.board.get_piece_by_id(capture.captured_piece_id)
            if captured_piece is not None:
                captured_piece.captured = True
                state.last_capture_tick = state.current_tick

                # Remove any active move for the captured piece
                # Also remove extra_move (e.g., rook move if king captured during castling)
                captured_move = next(
                    (m for m in state.active_moves if m.piece_id == capture.captured_piece_id),
                    None,
                )
                pieces_to_remove = {capture.captured_piece_id}
                if captured_move is not None and captured_move.extra_move is not None:
                    pieces_to_remove.add(captured_move.extra_move.piece_id)
                state.active_moves = [
                    m for m in state.active_moves if m.piece_id not in pieces_to_remove
                ]
                # Remove cooldown for captured piece
                state.cooldowns = [
                    c for c in state.cooldowns if c.piece_id != capture.captured_piece_id
                ]

                events.append(
                    GameEvent(
                        type=GameEventType.CAPTURE,
                        tick=state.current_tick,
                        data={
                            "capturing_piece_id": capture.capturing_piece_id,
                            "captured_piece_id": capture.captured_piece_id,
                            "position": capture.position,
                        },
                    )
                )

        # 2. Check for completed moves
        completed_moves: list[Move] = []
        for move in state.active_moves:
            total_ticks = move.num_squares * config.ticks_per_square
            ticks_elapsed = state.current_tick - move.start_tick

            if ticks_elapsed >= total_ticks:
                completed_moves.append(move)

        # Process completed moves
        for move in completed_moves:
            piece = state.board.get_piece_by_id(move.piece_id)
            if piece is not None and not piece.captured:
                # Update piece position to final position
                end_row, end_col = move.end_position
                piece.row = float(end_row)
                piece.col = float(end_col)
                piece.moved = True

                # Start cooldown
                state.cooldowns.append(
                    Cooldown(
                        piece_id=piece.id,
                        start_tick=state.current_tick,
                        duration=config.cooldown_ticks,
                    )
                )

                events.append(
                    GameEvent(
                        type=GameEventType.MOVE_COMPLETED,
                        tick=state.current_tick,
                        data={
                            "piece_id": move.piece_id,
                            "position": (end_row, end_col),
                        },
                    )
                )

                events.append(
                    GameEvent(
                        type=GameEventType.COOLDOWN_STARTED,
                        tick=state.current_tick,
                        data={
                            "piece_id": piece.id,
                            "duration": config.cooldown_ticks,
                        },
                    )
                )

                # 3. Check for pawn promotion
                if should_promote_pawn(piece, state.board, int(end_row), int(end_col)):
                    piece.type = PieceType.QUEEN
                    events.append(
                        GameEvent(
                            type=GameEventType.PROMOTION,
                            tick=state.current_tick,
                            data={
                                "piece_id": piece.id,
                                "new_type": "Q",
                            },
                        )
                    )

            # Remove completed move from active moves
            state.active_moves = [m for m in state.active_moves if m.piece_id != move.piece_id]

        # 4. Remove expired cooldowns
        state.cooldowns = [c for c in state.cooldowns if c.is_active(state.current_tick)]

        # 5. Check win/draw conditions
        winner = GameEngine.check_winner(state)
        if winner is not None:
            state.status = GameStatus.FINISHED
            state.finished_at = datetime.now(UTC)
            state.winner = winner

            if winner == 0:
                events.append(
                    GameEvent(
                        type=GameEventType.DRAW,
                        tick=state.current_tick,
                        data={},
                    )
                )
            else:
                events.append(
                    GameEvent(
                        type=GameEventType.GAME_OVER,
                        tick=state.current_tick,
                        data={"winner": winner},
                    )
                )

        return state, events

    @staticmethod
    def check_winner(state: GameState) -> int | None:
        """Check if the game has a winner.

        Returns:
            None if game is ongoing
            0 for draw
            1-4 for the winning player number
        """
        config = state.config

        # Check for captured kings - find players who still have their king
        players_with_king: list[int] = []
        for player_num in state.players.keys():
            king = state.board.get_king(player_num)
            if king is not None and not king.captured:
                players_with_king.append(player_num)

        # If only one player has their king, they win
        if len(players_with_king) == 1:
            return players_with_king[0]

        # If no players have their king (simultaneous capture), it's a draw
        if len(players_with_king) == 0:
            return 0

        # Multiple players still have their kings - check draw conditions
        # Only check after minimum game length
        if state.current_tick < config.min_draw_ticks:
            return None

        ticks_since_move = state.current_tick - state.last_move_tick
        ticks_since_capture = state.current_tick - state.last_capture_tick

        # Draw if no moves and no captures for extended periods
        if (
            ticks_since_move >= config.draw_no_move_ticks
            and ticks_since_capture >= config.draw_no_capture_ticks
        ):
            return 0

        return None

    @staticmethod
    def get_legal_moves(state: GameState, player: int) -> list[tuple[str, int, int]]:
        """Get all legal moves for a player.

        Args:
            state: Current game state
            player: Player number

        Returns:
            List of (piece_id, to_row, to_col) tuples
        """
        legal_moves: list[tuple[str, int, int]] = []

        for piece in state.board.get_pieces_for_player(player):
            if piece.captured:
                continue

            # Check if piece can move
            if is_piece_moving(piece.id, state.active_moves):
                continue

            if is_piece_on_cooldown(piece.id, state.cooldowns, state.current_tick):
                continue

            # Try all possible destinations
            for to_row in range(state.board.height):
                for to_col in range(state.board.width):
                    move = GameEngine.validate_move(state, player, piece.id, to_row, to_col)
                    if move is not None:
                        legal_moves.append((piece.id, to_row, to_col))

        return legal_moves

    @staticmethod
    def get_piece_state(
        state: GameState,
        piece_id: str,
    ) -> dict | None:
        """Get current state of a piece including interpolated position.

        Args:
            state: Current game state
            piece_id: ID of the piece

        Returns:
            Dictionary with piece state or None if not found
        """
        piece = state.board.get_piece_by_id(piece_id)
        if piece is None:
            return None

        config = state.config

        # Get interpolated position if moving
        interp_pos = get_interpolated_position(
            piece, state.active_moves, state.current_tick, config.ticks_per_square
        )

        # Check if on cooldown
        on_cooldown = is_piece_on_cooldown(piece_id, state.cooldowns, state.current_tick)

        # Get cooldown remaining
        cooldown_remaining = 0
        if on_cooldown:
            for cd in state.cooldowns:
                if cd.piece_id == piece_id:
                    end_tick = cd.start_tick + cd.duration
                    cooldown_remaining = max(0, end_tick - state.current_tick)
                    break

        return {
            "id": piece.id,
            "type": piece.type.value,
            "player": piece.player,
            "row": interp_pos[0],
            "col": interp_pos[1],
            "captured": piece.captured,
            "moving": is_piece_moving(piece_id, state.active_moves),
            "on_cooldown": on_cooldown,
            "cooldown_remaining": cooldown_remaining,
        }
