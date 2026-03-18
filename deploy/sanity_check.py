# /// script
# requires-python = ">=3.12"
# dependencies = ["websockets>=14.0", "httpx>=0.28.0"]
# ///
"""Post-deploy sanity check: play a partial game vs AI on the live site.

Exercises the full user flow: create lobby → start game → make a move →
verify AI responds → resign. Uses guest identity, same as the UI.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid

import httpx
import websockets


async def sanity_check(base_url: str, timeout: float = 20.0) -> None:
    """Create a game via lobby, make a move, verify AI responds, resign."""
    ws_scheme = "wss" if base_url.startswith("https") else "ws"
    ws_base = f"{ws_scheme}://{base_url.split('://')[1]}"

    start = time.monotonic()

    def elapsed() -> str:
        return f"{time.monotonic() - start:.1f}s"

    async def recv_ws(ws, expected_type: str | None = None) -> dict:
        """Receive and parse a JSON message, optionally filtering by type."""
        deadline = start + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for {expected_type or 'message'}"
                )
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            msg = json.loads(raw)
            if expected_type is None or msg.get("type") == expected_type:
                return msg

    guest_id = f"sanity-{uuid.uuid4().hex[:8]}"

    # 1. Create lobby with AI opponent (as guest, same as UI)
    print(f"[{elapsed()}] Creating lobby vs novice AI (guest: {guest_id})...")
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        resp = await client.post(
            "/api/lobbies",
            json={
                "settings": {
                    "isPublic": False,
                    "speed": "standard",
                    "playerCount": 2,
                },
                "addAi": True,
                "aiType": "bot:novice",
                "guestId": guest_id,
            },
        )
        resp.raise_for_status()
        lobby_data = resp.json()

    lobby_code = lobby_data["code"]
    lobby_player_key = lobby_data["playerKey"]
    print(f"[{elapsed()}] Lobby created: {lobby_code}")

    # 2. Connect to lobby WebSocket and start the game
    lobby_ws_url = f"{ws_base}/ws/lobby/{lobby_code}?player_key={lobby_player_key}"
    print(f"[{elapsed()}] Connecting to lobby WebSocket...")

    async with websockets.connect(lobby_ws_url) as lobby_ws:
        # Receive initial lobby state
        await recv_ws(lobby_ws, "lobby_state")
        print(f"[{elapsed()}] Got lobby state")

        # Start game (host is auto-readied, AI is always ready)
        await lobby_ws.send(json.dumps({"type": "start_game"}))

        # Wait for game_starting with our game credentials
        game_msg = await recv_ws(lobby_ws, "game_starting")
        game_id = game_msg["gameId"]
        game_player_key = game_msg["playerKey"]
        print(f"[{elapsed()}] Game starting: {game_id}")

    # 3. Connect to game WebSocket (handle 4302 multi-server redirect)
    game_ws_url = f"{ws_base}/ws/game/{game_id}?player_key={game_player_key}"
    print(f"[{elapsed()}] Connecting to game WebSocket...")

    try:
        ws = await websockets.connect(game_ws_url)
        first_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
    except websockets.exceptions.ConnectionClosedError as e:
        if e.rcvd and e.rcvd.code == 4302:
            server = e.rcvd.reason
            print(f"[{elapsed()}] Redirected to {server}")
            game_ws_url = f"{ws_base}/ws/game/{game_id}?player_key={game_player_key}&server={server}"
            ws = await websockets.connect(game_ws_url)
            first_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        else:
            raise

    try:
        # 4. Join game
        joined = json.loads(first_raw)
        if joined.get("type") != "joined":
            raise RuntimeError(f"Expected 'joined', got {joined}")
        player_num = joined["player_number"]
        print(f"[{elapsed()}] Joined as player {player_num}")

        state = await recv_ws(ws, "state")
        pieces = state["pieces"]
        print(f"[{elapsed()}] Got initial state ({len(pieces)} pieces)")

        # 5. Wait through countdown until game is playable
        # Lobby games start the game loop immediately, so we get countdown
        # messages followed by game_started.
        while True:
            msg = await recv_ws(ws)
            if msg.get("type") == "game_started":
                break
            elif msg.get("type") == "countdown":
                print(f"[{elapsed()}] Countdown: {msg['seconds']}...")
        print(f"[{elapsed()}] Game started!")

        # 6. Find a pawn to move (player 1 pawn at row 6 → row 4)
        pawn = None
        for p in pieces:
            if (
                p["player"] == player_num
                and p["type"] == "P"
                and p["row"] == 6.0
            ):
                pawn = p
                break

        if pawn is None:
            raise RuntimeError("Could not find a pawn to move")

        piece_id = pawn["id"]
        to_row, to_col = 4, int(pawn["col"])
        print(f"[{elapsed()}] Moving {piece_id} to ({to_row}, {to_col})...")
        await ws.send(
            json.dumps(
                {
                    "type": "move",
                    "piece_id": piece_id,
                    "to_row": to_row,
                    "to_col": to_col,
                }
            )
        )

        # 7. Wait for state update confirming our move
        while True:
            update = await recv_ws(ws, "state")
            if any(
                m["piece_id"] == piece_id
                for m in update.get("active_moves", [])
            ):
                print(f"[{elapsed()}] Move confirmed!")
                break

        # 8. Wait for AI to make a move
        while True:
            update = await recv_ws(ws, "state")
            ai_moves = [
                m
                for m in update.get("active_moves", [])
                if m["piece_id"] != piece_id
            ]
            if ai_moves:
                print(f"[{elapsed()}] AI moved: {ai_moves[0]['piece_id']}")
                break

        # 9. Resign to clean up the game
        print(f"[{elapsed()}] Resigning...")
        await ws.send(json.dumps({"type": "resign"}))
        game_over = await recv_ws(ws, "game_over")
        print(f"[{elapsed()}] Game over (winner: player {game_over['winner']})")
    finally:
        await ws.close()

    total = time.monotonic() - start
    print(f"\nSanity check PASSED in {total:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-deploy sanity check")
    parser.add_argument(
        "url",
        nargs="?",
        default="https://kfchess.com",
        help="Base URL (default: https://kfchess.com)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Timeout in seconds (default: 20)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(sanity_check(args.url, args.timeout))
    except (TimeoutError, httpx.HTTPStatusError, RuntimeError) as e:
        print(f"\nSanity check FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
