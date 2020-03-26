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
        self.lock_game_states = {}

        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')

        self.update_ongoing_games()

    def thread_update_ongoing_games(self):
        while(True):
            self.update_ongoing_games()
            time.sleep(5)

    def thread_stream_game_states(self):
        while(True):
            for game_id in self.get_ongoing_games_ids():
                if(game_id not in self.game_states.keys()):
                    self.stream_game_state(game_id)
            time.sleep(5)

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

    def get_is_move_valid(self, move, game_id=None):
        if(game_id is None or game_id not in self.game_states.keys()):
            if(game_id not in self.game_states.keys()):
                print_debug(f'State of game {game_id} not available to ' +
                            'get is move valid')
            # board.legal_moves prints <LegalMoveGenerator at 0x7ff666656908 (Nh3, ...)>
            board = chess.Board()
        else:
            # TODO: load from game state
            board = chess.Board()

        return move in str(board.legal_moves).split("(")[-1].split(")")[0]

    def stream_game_state(self, game_id):
        # USE AS THREAD
        self.lock_game_states[game_id] = Lock()
        self.game_states[game_id]['board'] = chess.Board()
        try:
            for event in self.client.bots.stream_game_state(game_id):
                with self.lock_game_states[game_id]:
                    self.game_states[game_id]['game_state'] = event
                    self.game_states[game_id]['board'] = event
                    
            with self.lock_game_states[game_id]:
                del self.game_states[game_id]
            del self.lock_game_states[game_id]

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