import time
from threading import Thread, Lock

import json
import pprint
import chess
import re
import berserk

from lib.misc import print_debug

class BotChess:

    pp = pprint.PrettyPrinter()

    def __init__(self, config):
        self.config = config
        
        self.ongoing_games = None
        self.lock_ongoing_games = Lock()

        self.game_states = {}
        self.game_move_votes = {}

        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')

        self.board = chess.Board()
        self.update_ongoing_games()

    def thread_update_ongoing_games(self):
        while(True):
            time.sleep(5)
            self.update_ongoing_games()

    def thread_stream_game_states(self):
        while(True):
            for game_id in self.get_ongoing_games_ids():
                if(game_id not in self.game_states.keys()):
                    self.stream_game_state(game_id)

    def vote_for_move(self, game_id, move):
        if(game_id not in self.game_move_votes.keys()):
            self.game_move_votes[game_id] = dict()
        if(move not in self.game_move_votes[game_id].keys()):
            self.game_move_votes[game_id][move] = 0
        self.game_move_votes[game_id][move] += 1
        print_debug(f'Voted for {move} in game {game_id}', 'DEBUG')

    def start_session(self):
        try:
            self.session = berserk.TokenSession(self.config['token'])
            self.client = berserk.Client(self.session)
            return True
        except Exception as e:
            print_debug('Unable to stablish session\nException: {}'.format(e),
                        'EXCEPTION')
            return None

    def get_move_from_msg(self, message):
        command = re.findall(r'!move [a-zA-Z0-9#\-+!?]+' , message)
        if(len(command) == 0):
            return None

        move = command[0].split(" ")[1]

        if(re.match(chess.SAN_REGEX, move) is not None):
            return move
        return None

    def make_move(self, game_id, move):
        try:
            self.client.bots.make_move(game_id, move)
        except Exception as e:
            print_debug(str(e), 'EXCEPTION')

    def get_is_move_valid(self, move):
        # board.legal_moves prints <LegalMoveGenerator at 0x7ff666656908 (Nh3, ...)>
        return move in str(self.board.legal_moves).split("(")[-1].split(")")[0]

    def stream_game_state(self, game_id):
        # USE AS THREAD
        try:
            self.game_states[game_id]['lock'] = Lock()
            for event in self.client.bots.stream_game_state(game_id):
                with self.game_states[game_id]['lock']:
                    self.game_states[game_id]['game_state'] = event
            with self.game_states[game_id]['lock']:
                del self.game_states[game_id]
            return True
        except Exception as e:
            if(game_id in self.game_states.keys()):
                del self.game_states[game_id]
            print_debug(str(e), 'EXCEPTION')
            return None

    def update_ongoing_games(self):
        try:
            with self.lock_ongoing_games:
                self.ongoing_games = self.client.games.get_ongoing()
        except Exception as e:
            print_debug('Unable to get ongoing games\nException: {}'.format(e),
                        'EXCEPTION')

    def get_ongoing_games_ids(self):
        with self.lock_ongoing_games:
            if(self.ongoing_games is not None):
                return [i['gameId'] for i in self.ongoing_games]

    def seek_game(self):
        pass

    def is_my_turn(self, game_id):
        pass