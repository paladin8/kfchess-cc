"""Extract AI-friendly state from GameState."""

from dataclasses import dataclass, field
from enum import Enum

from kfchess.game.moves import Cooldown, Move
from kfchess.game.pieces import Piece, PieceType
from kfchess.game.state import SPEED_CONFIGS, GameState, SpeedConfig


class PieceStatus(Enum):
    """Status of a piece from the AI's perspective."""

    IDLE = "idle"  # Can move right now
    TRAVELING = "traveling"  # Currently moving
    COOLDOWN = "cooldown"  # Waiting for cooldown


@dataclass
class AIPiece:
    """AI-friendly view of a piece."""

    piece: Piece
    status: PieceStatus
    cooldown_remaining: int  # Ticks remaining on cooldown (0 if not on cooldown)
    # For traveling pieces: destination square
    destination: tuple[int, int] | None
    # For traveling enemy pieces: direction of travel (row_delta, col_delta)
    travel_direction: tuple[float, float] | None
    # Current position (interpolated for traveling pieces, grid_position otherwise)
    current_position: tuple[int, int] = (0, 0)
    # For traveling pieces: ticks remaining until move completes
    travel_remaining_ticks: int = 0


@dataclass
class AIState:
    """AI-friendly snapshot of the game state."""

    pieces: list[AIPiece]
    ai_player: int
    current_tick: int
    board_width: int
    board_height: int
    speed_config: SpeedConfig | None = None
    # Pre-computed lookups (populated at construction)
    pieces_by_id: dict[str, AIPiece] = field(default_factory=dict)
    _movable: list[AIPiece] = field(default_factory=list)
    _own_pieces: list[AIPiece] = field(default_factory=list)
    _enemy_pieces: list[AIPiece] = field(default_factory=list)
    _enemy_king: AIPiece | None = None
    _own_king: AIPiece | None = None
    # Enemy piece escape move counts (populated by controller for L3+)
    enemy_escape_moves: dict[str, list[tuple[int, int]]] = field(default_factory=dict)

    def get_movable_pieces(self) -> list[AIPiece]:
        """Get pieces that can move right now (idle, not captured)."""
        return self._movable

    def get_own_pieces(self) -> list[AIPiece]:
        """Get all non-captured pieces belonging to the AI."""
        return self._own_pieces

    def get_enemy_pieces(self) -> list[AIPiece]:
        """Get all non-captured enemy pieces."""
        return self._enemy_pieces

    def get_enemy_king(self) -> AIPiece | None:
        """Get the nearest enemy king."""
        return self._enemy_king

    def get_own_king(self) -> AIPiece | None:
        """Get the AI's own king."""
        return self._own_king


class StateExtractor:
    """Converts GameState into AI-friendly structures."""

    @staticmethod
    def extract(
        state: GameState,
        ai_player: int,
        cooldown_buffer_ticks: int = 0,
        reaction_delay_ticks: int = 0,
    ) -> AIState:
        """Extract AI state from game state.

        Args:
            state: Current game state
            ai_player: Player number the AI controls
            cooldown_buffer_ticks: Extra ticks after cooldown expiry before
                a piece is considered idle (simulates reaction time).
            reaction_delay_ticks: Enemy moves younger than this many ticks
                are invisible to the AI (piece appears idle at start position).

        Returns:
            AI-friendly state snapshot
        """
        # Build lookup dicts once, filtering out enemy moves the AI can't
        # "see" yet (started fewer than reaction_delay_ticks ago)
        move_by_piece: dict[str, Move] = {}
        for m in state.active_moves:
            if (
                reaction_delay_ticks > 0
                and state.current_tick - m.start_tick < reaction_delay_ticks
            ):
                # Check if this move belongs to an enemy piece
                piece = state.board.get_piece_by_id(m.piece_id)
                if piece is not None and piece.player != ai_player:
                    continue  # AI hasn't seen this move yet
            move_by_piece[m.piece_id] = m
        cooldown_by_piece: dict[str, Cooldown] = {
            c.piece_id: c
            for c in state.cooldowns
            if c.is_active(state.current_tick)
        }

        # In 4-player mode, players whose king has been captured are eliminated.
        # Their remaining pieces can't move and shouldn't be treated as threats.
        eliminated_players: set[int] = set()
        for player_num in state.players:
            if player_num != ai_player:
                king = state.board.get_king(player_num)
                if king is None:
                    eliminated_players.add(player_num)

        pieces: list[AIPiece] = []
        pieces_by_id: dict[str, AIPiece] = {}
        movable: list[AIPiece] = []
        own_pieces: list[AIPiece] = []
        enemy_pieces: list[AIPiece] = []
        enemy_king: AIPiece | None = None
        own_king: AIPiece | None = None

        for piece in state.board.pieces:
            if piece.captured:
                continue

            # Determine status using dicts (O(1) lookups)
            move = move_by_piece.get(piece.id)
            cd = cooldown_by_piece.get(piece.id)

            # Check if piece recently came off cooldown (within buffer window)
            in_buffer = (
                cooldown_buffer_ticks > 0
                and piece.player == ai_player
                and piece.cooldown_end_tick > 0
                and state.current_tick - piece.cooldown_end_tick < cooldown_buffer_ticks
            )

            if move is not None:
                status = PieceStatus.TRAVELING
            elif cd is not None or in_buffer:
                status = PieceStatus.COOLDOWN
            else:
                status = PieceStatus.IDLE

            # Cooldown remaining
            cooldown_remaining = 0
            if cd is not None:
                end_tick = cd.start_tick + cd.duration
                cooldown_remaining = max(0, end_tick - state.current_tick)

            # Travel info + interpolated position
            destination = None
            travel_direction = None
            travel_remaining_ticks = 0
            current_position = piece.grid_position
            if move is not None:
                end_row, end_col = move.end_position

                if piece.player == ai_player:
                    destination = (int(end_row), int(end_col))
                else:
                    # Only expose destination for knights — their L-shaped
                    # path can't be derived from the travel direction, so
                    # the arrival field needs it explicitly.
                    if piece.type == PieceType.KNIGHT:
                        destination = (int(end_row), int(end_col))

                if piece.player != ai_player:
                    start_row, start_col = move.start_position
                    dr = end_row - start_row
                    dc = end_col - start_col
                    length = max(abs(dr), abs(dc))
                    if length > 0:
                        travel_direction = (dr / length, dc / length)

                # Compute interpolated position for traveling pieces
                tps = SPEED_CONFIGS[state.speed].ticks_per_square
                ticks_elapsed = state.current_tick - move.start_tick
                path = move.path
                total_squares = len(path) - 1
                total_travel_ticks = total_squares * tps
                travel_remaining_ticks = max(0, total_travel_ticks - ticks_elapsed)
                if total_squares > 0 and 0 <= ticks_elapsed < total_travel_ticks:
                    progress = ticks_elapsed / tps
                    seg = min(int(progress), total_squares - 1)
                    seg_frac = progress - seg
                    sr, sc = path[seg]
                    er, ec = path[seg + 1]
                    current_position = (
                        int(round(sr + (er - sr) * seg_frac)),
                        int(round(sc + (ec - sc) * seg_frac)),
                    )
                else:
                    current_position = (int(round(end_row)), int(round(end_col)))

            ai_piece = AIPiece(
                piece=piece,
                status=status,
                cooldown_remaining=cooldown_remaining,
                destination=destination,
                travel_direction=travel_direction,
                current_position=current_position,
                travel_remaining_ticks=travel_remaining_ticks,
            )
            pieces.append(ai_piece)
            pieces_by_id[piece.id] = ai_piece

            # Populate cached lists
            if piece.player == ai_player:
                own_pieces.append(ai_piece)
                if status == PieceStatus.IDLE:
                    movable.append(ai_piece)
                if piece.type == PieceType.KING:
                    own_king = ai_piece
            elif piece.player not in eliminated_players:
                enemy_pieces.append(ai_piece)
                if piece.type == PieceType.KING:
                    enemy_king = ai_piece

        return AIState(
            pieces=pieces,
            ai_player=ai_player,
            current_tick=state.current_tick,
            board_width=state.board.width,
            board_height=state.board.height,
            speed_config=SPEED_CONFIGS[state.speed],
            pieces_by_id=pieces_by_id,
            _movable=movable,
            _own_pieces=own_pieces,
            _enemy_pieces=enemy_pieces,
            _enemy_king=enemy_king,
            _own_king=own_king,
        )
