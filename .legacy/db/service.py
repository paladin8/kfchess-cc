import datetime
import json

from sqlalchemy.engine import create_engine

from db.models import ActiveGame, CampaignProgress, GameHistory, User, UserGameHistory


class DbService(object):

    def __init__(self, host):
        self.engine = create_engine(host)

    # user functions

    def get_user_by_id(self, user_id):
        with self.engine.connect() as conn:
            row = conn.execute(
                "SELECT * "
                "FROM users "
                "WHERE id = %s",
                int(user_id)
            ).fetchone()
            return row and User.from_row(row)

    def get_users_by_id(self, user_ids):
        with self.engine.connect() as conn:
            rows = conn.execute(
                "SELECT * "
                "FROM users "
                "WHERE id IN %s",
                ((tuple(user_id for user_id in user_ids),),)
            ).fetchall()
            return {row.id: User.from_row(row) for row in rows}

    def get_user_by_email(self, email):
        with self.engine.connect() as conn:
            row = conn.execute(
                "SELECT * "
                "FROM users "
                "WHERE email = %s",
                email
            ).fetchone()
            return row and User.from_row(row)

    def get_user_by_username(self, username):
        with self.engine.connect() as conn:
            row = conn.execute(
                "SELECT * "
                "FROM users "
                "WHERE username = %s",
                username
            ).fetchone()
            return row and User.from_row(row)

    def get_users_online_since(self, time):
        with self.engine.connect() as conn:
            rows = conn.execute(
                "SELECT * "
                "FROM users "
                "WHERE last_online IS NOT NULL AND last_online > %s",
                time
            ).fetchall()
            return {row.id: User.from_row(row) for row in rows}

    def create_user(self, email, username, picture_url, ratings):
        with self.engine.connect() as conn:
            conn.execute(
                "INSERT INTO users (email, username, picture_url, ratings, join_time, last_online, current_game) "
                "VALUES (%s, %s, %s, %s, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC', %s)",
                email, username, picture_url, json.dumps(ratings), None
            )

        return self.get_user_by_email(email)

    def update_user(self, user_id, username, picture_url):
        with self.engine.connect() as conn:
            conn.execute(
                "UPDATE users "
                "SET username = %s, picture_url = %s "
                "WHERE id = %s",
                username, picture_url, user_id
            )

    def update_user_ratings(self, user_id, ratings):
        with self.engine.connect() as conn:
            conn.execute(
                "UPDATE users "
                "SET ratings = %s "
                "WHERE id = %s",
                json.dumps(ratings), user_id
            )

    def update_user_last_online(self, user_id):
        with self.engine.connect() as conn:
            conn.execute(
                "UPDATE users "
                "SET last_online = %s "
                "WHERE id = %s",
                datetime.datetime.utcnow(), user_id
            )

    def update_user_current_game(self, user_id, game_id, player_key):
        current_game = json.dumps({'gameId': game_id, 'playerKey': player_key}) if game_id is not None else None
        with self.engine.connect() as conn:
            conn.execute(
                "UPDATE users "
                "SET current_game = %s "
                "WHERE id = %s",
                current_game, user_id
            )

    # active games

    def clear_active_games(self, server):
        with self.engine.connect() as conn:
            conn.execute(
                "DELETE FROM active_games "
                "WHERE server = %s",
                server
            )

    def add_active_game(self, server, game_id, game_info):
        with self.engine.connect() as conn:
            conn.execute(
                "INSERT INTO active_games (server, game_id, game_info) "
                "VALUES (%s, %s, %s)",
                server, game_id, json.dumps(game_info)
            )

    def remove_active_game(self, server, game_id):
        with self.engine.connect() as conn:
            conn.execute(
                "DELETE FROM active_games "
                "WHERE server = %s AND game_id = %s",
                server, game_id
            )

    def get_all_active_games(self):
        with self.engine.connect() as conn:
            rows = conn.execute(
                "SELECT * "
                "FROM active_games"
            ).fetchall()
            return [ActiveGame.from_row(row) for row in rows]

    # user game history

    def add_user_game_history(self, user_id, game_time, game_info):
        with self.engine.connect() as conn:
            conn.execute(
                "INSERT INTO user_game_history (user_id, game_time, game_info) "
                "VALUES (%s, %s, %s)",
                user_id, game_time, json.dumps(game_info)
            )

    def get_user_game_history(self, user_id, offset, count):
        with self.engine.connect() as conn:
            rows = conn.execute(
                "SELECT * "
                "FROM user_game_history "
                "WHERE user_id = %s "
                "ORDER BY game_time DESC "
                "OFFSET %s LIMIT %s",
                user_id, offset, count
            ).fetchall()
            return [UserGameHistory.from_row(row) for row in rows]

    # game history

    def add_game_history(self, replay):
        with self.engine.connect() as conn:
            row = conn.execute(
                "INSERT INTO game_history (replay) "
                "VALUES (%s) "
                "RETURNING id",
                json.dumps(replay.to_json_obj())
            ).fetchone()
            return row and row.id

    def get_game_history(self, history_id):
        with self.engine.connect() as conn:
            row = conn.execute(
                "SELECT * "
                "FROM game_history "
                "WHERE id = %s",
                history_id
            ).fetchone()
            return row and GameHistory.from_row(row)

    # campaign progress

    def get_campaign_progress(self, user_id):
        with self.engine.connect() as conn:
            row = conn.execute(
                "SELECT * "
                "FROM campaign_progress "
                "WHERE user_id = %s",
                user_id
            ).fetchone()
            return CampaignProgress.from_row(row)

    def update_campaign_progress(self, user_id, progress):
        with self.engine.connect() as conn:
            conn.execute(
                "INSERT INTO campaign_progress (user_id, progress) "
                "VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE "
                "SET progress = excluded.progress",
                user_id, json.dumps(progress.to_json_obj())
            )
