import datetime
import json
import random
import string
import sys
import time
import traceback
import uuid

import eventlet
from flask import Blueprint, request
from flask_login import current_user

import context
from db import db_service
from lib import ai, campaign, elo
from lib.board import Board
from lib.game import Game, GameState, Speed
from lib.replay import Replay
from web import game_states


TICK_PERIOD = 0.1
DEFAULT_RATING = 1200

game = Blueprint('game', __name__)

socketio = None  # populated by initialize()


def generate_game_id():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for i in xrange(6))


@game.route('/api/game/new', methods=['POST'])
def new():
    data = json.loads(request.data)
    speed = data['speed']
    bots = data.get('bots', {})
    bots = {int(player): ai.get_bot(difficulty) for player, difficulty in bots.iteritems()}
    username = data.get('username')
    print 'new game', data

    # generate game ID and player keys
    game_id = generate_game_id()
    player_keys = {i: str(uuid.uuid4()) for i in xrange(1, 3) if i not in bots}

    # if logged in, add current user to game
    players = {i: 'b:%s' % bot.difficulty for i, bot in bots.iteritems()}
    if current_user.is_authenticated:
        players[1] = 'u:%s' % current_user.user_id

        user = db_service.get_user_by_id(current_user.user_id)
        if user.current_game:
            return json.dumps({
                'success': False,
                'message': 'User already in game.',
            })

        db_service.update_user_current_game(current_user.user_id, game_id, player_keys[1])

    # check opponent
    if username is not None:
        user = db_service.get_user_by_username(username)
        if user is None:
            return json.dumps({
                'success': False,
                'message': 'User to invite does not exist.',
            })

        if user.current_game is not None:
            return json.dumps({
                'success': False,
                'message': 'User to invite is already in a game.',
            })

        players[2] = 'u:%s' % user.user_id
        db_service.update_user_current_game(user.user_id, game_id, player_keys[2])

        socketio.emit('invite', '', room=user.user_id)

    for i in xrange(1, 3):
        if i not in players:
            players[i] = 'o'

    # create game and add to game states
    game = Game(Speed(speed), players)
    for player in bots:
        game.mark_ready(player)

    game_states[game_id] = GameState(game_id, game, player_keys, bots)

    return json.dumps({
        'success': True,
        'gameId': game_id,
        'playerKeys': player_keys,
    })


@game.route('/api/game/check', methods=['GET'])
def check():
    game_id = request.args['gameId']
    print 'check', request.args

    if not current_user.is_authenticated:
        return json.dumps({
            'success': False,
            'message': 'User is not logged in.'
        })

    if game_id in game_states:
        return json.dumps({
            'success': True,
        })

    db_service.update_user_current_game(current_user.user_id, None, None)
    user = db_service.get_user_by_id(current_user.user_id)

    return json.dumps({
        'success': False,
        'user': user.to_json_obj(),
    })


@game.route('/api/game/invite', methods=['POST'])
def invite():
    data = json.loads(request.data)
    game_id = data['gameId']
    player = data['player']
    username = data['username']
    print 'invite', data

    if not current_user.is_authenticated:
        return json.dumps({
            'success': False,
            'message': 'User is not logged in.',
        })

    if game_id not in game_states:
        return json.dumps({
            'success': False,
            'message': 'Game does not exist.',
        })

    game_state = game_states[game_id]
    game = game_state.game
    if game.players[player] != 'o':
        return json.dumps({
            'success': False,
            'message': 'Player position is already filled.',
        })

    if ('u:%s' % current_user.user_id) not in game.players.values():
        return json.dumps({
            'success': False,
            'message': 'User is not in the game.',
        })

    user = db_service.get_user_by_username(username)
    if user is None:
        return json.dumps({
            'success': False,
            'message': 'User to invite does not exist.',
        })

    if user.current_game is not None:
        return json.dumps({
            'success': False,
            'message': 'User to invite is already in a game.',
        })

    # generate a new player key (for security)
    new_key = str(uuid.uuid4())
    game_state.player_keys[player] = new_key
    game.players[player] = 'u:%s' % user.user_id
    db_service.update_user_current_game(user.user_id, game_id, new_key)

    socketio.emit('invite', '', room=str(user.user_id))

    socketio.emit('inviteack', {
        'game': game.to_json_obj(),
    }, room=game_id, json=True)

    return json.dumps({
        'success': True,
    })


@game.route('/api/game/startreplay', methods=['POST'])
def replay_start():
    data = json.loads(request.data)
    history_id = data['historyId']
    print 'replay start', data

    game_history = db_service.get_game_history(history_id)
    if game_history is None:
        return json.dumps({
            'success': False,
            'message': 'Replay does not exist.',
        })

    # create game and add to game states
    replay = Replay.from_json_obj(game_history.replay)
    if replay.players[2].startswith('c'):
        level = int(replay.players[2][2:])
        campaign_level = campaign.get_level(level)
        game = Game(
            Speed(replay.speed), replay.players,
            board=Board.from_str(campaign_level.board),
            is_campaign=True
        )
    else:
        game = Game(Speed(replay.speed), replay.players)
    for player in replay.players:
        game.mark_ready(player)

    game_id = generate_game_id()
    game_states[game_id] = GameState(game_id, game, {}, {}, replay)

    return json.dumps({
        'success': True,
        'gameId': game_id,
    })


@game.route('/api/game/startcampaign', methods=['POST'])
def campaign_start():
    data = json.loads(request.data)
    level = data['level']
    print 'campaign start', data

    if not current_user.is_authenticated:
        return json.dumps({
            'success': False,
            'message': 'User is not logged in.',
        })

    # check if user is already in game
    user_id = current_user.user_id
    user = db_service.get_user_by_id(user_id)
    if user.current_game:
        game_id = user.current_game['gameId']
        if game_id in game_states:
            game_state = game_states[game_id]
            if not game_state.game.started or game_state.game.finished:
                del game_states[game_id]
            else:
                return json.dumps({
                    'success': False,
                    'message': 'User already in game.',
                })

    # check that user has access to this level
    progress = db_service.get_campaign_progress(user_id)
    belt = level / 8 + 1
    if belt > 1 and not progress.belts_completed[str(belt - 1)]:
        return json.dumps({
            'success': False,
            'message': 'User does not have access to this level.',
        })

    # create game and add to game states
    campaign_level = campaign.get_level(level)
    players = {1: 'u:%s' % user_id, 2: 'c:%s' % level}
    game = Game(
        Speed(campaign_level.speed), players,
        board=Board.from_str(campaign_level.board),
        is_campaign=True
    )
    game.mark_ready(2)

    game_id = generate_game_id()
    player_keys = {1: str(uuid.uuid4())}
    bots = {2: ai.get_bot('campaign')}
    game_states[game_id] = GameState(game_id, game, player_keys, bots, level=level)

    # update user current game
    db_service.update_user_current_game(user_id, game_id, player_keys[1])

    return json.dumps({
        'success': True,
        'gameId': game_id,
        'playerKeys': player_keys,
    })


def initialize(init_socketio):
    global socketio
    socketio = init_socketio

    # clear all active games on server init
    db_service.clear_active_games(context.SERVER)

    # infinite loop that ticks all active games
    def tick():
        start = time.time()
        tick_number = 0
        while True:
            try:
                # adjust sleep amount to avoid drift
                tick_number += 1
                next_tick = start + TICK_PERIOD * tick_number
                sleep_amount = next_tick - time.time()
                if sleep_amount > 0:
                    eventlet.sleep(sleep_amount)

                if tick_number % 600 == 0:
                    # log extra info and flush every minute
                    print 'game tick', tick_number
                    sys.stdout.flush()

                randnum = random.randint(0, 9999)

                current_time = time.time()
                expired_games = set()
                for game_id, game_state in game_states.items():
                    game = game_state.game

                    if tick_number % 600 == 0:
                        # log extra info every minute
                        print 'game status', game_id, game.current_tick, game.players, game.finished

                    # keep games around for 10 min
                    if current_time - game.last_tick_time > 60 * 10:
                        expired_games.add(game_id)
                        continue

                    if not game.started or game.finished:
                        continue

                    moved = False

                    try:
                        # add to active games
                        if game.current_tick == 0 and game_state.replay is None:
                            db_service.add_active_game(context.SERVER, game_id, {
                                'players': game.players,
                                'speed': game.speed.value,
                                'startTime': str(datetime.datetime.utcnow()),
                            })
                    except:
                        traceback.print_exc()

                    try:
                        # check for bot moves (after game has been running for 1s)
                        if game.current_tick >= 10:
                            for player, bot in game_state.bots.iteritems():
                                move = bot.get_move(game, player, randnum)
                                if move:
                                    piece, row, col = move
                                    game.move(piece.id, player, row, col)
                                    moved = True
                    except:
                        traceback.print_exc()

                    try:
                        # check for replay moves
                        if game_state.replay:
                            for replay_move in game_state.replay.moves_by_tick[game.current_tick]:
                                game.move(replay_move.piece_id, replay_move.player, replay_move.row, replay_move.col)
                                moved = True
                    except:
                        traceback.print_exc()

                    try:
                        # tick game; if there are updates (or a bot/replay move), emit to room
                        status, updates = game.tick()
                        if status != 0 or updates or moved:
                            socketio.emit('update', {
                                'game': game.to_json_obj(),
                                'updates': updates,
                            }, room=game_id, json=True)
                    except:
                        traceback.print_exc()

                    try:
                        # remove from active games and add to history
                        if game.finished and game_state.replay is None:
                            db_service.remove_active_game(context.SERVER, game_id)

                            history_id = db_service.add_game_history(Replay.from_game(game))
                            user_id1, user_id2 = None, None
                            for player, value in game.players.iteritems():
                                if not value.startswith('u:'):
                                    continue

                                user_id = int(value[2:])
                                if player == 1:
                                    user_id1 = user_id
                                elif player == 2:
                                    user_id2 = user_id

                                opponents = [v for k, v in game.players.iteritems() if k != player]
                                db_service.add_user_game_history(user_id, game.start_time, {
                                    'speed': game.speed.value,
                                    'player': player,
                                    'winner': game.finished,
                                    'historyId': history_id,
                                    'ticks': game.current_tick,
                                    'opponents': opponents,
                                })

                            # update elo if two logged in users
                            if user_id1 and user_id2:
                                user1 = db_service.get_user_by_id(user_id1)
                                user2 = db_service.get_user_by_id(user_id2)

                                r1 = user1.ratings.get(game.speed.value, DEFAULT_RATING)
                                r2 = user2.ratings.get(game.speed.value, DEFAULT_RATING)
                                nr1, nr2 = elo.update_ratings(r1, r2, game.finished)

                                user1.ratings[game.speed.value] = nr1
                                user2.ratings[game.speed.value] = nr2
                                db_service.update_user_ratings(user_id1, user1.ratings)
                                db_service.update_user_ratings(user_id2, user2.ratings)

                                data = {
                                    '1': {
                                        'oldRating': r1,
                                        'newRating': nr1,
                                    },
                                    '2': {
                                        'oldRating': r2,
                                        'newRating': nr2,
                                    },
                                }

                                print 'new ratings', game_id, data
                                socketio.emit('newratings', data, room=game_id, json=True)

                            # update campaign progress
                            if game_state.level is not None and game.finished == 1:
                                progress = db_service.get_campaign_progress(user_id1)
                                progress.levels_completed[str(game_state.level)] = True

                                # check if belt is completed
                                belt = game_state.level / 8 + 1
                                belt_levels = xrange(8 * belt - 8, 8 * belt)
                                if (
                                    not progress.belts_completed.get(str(belt)) and
                                    all(progress.levels_completed.get(str(level)) for level in belt_levels)
                                ):
                                    progress.belts_completed[str(belt)] = True

                                    data = {
                                        'belt': belt,
                                    }

                                    print 'new belt', game_id, data
                                    socketio.emit('newbelt', data, room=game_id, json=True)

                                db_service.update_campaign_progress(user_id1, progress)
                    except:
                        traceback.print_exc()

                # remove expired games
                for game_id in expired_games:
                    try:
                        print 'expiring', game_id
                        db_service.remove_active_game(context.SERVER, game_id)

                        game = game_states[game_id].game
                        for player, value in game.players.iteritems():
                            if not value.startswith('u:'):
                                continue

                            user_id = int(value[2:])
                            if player == 1:
                                user_id1 = user_id
                            elif player == 2:
                                user_id2 = user_id

                        if user_id1:
                            db_service.update_user_current_game(user_id1, None, None)
                        if user_id2:
                            db_service.update_user_current_game(user_id2, None, None)

                        del game_states[game_id]
                    except:
                        traceback.print_exc()
            except:
                traceback.print_exc()


    eventlet.spawn(tick)
