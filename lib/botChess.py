import time
from threading import Thread, Lock
import os

import requests
import json
import pprint
import chess
import re
import berserk

from lib.misc import print_debug

pp = pprint.PrettyPrinter()

class BotChess:

    UCI_PATTERN = re.compile("[a-h][1-8][a-h][1-8]")

    def __init__(self, config, mode='anarchy'):
        self.config = config
        self.mode = mode

        self.ongoing_games = {}
        self.lock_ongoing_games = Lock()

        self.game_move_votes = {}
        self.lock_game_move_votes = Lock()

        self.thread_games = []
        self.lock_thread_games = Lock()

        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')

        # Start threads
        self.start_thread(self.thread_update_ongoing_games)
        self.start_thread(self.thread_games_handler)

    def start_thread(self, thread_func, daemon=True, args=()):
        thread = Thread(target=thread_func, args=args)
        thread.daemon = daemon
        thread.start()
        return thread

    def thread_update_ongoing_games(self):
        while(True):
            self.update_ongoing_games()
            time.sleep(1)

    def thread_games_handler(self):
        while(True):
            with(self.lock_ongoing_games):
                for game_id in self.ongoing_games.keys():
                    if(game_id not in self.thread_games):
                        with(self.lock_thread_games):
                            self.thread_games.append(game_id)
                        self.start_thread(
                            self.thread_make_move_handler, args=(game_id, ))
            time.sleep(0.5)

    def get_account_info(self):
        return self.client.account.get()

    def thread_make_move_handler(self, game_id):
        while(True):
            time.sleep(0.5)

            with(self.lock_game_move_votes):
                if(game_id not in self.game_move_votes.keys()):
                    continue

                moves = list(self.game_move_votes[game_id].keys())
                if(len(moves) == 0):
                    continue

                if(self.mode == 'anarchy'):
                    move = moves[0]
                    ret = self.make_move(game_id, move)
                    if(ret):# remove all votes if succeeded
                        self.game_move_votes[game_id] = {}
                    else: # remove move if not succeeded
                        del self.game_move_votes[game_id][move]

            with(self.lock_ongoing_games):
                if(game_id not in self.ongoing_games.keys()):
                    break

        with(self.lock_thread_games):
            self.thread_games.remove(game_id)
        print_debug(f'Finished game {game_id}', 'DEBUG')

    def vote_for_move(self, game_id, move):
        with(self.lock_game_move_votes):
            if(not self.get_is_move_fmt_valid(move)):
                print_debug(f'Unable to vote for {move} in game {game_id}. ' +
                    'Invalid format.', 'DEBUG')
                return False

            # Parse from SAN to UCI if necessary
            if(not self.get_is_uci(move)):
                board = self.get_board_from_game(game_id)
                if(board is None):
                    print_debug(f'Unable to get board from {game_id}. ' + 
                        'Unable to make move', 'ERROR')
                try:
                    move = board.parse_san(move)
                except Exception as e:
                    print_debug(f'Unable to vote for {move} in game {game_id}. ' +
                        f'Exception: {e}', 'DEBUG')
                    return False

            if(game_id not in self.game_move_votes.keys()):
                self.game_move_votes[game_id] = dict()
            if(move not in self.game_move_votes[game_id].keys()):
                self.game_move_votes[game_id][move] = 0
            self.game_move_votes[game_id][move] += 1
        
        print_debug(f'Voted for {move} in game {game_id}', 'DEBUG')
        return True

    def start_session(self):
        try:
            self.session = berserk.TokenSession(self.config['token'])
            self.client = berserk.Client(self.session)
            return True
        except Exception as e:
            print_debug(f'Unable to stablish session\nException: {e}',
                        'EXCEPTION')
            return None

    def get_move_from_msg(self, message, uci=False):
        # messages must be as "e4" "Nc3", not "move Nc4" "e7 is a great move"
        if(" " in message):
            return None

        if(uci):
            command = re.findall(r'[a-h][1-8][a-h][1-8]', message)
        else:
            command = re.findall(r'[a-zA-Z0-9#+!?\-]+' , message)
        if(len(command) == 0):
            return None

        move = command[0].split(" ")[1]

        return move

    def make_move(self, game_id, move):
        try:
            #Must recieve an UCI
            self.client.bots.make_move(game_id, move)
            return True
        except Exception as e:
            print_debug(str(e), 'EXCEPTION')
            return False

    def get_is_move_fmt_valid(self, move):
        if(not self.get_is_uci(move)):
            # PROBLEMS WITH CASTLING (0-0-0, 0-0)
            if(chess.SAN_REGEX.match(move) is None):
                return False
        return True

    def update_ongoing_games(self):
        try:
            with self.lock_ongoing_games:
                self.ongoing_games = {}
                games = self.client.games.get_ongoing()
                for game in games:
                    self.ongoing_games[game['gameId']] = game

        except Exception as e:
            print_debug(f'Unable to get ongoing games\nException: {e}',
                        'EXCEPTION')

    def create_challenge(self, username, rated=True, clock_min=3, clock_incr_sec=2):
        try:
            self.client.challenges.create(
                username, rated, clock_limit=clock_min,
                clock_increment=clock_incr_sec)
        except Exception as e:
            print_debug(f'Unable to create challenge. Exception: {e}', 'EXCEPTION')

    def seek_game(self, rated=True, clock_min=3, clock_incr_sec=2):
        try:
            r = requests.post("http://www.lichess.org/api/board/seek", 
                params={'rated': str(rated), 
                    'time': clock_min, 
                    'incremet': clock_incr_sec},
                headers={'Authorization': 'Bearer ' + self.config['token']})
            print(r.text)
        except Exception as e:
            print_debug(f'Unable to seek game. Exception: {e}', 'EXCEPTION')

    def is_my_turn(self, game_id):
        if game_id in self.ongoing_games.keys():
            return self.ongoing_games[game_id]['isMyTurn']

    def get_ongoing_game_ids(self):
        with self.lock_ongoing_games:
            return list(self.ongoing_games.keys())
    
    def get_board_from_game(self, game_id):
        with(self.lock_ongoing_games):
            if(game_id in self.ongoing_games.keys()):
                game = self.ongoing_games[game_id]
                board = chess.Board(game['fen'])
                board.turn = game['color'] == 'white'
                return board
        return None
    
    def get_is_uci(self, move):
        return BotChess.UCI_PATTERN.match(move)
