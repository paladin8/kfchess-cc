# ELO Rating System Design

This document describes the design for implementing an ELO-based rating system for Kung Fu Chess.

---

## Overview

The rating system tracks player skill across four separate rating pools:
- **2-Player Standard** (`2p_standard`)
- **2-Player Lightning** (`2p_lightning`)
- **4-Player Standard** (`4p_standard`)
- **4-Player Lightning** (`4p_lightning`)

Ratings update only after **ranked games**. Each rating corresponds to a martial arts belt rank based on thresholds.

---

## ELO Algorithm

Adapted from legacy implementation (`/home/jeffr/code/kfchess/lib/elo.py`):

```python
import math
from dataclasses import dataclass

DEFAULT_RATING = 1200
MIN_RATING = 100  # Floor to prevent discouraging new players
K_FACTOR = 32
K_FACTOR_HIGH = 16  # Used for ratings above HIGH_RATING_THRESHOLD
HIGH_RATING_THRESHOLD = 2000


@dataclass
class RatingChange:
    """Result of a rating update for a single player."""
    old_rating: int
    new_rating: int
    old_belt: str
    new_belt: str
    belt_changed: bool = False

    def __post_init__(self):
        self.belt_changed = self.old_belt != self.new_belt


def get_k_factor(rating: int) -> int:
    """Get K-factor based on rating. Lower K at high ratings for stability."""
    return K_FACTOR_HIGH if rating >= HIGH_RATING_THRESHOLD else K_FACTOR


def clamp_rating(rating: int) -> int:
    """Ensure rating doesn't fall below minimum."""
    return max(MIN_RATING, rating)


def calculate_expected_score(rating_a: int, rating_b: int) -> float:
    """Calculate expected score for player A against player B."""
    return 1.0 / (1 + math.pow(10, (rating_b - rating_a) / 400.0))

def update_ratings_2p(
    rating_a: int,
    rating_b: int,
    winner: int  # 0=draw, 1=player A won, 2=player B won
) -> tuple[int, int]:
    """Calculate new ratings for a 2-player game."""
    ea = calculate_expected_score(rating_a, rating_b)
    eb = 1.0 - ea

    if winner == 0:  # Draw
        sa, sb = 0.5, 0.5
    elif winner == 1:  # Player A won
        sa, sb = 1.0, 0.0
    else:  # Player B won
        sa, sb = 0.0, 1.0

    # Use dynamic K-factor based on each player's rating
    k_a = get_k_factor(rating_a)
    k_b = get_k_factor(rating_b)

    new_a = clamp_rating(int(round(rating_a + k_a * (sa - ea))))
    new_b = clamp_rating(int(round(rating_b + k_b * (sb - eb))))

    return new_a, new_b
```

### 4-Player ELO

For 4-player games, each player's rating change is calculated based on their performance against all opponents:

```python
def update_ratings_4p(
    ratings: dict[int, int],  # {player_num: rating}
    winner: int  # 0=draw, 1-4=winner
) -> dict[int, int]:
    """Calculate new ratings for a 4-player game.

    Each player's rating change is the average of their expected
    performance against each opponent.

    Design note: When two players both lose to a third player, they are
    treated as having drawn against each other (actual=0.5). This is a
    simplification - a more complex system could track elimination order
    to give partial credit for lasting longer. The current approach is
    simpler and commonly used in multi-player ELO variants.
    """
    new_ratings = {}
    players = list(ratings.keys())

    for player in players:
        total_change = 0.0
        my_rating = ratings[player]
        k = get_k_factor(my_rating)

        for opponent in players:
            if opponent == player:
                continue

            opp_rating = ratings[opponent]
            expected = calculate_expected_score(my_rating, opp_rating)

            # Determine actual score against this opponent
            if winner == 0:  # Draw
                actual = 0.5
            elif winner == player:  # I won
                actual = 1.0
            elif winner == opponent:  # This opponent won
                actual = 0.0
            else:  # Neither of us won - treated as draw
                actual = 0.5

            total_change += k * (actual - expected)

        # Average the change across all opponents
        avg_change = total_change / (len(players) - 1)
        new_ratings[player] = clamp_rating(int(round(my_rating + avg_change)))

    return new_ratings
```

---

## Belt System

### Rating Thresholds

| Belt | Rating Range | Icon Path |
|------|-------------|-----------|
| None | (unranked) | `belt-none.png` |
| White | 0 - 899 | `belt-white.png` |
| Yellow | 900 - 1099 | `belt-yellow.png` |
| Green | 1100 - 1299 | `belt-green.png` |
| Purple | 1300 - 1499 | `belt-purple.png` |
| Orange | 1500 - 1699 | `belt-orange.png` |
| Blue | 1700 - 1899 | `belt-blue.png` |
| Brown | 1900 - 2099 | `belt-brown.png` |
| Red | 2100 - 2299 | `belt-red.png` |
| Black | 2300+ | `belt-black.png` |

New players start at 1200 rating (Green belt).

### Belt Determination Logic

```python
BELT_THRESHOLDS = [
    (2300, "black"),
    (2100, "red"),
    (1900, "brown"),
    (1700, "blue"),
    (1500, "orange"),
    (1300, "purple"),
    (1100, "green"),
    (900, "yellow"),
    (0, "white"),
]

def get_belt(rating: int | None) -> str:
    """Get belt name for a given rating. Returns 'none' for unranked."""
    if rating is None:
        return "none"
    for threshold, belt in BELT_THRESHOLDS:
        if rating >= threshold:
            return belt
    return "white"

```

### Belt Icons

Icons are stored on S3 at:
```
https://com-kfchess-public.s3.amazonaws.com/static/belt-{name}.png
```

Source files: `/home/jeffr/code/kfchess/ui/static/belt-*.png`

**Upload command:**
```bash
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-none.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-white.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-yellow.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-green.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-purple.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-orange.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-blue.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-brown.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-red.png s3://com-kfchess-public/static/
aws s3 cp /home/jeffr/code/kfchess/ui/static/belt-black.png s3://com-kfchess-public/static/
```

---

## Data Model Changes

### User Ratings Schema

Update the `ratings` JSONB field structure from:
```json
{"standard": 1200, "lightning": 1350}
```

To the new 4-pool structure with embedded game counts:
```json
{
  "2p_standard": {"rating": 1200, "games": 50, "wins": 28},
  "2p_lightning": {"rating": 1350, "games": 23, "wins": 15},
  "4p_standard": {"rating": 1200, "games": 0, "wins": 0},
  "4p_lightning": {"rating": 1200, "games": 0, "wins": 0}
}
```

This structure allows efficient leaderboard queries without JOIN operations while tracking games played and wins for each mode.

### User Model Update

```python
# server/src/kfchess/db/models.py

class User(SQLAlchemyBaseUserTable[int], Base):
    # ... existing fields ...

    # Ratings stored as JSONB with structure:
    # {mode: {"rating": int, "games": int, "wins": int}}
    ratings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
```

### Helper Functions

```python
@dataclass
class UserRatingStats:
    """User's rating stats for a specific mode."""
    rating: int
    games: int
    wins: int

    @classmethod
    def default(cls) -> "UserRatingStats":
        return cls(rating=DEFAULT_RATING, games=0, wins=0)


def get_rating_key(player_count: int, speed: str) -> str:
    """Get the rating key for a game mode."""
    prefix = "2p" if player_count == 2 else "4p"
    return f"{prefix}_{speed}"


def get_user_rating_stats(user: User, player_count: int, speed: str) -> UserRatingStats:
    """Get user's rating stats for a specific mode."""
    key = get_rating_key(player_count, speed)
    data = user.ratings.get(key)
    if data is None:
        return UserRatingStats.default()
    return UserRatingStats(
        rating=data.get("rating", DEFAULT_RATING),
        games=data.get("games", 0),
        wins=data.get("wins", 0),
    )


def get_user_rating(user: User, player_count: int, speed: str) -> int:
    """Get user's rating for a specific mode (convenience wrapper)."""
    return get_user_rating_stats(user, player_count, speed).rating
```

### Migration

```python
# Alembic migration to convert existing ratings
def upgrade():
    """Convert old rating format to new format with game stats.

    Old format: {"standard": 1200, "lightning": 1350}
    New format: {
        "2p_standard": {"rating": 1200, "games": 0, "wins": 0},
        "2p_lightning": {"rating": 1350, "games": 0, "wins": 0},
        "4p_standard": {"rating": 1200, "games": 0, "wins": 0},
        "4p_lightning": {"rating": 1200, "games": 0, "wins": 0}
    }

    Note: Historical game counts are not migrated (would require scanning
    all replays). New games will track counts going forward.
    """
    op.execute("""
        UPDATE users
        SET ratings = jsonb_build_object(
            '2p_standard', jsonb_build_object(
                'rating', COALESCE((ratings->>'standard')::int, 1200),
                'games', 0,
                'wins', 0
            ),
            '2p_lightning', jsonb_build_object(
                'rating', COALESCE((ratings->>'lightning')::int, 1200),
                'games', 0,
                'wins', 0
            ),
            '4p_standard', jsonb_build_object('rating', 1200, 'games', 0, 'wins', 0),
            '4p_lightning', jsonb_build_object('rating', 1200, 'games', 0, 'wins', 0)
        )
        WHERE ratings != '{}'::jsonb
    """)
```

---

## Rating Update Flow

### Conditions for Rating Update

Ratings only update when ALL conditions are met:
1. `lobby.is_ranked == True`
2. All players are human (no AI slots)
3. Game completed normally (see below)
4. All players have accounts (no guests)

#### Game Completion Criteria

A game is considered "completed normally" when:
- **King captured**: A player's king is captured (standard win condition)
- **Draw by no moves**: No valid moves available for draw timeout period
- **Draw by no captures**: No captures for extended period
- **Resignation**: Player explicitly resigns (future feature)

A game is **NOT** eligible for rating update when:
- **Abandoned**: A player disconnects and doesn't reconnect within grace period
- **Cancelled**: Game cancelled before first move (both players must have moved)
- **Technical error**: Server error causes game termination

The `win_reason` field in GameState tracks how the game ended:
```python
WIN_REASONS_RATED = {"king_captured", "draw_no_moves", "draw_no_captures", "resignation"}
WIN_REASONS_NOT_RATED = {"abandoned", "cancelled", "error"}
```

### Update Process

1. **Game ends** → `game_service.finish_game()` called
2. **Check eligibility** → Verify ranked game conditions
3. **Fetch ratings** → Get current ratings for all players
4. **Calculate new ratings** → Use 2p or 4p algorithm based on player count
5. **Update database** → Store new ratings atomically
6. **Broadcast results** → Send `rating_update` message to all clients

### Backend Implementation

```python
# server/src/kfchess/services/rating_service.py

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


class RatingService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def update_ratings_for_game(
        self,
        game_id: str,
        game_state: GameState,
        lobby: Lobby,
        player_user_ids: dict[int, int],  # player_num -> user_id
    ) -> dict[int, RatingChange] | None:
        """Update ratings after a ranked game.

        Returns dict of {player_num: RatingChange} or None if not eligible.

        Uses SELECT FOR UPDATE to prevent race conditions when the same
        player finishes multiple games simultaneously.
        """
        # Check eligibility
        if not lobby.is_ranked:
            return None
        if any(p.is_ai for p in lobby.players):
            return None
        if any(p.user_id is None for p in lobby.players):
            return None

        rating_key = get_rating_key(lobby.player_count, lobby.speed)
        user_ids = list(player_user_ids.values())

        # Use a transaction with row-level locking
        async with self.session.begin():
            # Lock user rows to prevent concurrent rating updates
            # ORDER BY id prevents deadlocks when multiple games finish
            stmt = (
                select(User)
                .where(User.id.in_(user_ids))
                .order_by(User.id)
                .with_for_update()
            )
            result = await self.session.execute(stmt)
            users = {u.id: u for u in result.scalars().all()}

            # Get current ratings
            current_stats = {
                player_num: get_user_rating_stats(users[user_id], lobby.player_count, lobby.speed)
                for player_num, user_id in player_user_ids.items()
            }
            current_ratings = {pn: stats.rating for pn, stats in current_stats.items()}

            # Calculate new ratings
            if lobby.player_count == 2:
                new_a, new_b = update_ratings_2p(
                    current_ratings[1],
                    current_ratings[2],
                    game_state.winner or 0
                )
                new_ratings = {1: new_a, 2: new_b}
            else:
                new_ratings = update_ratings_4p(current_ratings, game_state.winner or 0)

            # Update all users atomically using JSONB operators
            for player_num, user_id in player_user_ids.items():
                user = users[user_id]
                old_stats = current_stats[player_num]
                new_rating = new_ratings[player_num]
                is_winner = game_state.winner == player_num

                # Update the nested JSONB structure atomically
                new_stats = {
                    "rating": new_rating,
                    "games": old_stats.games + 1,
                    "wins": old_stats.wins + (1 if is_winner else 0),
                }
                user.ratings = {**user.ratings, rating_key: new_stats}

        # Return changes (after transaction commits)
        return {
            player_num: RatingChange(
                old_rating=current_ratings[player_num],
                new_rating=new_ratings[player_num],
                old_belt=get_belt(current_ratings[player_num]),
                new_belt=get_belt(new_ratings[player_num]),
            )
            for player_num in player_user_ids
        }
```

### WebSocket Message

```python
# Server -> Client after ranked game ends
{
    "type": "rating_update",
    "payload": {
        "ratings": {
            "1": {
                "old_rating": 1200,
                "new_rating": 1215,
                "old_belt": "green",
                "new_belt": "green"
            },
            "2": {
                "old_rating": 1180,
                "new_rating": 1165,
                "old_belt": "yellow",
                "new_belt": "yellow"
            }
        }
    }
}
```

---

## Watch Page & Leaderboard

### Route Structure

Create a new `/watch` route with tabbed navigation:

```
/watch              -> defaults to /watch/live
/watch/live         -> Live Games tab
/watch/replays      -> Replays tab
/watch/leaderboard  -> Leaderboard tab
```

### Leaderboard API

#### Main Leaderboard Endpoint

**Endpoint:** `GET /api/leaderboard`

**Query Parameters:**
- `mode`: Rating pool (`2p_standard`, `2p_lightning`, `4p_standard`, `4p_lightning`)
- `limit`: Max results (default: 50, max: 100)
- `offset`: Pagination offset

**Response Headers:**
- `Cache-Control: public, max-age=60` (1 minute cache)

**Response:**
```json
{
  "mode": "2p_standard",
  "entries": [
    {
      "rank": 1,
      "user_id": 123,
      "username": "GrandMaster42",
      "rating": 1892,
      "belt": "black",
      "games_played": 156,
      "wins": 98
    },
    {
      "rank": 2,
      "user_id": 456,
      "username": "ChessNinja",
      "rating": 1845,
      "belt": "black",
      "games_played": 89,
      "wins": 52
    }
  ],
  "total_count": 1234
}
```

#### User's Own Rank Endpoint

**Endpoint:** `GET /api/leaderboard/me`

**Query Parameters:**
- `mode`: Rating pool (required)

**Response:**
```json
{
  "mode": "2p_standard",
  "rank": 156,
  "rating": 1245,
  "belt": "green",
  "games_played": 42,
  "wins": 23,
  "percentile": 88.5
}
```

### Database Indexes

Add indexes to support efficient leaderboard queries on JSONB fields:

```sql
-- Functional indexes for each rating mode (add in Alembic migration)
CREATE INDEX idx_users_rating_2p_standard
ON users (((ratings->'2p_standard'->>'rating')::int) DESC NULLS LAST)
WHERE ratings ? '2p_standard';

CREATE INDEX idx_users_rating_2p_lightning
ON users (((ratings->'2p_lightning'->>'rating')::int) DESC NULLS LAST)
WHERE ratings ? '2p_lightning';

CREATE INDEX idx_users_rating_4p_standard
ON users (((ratings->'4p_standard'->>'rating')::int) DESC NULLS LAST)
WHERE ratings ? '4p_standard';

CREATE INDEX idx_users_rating_4p_lightning
ON users (((ratings->'4p_lightning'->>'rating')::int) DESC NULLS LAST)
WHERE ratings ? '4p_lightning';

-- GIN index for general JSONB queries
CREATE INDEX idx_users_ratings_gin ON users USING gin(ratings);
```

### Backend Implementation

```python
# server/src/kfchess/api/leaderboard.py

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api", tags=["leaderboard"])

VALID_MODES = {"2p_standard", "2p_lightning", "4p_standard", "4p_lightning"}


@router.get("/leaderboard")
async def get_leaderboard(
    mode: str = Query(..., pattern="^(2p|4p)_(standard|lightning)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get leaderboard for a specific rating mode.

    Results are cached for 60 seconds to reduce database load.
    """
    # Query with the functional index
    query = text("""
        SELECT
            id,
            username,
            (ratings->:mode->>'rating')::int as rating,
            (ratings->:mode->>'games')::int as games_played,
            (ratings->:mode->>'wins')::int as wins
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
        ORDER BY (ratings->:mode->>'rating')::int DESC
        LIMIT :limit OFFSET :offset
    """)

    result = await db.execute(query, {"mode": mode, "limit": limit, "offset": offset})
    rows = result.fetchall()

    # Get total count for pagination
    count_query = text("""
        SELECT COUNT(*)
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
    """)
    total = (await db.execute(count_query, {"mode": mode})).scalar()

    entries = [
        {
            "rank": offset + i + 1,
            "user_id": row.id,
            "username": row.username,
            "rating": row.rating,
            "belt": get_belt(row.rating),
            "games_played": row.games_played,
            "wins": row.wins,
        }
        for i, row in enumerate(rows)
    ]

    response = JSONResponse({
        "mode": mode,
        "entries": entries,
        "total_count": total,
    })
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@router.get("/leaderboard/me")
async def get_my_rank(
    mode: str = Query(..., pattern="^(2p|4p)_(standard|lightning)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_active_user),
):
    """Get the current user's rank in a specific leaderboard."""
    stats = get_user_rating_stats(user, *mode.split("_", 1))

    if stats.games == 0:
        return {"mode": mode, "rank": None, "rating": stats.rating, "belt": get_belt(stats.rating),
                "games_played": 0, "wins": 0, "percentile": None}

    # Count users with higher rating
    rank_query = text("""
        SELECT COUNT(*) + 1
        FROM users
        WHERE ratings ? :mode
          AND (ratings->:mode->>'games')::int > 0
          AND (ratings->:mode->>'rating')::int > :rating
    """)
    rank = (await db.execute(rank_query, {"mode": mode, "rating": stats.rating})).scalar()

    # Get total for percentile
    total_query = text("""
        SELECT COUNT(*)
        FROM users
        WHERE ratings ? :mode AND (ratings->:mode->>'games')::int > 0
    """)
    total = (await db.execute(total_query, {"mode": mode})).scalar()

    percentile = round((1 - (rank - 1) / total) * 100, 1) if total > 0 else None

    return {
        "mode": mode,
        "rank": rank,
        "rating": stats.rating,
        "belt": get_belt(stats.rating),
        "games_played": stats.games,
        "wins": stats.wins,
        "percentile": percentile,
    }
```

### Frontend Components

```
client/src/pages/Watch.tsx           # Tab container
client/src/components/LiveGames.tsx   # Live games list (existing lobbies logic)
client/src/components/ReplaysList.tsx # Replays list (move from Replays.tsx)
client/src/components/Leaderboard.tsx # New leaderboard component
```

### Leaderboard UI

```tsx
// client/src/components/Leaderboard.tsx

interface LeaderboardEntry {
  rank: number;
  userId: number;
  username: string;
  rating: number;
  belt: string;
  gamesPlayed: number;
}

function Leaderboard() {
  const [mode, setMode] = useState<RatingMode>('2p_standard');
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);

  return (
    <div className="leaderboard">
      <div className="leaderboard-filters">
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="2p_standard">2-Player Standard</option>
          <option value="2p_lightning">2-Player Lightning</option>
          <option value="4p_standard">4-Player Standard</option>
          <option value="4p_lightning">4-Player Lightning</option>
        </select>
      </div>

      <table className="leaderboard-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Player</th>
            <th>Belt</th>
            <th>Rating</th>
            <th>Games</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry) => (
            <tr key={entry.userId}>
              <td>{entry.rank}</td>
              <td>{entry.username}</td>
              <td>
                <img
                  src={staticUrl(`belt-${entry.belt}.png`)}
                  alt={entry.belt}
                  className="belt-icon"
                />
              </td>
              <td>{entry.rating}</td>
              <td>{entry.gamesPlayed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

## Profile Integration

### Profile Page Updates

Display user's ratings and belts on their profile:

```tsx
// In Profile.tsx
<div className="profile-ratings">
  <h2>Ratings</h2>
  <div className="rating-cards">
    {['2p_standard', '2p_lightning', '4p_standard', '4p_lightning'].map((mode) => (
      <div key={mode} className="rating-card">
        <img src={staticUrl(`belt-${getBelt(ratings[mode])}.png`)} />
        <div className="rating-mode">{formatModeName(mode)}</div>
        <div className="rating-value">{ratings[mode] ?? 1200}</div>
      </div>
    ))}
  </div>
</div>
```

### Game End Screen

Show rating change after ranked games:

```tsx
// In GameOverOverlay.tsx
{ratingChange && (
  <div className="rating-change">
    <div className="rating-change-value">
      {ratingChange.newRating > ratingChange.oldRating ? '+' : ''}
      {ratingChange.newRating - ratingChange.oldRating}
    </div>
    <div className="rating-change-total">
      {ratingChange.oldRating} → {ratingChange.newRating}
    </div>
    {ratingChange.oldBelt !== ratingChange.newBelt && (
      <div className="belt-change">
        New belt: {ratingChange.newBelt}!
        <img src={staticUrl(`belt-${ratingChange.newBelt}.png`)} />
      </div>
    )}
  </div>
)}
```

---

## Integration Points

This section documents exactly where to integrate rating updates in the existing codebase.

### Game Handler Integration

The rating update should occur in `server/src/kfchess/ws/handler.py` after the game ends and replay is saved:

```python
# In _run_game_loop(), after game finishes (around line 706-710):

# Existing code:
await _save_replay(game_id, service)

# ADD: Update ratings for ranked games
rating_changes = await _update_ratings(game_id, state, lobby_code)

# Existing code:
await _notify_lobby_game_ended(game_id, state.winner, reason)

# ADD: Broadcast rating changes to players
if rating_changes:
    await _broadcast_rating_update(game_id, rating_changes)
```

### New Handler Functions

```python
async def _update_ratings(
    game_id: str,
    state: GameState,
    lobby_code: str,
) -> dict[int, RatingChange] | None:
    """Update ratings after a ranked game completes."""
    from kfchess.services.rating_service import RatingService
    from kfchess.lobby.manager import lobby_manager

    lobby = await lobby_manager.get_lobby(lobby_code)
    if lobby is None:
        return None

    # Build player_num -> user_id mapping
    player_user_ids = {}
    for player in lobby.players:
        if player.user_id is not None:
            player_user_ids[player.player_slot] = player.user_id

    async with get_db_session() as session:
        rating_service = RatingService(session)
        return await rating_service.update_ratings_for_game(
            game_id, state, lobby, player_user_ids
        )


async def _broadcast_rating_update(
    game_id: str,
    rating_changes: dict[int, RatingChange],
) -> None:
    """Send rating update message to all connected players."""
    message = RatingUpdateMessage(
        ratings={
            str(player_num): {
                "old_rating": change.old_rating,
                "new_rating": change.new_rating,
                "old_belt": change.old_belt,
                "new_belt": change.new_belt,
                "belt_changed": change.belt_changed,
            }
            for player_num, change in rating_changes.items()
        }
    )
    await broadcast_to_game(game_id, message)
```

### Protocol Updates

Add to `server/src/kfchess/ws/protocol.py`:

```python
@dataclass
class RatingUpdateMessage(ServerMessage):
    """Sent after a ranked game to report rating changes."""
    type: str = "rating_update"
    ratings: dict[str, dict] = field(default_factory=dict)
```

### Frontend Store Integration

Update `client/src/stores/game.ts` to handle rating updates:

```typescript
// In WebSocket message handler
case 'rating_update':
  set({
    ratingChange: payload.ratings[String(get().playerNumber)] ?? null
  });
  break;
```

### Lobby Manager Updates

The `LobbyManager` in `server/src/kfchess/lobby/manager.py` may need a method to retrieve lobby by game_id if not already available:

```python
async def get_lobby_by_game_id(self, game_id: str) -> Lobby | None:
    """Get lobby associated with a game."""
    # May need to track game_id -> lobby_code mapping
    pass
```

---

## Implementation Tasks

### Phase 1: Database & Core Rating System (COMPLETE)
1. [x] Create Alembic migration for:
   - New `ratings` JSONB schema with nested stats
   - Functional indexes for leaderboard queries
2. [x] Create `server/src/kfchess/game/elo.py` with:
   - ELO calculation functions
   - Belt thresholds and `get_belt()` function
   - `RatingChange` and `UserRatingStats` dataclasses
3. [x] Create `server/src/kfchess/services/rating_service.py` with:
   - `RatingService` class with transaction handling
   - Race condition protection via `SELECT FOR UPDATE`
4. [ ] Upload belt icons to S3

### Phase 2: Backend Integration (COMPLETE)
5. [x] Add `RatingUpdateMessage` to `ws/protocol.py`
6. [x] Add `_update_ratings()` and `_broadcast_rating_update()` to `ws/handler.py`
7. [x] Integrate rating updates into game loop (after `_save_replay()`)
8. [x] Add leaderboard API endpoints:
   - `GET /api/leaderboard`
   - `GET /api/leaderboard/me`
9. [x] Add user ratings to profile API response (via `UserRead` schema)

### Phase 3: Frontend Integration
10. [ ] Add `ratingChange` to game store
11. [ ] Handle `rating_update` WebSocket message
12. [ ] Add rating change display to game over overlay
13. [ ] Update profile page with ratings display and belt icons
14. [ ] Add belt display next to usernames in game UI

### Phase 4: Watch Page & Leaderboard
15. [ ] Create `/watch` route with tabbed layout
16. [ ] Implement Live Games tab (refactor existing lobbies)
17. [ ] Implement Replays tab (refactor from Replays.tsx)
18. [ ] Implement Leaderboard component with mode selector

### Phase 5: Testing
19. [ ] Unit tests for ELO calculations (2p and 4p)
20. [ ] Unit tests for belt thresholds
21. [ ] Integration tests for rating updates with mocked DB
22. [ ] Integration tests for race condition handling
23. [ ] E2E tests for leaderboard API
24. [ ] Frontend tests for rating display components

---

## Future Considerations

### Provisional Ratings
Consider implementing provisional ratings for new players:
- First 20 games use higher K-factor (K=40)
- Display "(provisional)" badge on leaderboard
- Provisional players not shown on main leaderboard

### Rating Decay
To keep leaderboard active, consider:
- Ratings decay 5 points/week after 2 weeks of inactivity
- Minimum decay threshold (don't decay below the floor)
- Show "inactive" badge on leaderboard for decaying players

### Matchmaking
Future ranked queue could use ratings for matchmaking:
- Match players within 200 rating points
- Expand range over time if no match found
- Separate queues for each rating mode

### Anti-Cheat
- Detect rating manipulation (intentional losing)
- Track win/loss patterns via replay analysis
- Require minimum 5 games for leaderboard eligibility (already implemented)
- Flag accounts with unusual win streaks or loss patterns

### Rating History (Future)
If detailed rating history is needed later, add a `rating_history` table to enable:
- Rating progression graphs on profile page
- Peak rating tracking
- Recent trend indicators

### Seasonal Ratings
Consider implementing seasons:
- Reset ratings periodically (e.g., quarterly)
- Archive previous season rankings
- Seasonal rewards based on peak rating
