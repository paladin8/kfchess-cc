"""Core game engine for Kung Fu Chess.

This module provides the main game logic. State is mutated in place
for performance. Use GameState.copy() if you need to preserve state
(e.g., for AI lookahead).
"""

import logging
import random
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
    FOUR_PLAYER_ORIENTATIONS,
    Cooldown,
    Move,
    PathClearContext,
    build_path_clear_context,
    check_castling,
    compute_move_path,
    should_promote_pawn,
)
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import (
    CAMPAIGN_DRAW_NO_MOVE_TICKS,
    GameState,
    GameStatus,
    ReplayMove,
    Speed,
    WinReason,
)

logger = logging.getLogger(__name__)


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
        *,
        ignore_cooldown: bool = False,
        path_context: PathClearContext | None = None,
    ) -> Move | None:
        """Validate and compute a move.

        Args:
            state: Current game state
            player: Player number attempting the move
            piece_id: ID of the piece to move
            to_row: Destination row
            to_col: Destination column
            ignore_cooldown: If True, skip cooldown check (for AI escape analysis)
            path_context: Optional precomputed blocking context (avoids repeated
                iteration over active_moves when validating many candidates)

        Returns:
            Move object if valid, None if invalid
        """
        if state.status != GameStatus.PLAYING:
            return None

        # Check if player is eliminated (king captured) - applies to 4-player mode
        king = state.board.get_king(player)
        if king is None or king.captured:
            logger.warning(f"Move rejected: player {player} is eliminated (king captured)")
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
            logger.warning(f"Move rejected: {piece_id} is already moving")
            return None

        # Check piece is not on cooldown
        if not ignore_cooldown and is_piece_on_cooldown(piece_id, state.cooldowns, state.current_tick):
            logger.warning(f"Move rejected: {piece_id} is on cooldown")
            return None

        # Check for castling
        config = state.config
        castling = check_castling(
            piece,
            state.board,
            to_row,
            to_col,
            state.active_moves,
            cooldowns=state.cooldowns,
            current_tick=state.current_tick,
            ticks_per_square=config.ticks_per_square,
        )
        if castling is not None:
            king_move, rook_move = castling
            # Move starts on NEXT tick (compensates for network delay)
            king_move.start_tick = state.current_tick + 1
            rook_move.start_tick = state.current_tick + 1
            logger.debug(f"Castling validated for {piece_id}")
            return king_move

        # Compute the move path
        path = compute_move_path(
            piece, state.board, to_row, to_col, state.active_moves,
            current_tick=state.current_tick,
            ticks_per_square=config.ticks_per_square,
            path_context=path_context,
        )
        if path is None:
            logger.debug(
                f"Move rejected: {piece_id} from ({piece.row},{piece.col}) to ({to_row},{to_col}) - invalid path"
            )
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
        state.board.invalidate_position_map()

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

        # Invalidate position cache after captures and move completions
        if captures or completed_moves:
            state.board.invalidate_position_map()

        # 4. Remove expired cooldowns (record end tick on piece for AI buffer)
        active_cooldowns = []
        for c in state.cooldowns:
            if c.is_active(state.current_tick):
                active_cooldowns.append(c)
            else:
                piece = state.board.get_piece_by_id(c.piece_id)
                if piece is not None:
                    piece.cooldown_end_tick = state.current_tick
        state.cooldowns = active_cooldowns

        # 5. Check win/draw conditions
        winner, win_reason = GameEngine.check_winner(state)
        if winner is not None:
            state.status = GameStatus.FINISHED
            state.finished_at = datetime.now(UTC)
            state.winner = winner
            state.win_reason = win_reason

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
    def check_winner(state: GameState) -> tuple[int | None, WinReason | None]:
        """Check if the game has a winner.

        Returns:
            Tuple of (winner, win_reason) where:
            - winner: None if game is ongoing, 0 for draw, 1-4 for winning player
            - win_reason: None if ongoing, otherwise WinReason enum value
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
            return players_with_king[0], WinReason.KING_CAPTURED

        # If no players have their king (simultaneous capture), it's a draw
        if len(players_with_king) == 0:
            return 0, WinReason.DRAW

        # In multiplayer, if all remaining players are bots, end the game
        if len(players_with_king) >= 2 and len(state.players) > 2:
            all_bots = all(
                state.players.get(p, "").startswith(("bot:", "c:"))
                for p in players_with_king
            )
            if all_bots:
                return random.choice(players_with_king), WinReason.KING_CAPTURED

        # Multiple players still have their kings - check draw conditions

        # Campaign games: only draw on no-move timeout (no min game time,
        # no capture timeout). This prevents the AI from forcing a draw
        # via the capture timeout in puzzle-like campaign levels.
        # Note: last_move_tick only tracks human moves, so this is
        # effectively an AFK timer — AI moves don't prevent the draw.
        if state.is_campaign:
            ticks_since_move = state.current_tick - state.last_move_tick
            if ticks_since_move >= CAMPAIGN_DRAW_NO_MOVE_TICKS:
                return 0, WinReason.DRAW
            return None, None

        # Only check after minimum game length
        if state.current_tick < config.min_draw_ticks:
            return None, None

        ticks_since_move = state.current_tick - state.last_move_tick
        ticks_since_capture = state.current_tick - state.last_capture_tick

        # Draw if no human moves OR no captures for extended periods.
        # last_move_tick only tracks human moves (AFK detection), while
        # last_capture_tick tracks all captures. Each condition triggers
        # independently — e.g. AI keeps moving but no captures happen,
        # the capture timeout still fires.
        if (
            ticks_since_move >= config.draw_no_move_ticks
            or ticks_since_capture >= config.draw_no_capture_ticks
        ):
            return 0, WinReason.DRAW

        return None, None

    @staticmethod
    def get_legal_moves(state: GameState, player: int) -> list[tuple[str, int, int]]:
        """Get all legal moves for a player.

        Delegates to get_legal_moves_fast() which uses per-piece candidate
        generation for better performance.

        Args:
            state: Current game state
            player: Player number

        Returns:
            List of (piece_id, to_row, to_col) tuples
        """
        return GameEngine.get_legal_moves_fast(state, player)

    @staticmethod
    def get_legal_moves_fast(
        state: GameState, player: int, *, ignore_cooldown: bool = False,
    ) -> list[tuple[str, int, int]]:
        """Get all legal moves for a player using per-piece candidate generation.

        Instead of brute-forcing every board square, generates only geometrically
        reachable squares per piece type, then validates each candidate. This reduces
        validate_move calls from ~1024 to ~100 for a typical position.

        Bypasses ``validate_move`` for the inner loop — the precondition checks
        (game status, king alive, piece ownership, captured, moving, cooldown)
        are already performed once in the outer loop, so only
        ``compute_move_path`` / ``check_castling`` are called per candidate.

        Args:
            state: Current game state
            player: Player number
            ignore_cooldown: If True, include moves for pieces on cooldown
                (useful for computing potential escape squares)

        Returns:
            List of (piece_id, to_row, to_col) tuples
        """
        legal_moves: list[tuple[str, int, int]] = []

        king = state.board.get_king(player)
        if king is None or king.captured:
            return legal_moves

        # Cache config values and build blocking context once.
        config = state.config
        tps = config.ticks_per_square
        current_tick = state.current_tick
        active_moves = state.active_moves
        board = state.board

        ctx = build_path_clear_context(
            player, board, active_moves, current_tick, tps,
        )

        for piece in board.get_pieces_for_player(player):
            if piece.captured:
                continue
            # Set lookup replaces is_piece_moving's any() linear scan
            if piece.id in ctx.moving_piece_ids:
                continue
            if not ignore_cooldown and is_piece_on_cooldown(piece.id, state.cooldowns, current_tick):
                continue

            is_king = piece.type == PieceType.KING
            candidates = _get_piece_candidates(piece, board, active_moves)
            for to_row, to_col in candidates:
                # For kings, check castling first (handles 2-square moves)
                if is_king:
                    castling = check_castling(
                        piece, board, to_row, to_col, active_moves,
                        cooldowns=state.cooldowns,
                        current_tick=current_tick,
                        ticks_per_square=tps,
                    )
                    if castling is not None:
                        legal_moves.append((piece.id, to_row, to_col))
                        continue

                # Compute the move path directly (precondition checks
                # already done in the outer loop above)
                path = compute_move_path(
                    piece, board, to_row, to_col, active_moves,
                    current_tick=current_tick,
                    ticks_per_square=tps,
                    path_context=ctx,
                )
                if path is not None:
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


def _get_piece_candidates(
    piece: Piece, board: Board, active_moves: list[Move]
) -> list[tuple[int, int]]:
    """Generate candidate destination squares for a piece based on its type.

    Returns only geometrically reachable squares, dramatically reducing the
    number of validate_move calls needed compared to brute-forcing all squares.
    """
    from_row, from_col = piece.grid_position

    match piece.type:
        case PieceType.PAWN:
            return _pawn_candidates(piece, board, from_row, from_col, active_moves)
        case PieceType.KNIGHT:
            return _knight_candidates(board, from_row, from_col)
        case PieceType.BISHOP:
            return _slider_candidates(board, from_row, from_col, _BISHOP_DIRS, active_moves)
        case PieceType.ROOK:
            return _slider_candidates(board, from_row, from_col, _ROOK_DIRS, active_moves)
        case PieceType.QUEEN:
            return _slider_candidates(board, from_row, from_col, _QUEEN_DIRS, active_moves)
        case PieceType.KING:
            return _king_candidates(piece, board, from_row, from_col)
        case _:
            return []


_ROOK_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]
_BISHOP_DIRS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
_QUEEN_DIRS = _ROOK_DIRS + _BISHOP_DIRS

_KNIGHT_OFFSETS = [
    (-2, -1), (-2, 1), (-1, -2), (-1, 2),
    (1, -2), (1, 2), (2, -1), (2, 1),
]


def _pawn_candidates(
    piece: Piece, board: Board, from_row: int, from_col: int, active_moves: list[Move]
) -> list[tuple[int, int]]:
    """Generate pawn candidate squares."""
    candidates: list[tuple[int, int]] = []

    if board.board_type == BoardType.STANDARD:
        direction = -1 if piece.player == 1 else 1
        start_row = 6 if piece.player == 1 else 1

        # Forward 1
        r = from_row + direction
        if 0 <= r < board.height:
            candidates.append((r, from_col))
        # Forward 2 from start
        if from_row == start_row:
            r2 = from_row + 2 * direction
            if 0 <= r2 < board.height:
                candidates.append((r2, from_col))
        # Diagonal captures (only if occupied by enemy or en-passant possible)
        for dc in (-1, 1):
            c = from_col + dc
            dr = from_row + direction
            if 0 <= dr < board.height and 0 <= c < board.width:
                occupant = board.get_piece_at(dr, c)
                if occupant is not None and occupant.player != piece.player:
                    candidates.append((dr, c))
                elif not occupant:
                    # En-passant: check if an enemy pawn just moved to adjacent square
                    adj = board.get_piece_at(from_row, c)
                    if adj is not None and adj.player != piece.player and adj.type == PieceType.PAWN:
                        candidates.append((dr, c))
    else:
        orient = FOUR_PLAYER_ORIENTATIONS.get(piece.player)
        if orient is None:
            return candidates
        fwd_r, fwd_c = orient.forward

        # Forward 1
        r1, c1 = from_row + fwd_r, from_col + fwd_c
        if board.is_valid_square(r1, c1):
            candidates.append((r1, c1))

        # Forward 2 from start
        if orient.axis == "col":
            is_start = from_col == orient.pawn_home_axis
        else:
            is_start = from_row == orient.pawn_home_axis
        if is_start:
            r2, c2 = from_row + 2 * fwd_r, from_col + 2 * fwd_c
            if board.is_valid_square(r2, c2):
                candidates.append((r2, c2))

        # Diagonal captures: one forward + one lateral (only if enemy present)
        if orient.axis == "col":
            # Lateral is row direction
            for dr in (-1, 1):
                r, c = from_row + dr, from_col + fwd_c
                if board.is_valid_square(r, c):
                    occupant = board.get_piece_at(r, c)
                    if occupant is not None and occupant.player != piece.player:
                        candidates.append((r, c))
        else:
            # Lateral is col direction
            for dc in (-1, 1):
                r, c = from_row + fwd_r, from_col + dc
                if board.is_valid_square(r, c):
                    occupant = board.get_piece_at(r, c)
                    if occupant is not None and occupant.player != piece.player:
                        candidates.append((r, c))

    return candidates


def _knight_candidates(board: Board, from_row: int, from_col: int) -> list[tuple[int, int]]:
    """Generate knight candidate squares (up to 8 L-shapes)."""
    candidates: list[tuple[int, int]] = []
    for dr, dc in _KNIGHT_OFFSETS:
        r, c = from_row + dr, from_col + dc
        if board.is_valid_square(r, c):
            candidates.append((r, c))
    return candidates


def _slider_candidates(
    board: Board,
    from_row: int,
    from_col: int,
    directions: list[tuple[int, int]],
    active_moves: list[Move],
) -> list[tuple[int, int]]:
    """Generate slider (rook/bishop/queen) candidates by ray-casting.

    Walks each ray direction, collecting squares up to and including the first
    occupied square (by a stationary piece). Moving pieces are treated as vacated.
    """
    # Build set of moving piece IDs for vacancy check
    moving_ids = {m.piece_id for m in active_moves}

    candidates: list[tuple[int, int]] = []
    for dr, dc in directions:
        r, c = from_row + dr, from_col + dc
        while board.is_valid_square(r, c):
            candidates.append((r, c))
            # Stop at first stationary piece (own or enemy)
            occupant = board.get_piece_at(r, c)
            if occupant is not None and occupant.id not in moving_ids:
                break
            r += dr
            c += dc
    return candidates


def _king_candidates(
    piece: Piece, board: Board, from_row: int, from_col: int
) -> list[tuple[int, int]]:
    """Generate king candidate squares (8 adjacents + castling targets)."""
    candidates: list[tuple[int, int]] = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            r, c = from_row + dr, from_col + dc
            if board.is_valid_square(r, c):
                candidates.append((r, c))

    # Castling candidates (king moves 2 squares)
    if not piece.moved:
        if board.board_type == BoardType.STANDARD:
            # Kingside and queenside
            for dc in (-2, 2):
                c = from_col + dc
                if board.is_valid_square(from_row, c):
                    candidates.append((from_row, c))
        else:
            orient = FOUR_PLAYER_ORIENTATIONS.get(piece.player)
            if orient is not None:
                if orient.axis == "row":
                    # Horizontal castling
                    for dc in (-2, 2):
                        c = from_col + dc
                        if board.is_valid_square(from_row, c):
                            candidates.append((from_row, c))
                else:
                    # Vertical castling
                    for dr in (-2, 2):
                        r = from_row + dr
                        if board.is_valid_square(r, from_col):
                            candidates.append((r, from_col))

    return candidates
