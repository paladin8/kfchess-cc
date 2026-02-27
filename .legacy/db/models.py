import json


class User(object):

    def __init__(self, user_id, email, username, picture_url, ratings, join_time, last_online, current_game):
        self.user_id = user_id
        self.email = email
        self.username = username
        self.picture_url = picture_url
        self.ratings = ratings
        self.join_time = join_time
        self.last_online = last_online
        self.current_game = current_game

        # for flask-login
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    # for flask-login
    def get_id(self):
        return unicode(self.user_id)

    def to_json_obj(self, with_key=False):
        return {
            'userId': str(self.user_id),
            'email': self.email,
            'username': self.username,
            'pictureUrl': self.picture_url,
            'ratings': self.ratings,
            'joinTime': str(self.join_time),
            'lastOnline': self.last_online and str(self.last_online),
            'currentGame': {
                key: value
                for key, value in self.current_game.iteritems()
                if with_key or key != 'playerKey'
            } if self.current_game is not None else None,
        }

    def __str__(self):
        return json.dumps(self.to_json_obj())

    @staticmethod
    def from_row(row):
        return User(
            row.id,
            row.email,
            row.username,
            row.picture_url,
            row.ratings,
            row.join_time,
            row.last_online,
            row.current_game
        )


class UserGameHistory(object):

    def __init__(self, history_id, user_id, game_time, game_info):
        self.history_id = history_id
        self.user_id = user_id
        self.game_time = game_time
        self.game_info = game_info

    def to_json_obj(self):
        return {
            'historyId': self.history_id,
            'userId': str(self.user_id),
            'gameTime': str(self.game_time),
            'gameInfo': self.game_info,
        }

    @staticmethod
    def from_row(row):
        return UserGameHistory(row.id, row.user_id, row.game_time, row.game_info)


class ActiveGame(object):

    def __init__(self, active_id, server, game_id, game_info):
        self.active_id = active_id
        self.server = server
        self.game_id = game_id
        self.game_info = game_info

    def to_json_obj(self):
        return {
            'activeId': self.active_id,
            'server': self.server,
            'gameId': self.game_id,
            'gameInfo': self.game_info,
        }

    @staticmethod
    def from_row(row):
        return ActiveGame(row.id, row.server, row.game_id, row.game_info)


class GameHistory(object):

    def __init__(self, history_id, replay):
        self.history_id = history_id
        self.replay = replay

    def to_json_obj(self):
        return {
            'historyId': self.history_id,
            'replay': self.replay,
        }

    @staticmethod
    def from_row(row):
        return GameHistory(row.id, row.replay)


class CampaignProgress(object):

    def __init__(self, levels_completed, belts_completed):
        self.levels_completed = levels_completed
        self.belts_completed = belts_completed

    def to_json_obj(self):
        return {
            'levelsCompleted': self.levels_completed,
            'beltsCompleted': self.belts_completed,
        }

    @staticmethod
    def from_row(row):
        if row is None:
            return CampaignProgress({}, {})

        return CampaignProgress(
            row.progress.get('levelsCompleted', {}),
            row.progress.get('beltsCompleted', {}),
        )
