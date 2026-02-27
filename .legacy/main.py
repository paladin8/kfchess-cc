import datetime
import json

import eventlet
from flask import Flask, abort, request, session
from flask_login import LoginManager
from flask_socketio import SocketIO, join_room, leave_room, emit

import config
import context
from db import db_service
from lib import ai, campaign
from lib.board import Board
from lib.game import Game
from web import game_states, game as game_handlers
from web.game import game as game_blueprint
from web.live import live as live_blueprint
from web.user import user as user_blueprint


eventlet.monkey_patch()

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config.update(SESSION_COOKIE_SAMESITE=None, SESSION_COOKIE_SECURE=True)

app.register_blueprint(game_blueprint)
app.register_blueprint(live_blueprint)
app.register_blueprint(user_blueprint)
socketio = SocketIO(app)

login_manager = LoginManager()
login_manager.init_app(app)

game_handlers.initialize(socketio)


@login_manager.user_loader
def load_user(user_id):
    return db_service.get_user_by_id(user_id)


@app.before_request
def csrf_protect():
    if request.method == 'POST':
        token = session.get('_csrf_token')
        if not token or token != request.headers.get('X-CSRF-Token'):
            abort(403)


@app.route('/', methods=['GET'])
def index():
    return 'Kung Fu Chess'


# socket.io functions


def _emit_online_users(requesting_user_id):
    ten_minutes_ago = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    online_users = db_service.get_users_online_since(ten_minutes_ago)

    emit('online', {
        'users': {
            user_id: user.to_json_obj()
            for user_id, user in online_users.iteritems()
            if user_id != requesting_user_id
        },
    }, json=True)


@socketio.on('listen')
def listen(data):
    data = json.loads(data)
    user_id = int(data['userId']) if data['userId'] is not None else None
    print 'listen', data

    if user_id:
        db_service.update_user_last_online(user_id)
        join_room(user_id)

    _emit_online_users(user_id)


@socketio.on('uping')
def uping(data):
    data = json.loads(data)
    user_id = int(data['userId']) if data['userId'] is not None else None
    print 'uping', data

    if user_id:
        user = db_service.get_user_by_id(user_id)
        if user:
            # check if current game is still valid
            game_id = user.current_game and user.current_game['gameId']
            if game_id and game_id not in game_states:
                db_service.update_user_current_game(user_id, None, None)

            db_service.update_user_last_online(user_id)

    _emit_online_users(user_id)


def get_auth_player(game_state, player_key):
    if player_key is not None:
        for player, key in game_state.player_keys.iteritems():
            if player_key == key:
                return player

    return 0  # no key or no match means player 0 = spectator


@socketio.on('join')
def join(data):
    data = json.loads(data)
    game_id = data['gameId']
    player_key = data.get('playerKey')
    print 'join', data

    if game_id not in game_states:
        emit('notfound')
        return

    game_state = game_states[game_id]
    auth_player = get_auth_player(game_state, player_key)

    join_room(game_id)
    emit('joinack', {
        'game': game_state.game.to_json_obj(),
        'player': auth_player,
        'ticks': game_state.replay.ticks if game_state.replay is not None else None,
        'level': game_state.level,
    }, json=True)


@socketio.on('cancel')
def cancel(data):
    data = json.loads(data)
    game_id = data['gameId']
    player_key = data.get('playerKey')
    print 'cancel', data

    if game_id not in game_states:
        emit('cancelack', {}, json=True)
        return

    game_state = game_states[game_id]
    auth_player = get_auth_player(game_state, player_key)

    # only authenticated players can cancel
    game = game_state.game
    if auth_player and (not game.started or game.finished):
        for player, value in game.players.iteritems():
            if value.startswith('u'):
                user_id = int(value[2:])
                db_service.update_user_current_game(user_id, None, None)

        del game_states[game_id]

        emit('cancelack', {}, room=game_id, json=True)


@socketio.on('ready')
def ready(data):
    data = json.loads(data)
    game_id = data['gameId']
    player_key = data['playerKey']
    print 'ready', data

    if game_id not in game_states:
        emit('notfound')
        return

    game_state = game_states[game_id]
    auth_player = get_auth_player(game_state, player_key)

    # only authenticated players can ready
    if auth_player:
        game_state.game.mark_ready(auth_player)

        emit('readyack', {
            'game': game_state.game.to_json_obj(),
        }, room=game_id, json=True)


@socketio.on('difficulty')
def difficulty(data):
    data = json.loads(data)
    game_id = data['gameId']
    player_key = data['playerKey']
    player = data['player']
    difficulty = data['difficulty']
    print 'difficulty', data

    if game_id not in game_states:
        emit('notfound')
        return

    game_state = game_states[game_id]
    auth_player = get_auth_player(game_state, player_key)

    # only authenticated players can change difficulty
    if auth_player is not None:
        if not game_state.game.players[player].startswith('b'):
            return

        game_state.bots[player] = ai.get_bot(difficulty)
        game_state.game.players[player] = 'b:%s' % difficulty

        emit('difficultyack', {
            'game': game_state.game.to_json_obj(),
        }, room=game_id, json=True)


@socketio.on('move')
def move(data):
    data = json.loads(data)
    game_id = data['gameId']
    player_key = data['playerKey']
    piece_id = data['pieceId']
    to_row = data['toRow']
    to_col = data['toCol']
    print 'move', data

    if game_id not in game_states:
        emit('notfound')
        return

    game_state = game_states[game_id]
    auth_player = get_auth_player(game_state, player_key)

    # only authenticated players can make moves
    if auth_player is not None:
        move = game_state.game.move(piece_id, auth_player, to_row, to_col)
        emit('moveack', {
            'game': game_state.game.to_json_obj(),
            'success': move is not None,
        }, room=game_id, json=True)


@socketio.on('reset')
def reset(data):
    data = json.loads(data)
    game_id = data['gameId']
    player_key = data['playerKey']
    print 'reset', data

    if game_id not in game_states:
        emit('notfound')
        return

    game_state = game_states[game_id]
    auth_player = get_auth_player(game_state, player_key)

    # can't reset an in-progress multiplayer game
    if game_state.level is None and not game_state.game.finished:
        return

    # only authenticated players can reset game
    if auth_player is not None:
        db_service.remove_active_game(context.SERVER, game_id)

        board = None
        if game_state.level is not None:
            campaign_level = campaign.get_level(game_state.level)
            board = Board.from_str(campaign_level.board)

        old_game = game_state.game
        game = Game(
            old_game.speed, old_game.players,
            num_players=old_game.num_players,
            board=board,
            is_campaign=old_game.is_campaign,
            debug=old_game.debug
        )
        for player in game_state.bots:
            game.mark_ready(player)
        game_state.game = game

        emit('resetack', {
            'game': game.to_json_obj(),
        }, room=game_id, json=True)


@socketio.on('leave')
def leave(data):
    data = json.loads(data)
    game_id = data['gameId']
    print 'leave', data

    leave_room(game_id)
