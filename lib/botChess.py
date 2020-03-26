import time
from threading import Thread, Lock

import json
import pprint
import chess
import re
import berserk

from lib.misc import print_debug

pp = pprint.PrettyPrinter()


class BotChess:

    def __init__(self, config):
        self.config = config
        
        self.ongoing_games = {}
        self.lock_ongoing_games = Lock()

        self.game_move_votes = {}

        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')

        # Start threads
        self.start_thread(self.thread_update_ongoing_games)

    def start_thread(self, thread_func, daemon=False, args=()):
        thread = Thread(target=thread_func, args=args)
        thread.daemon = True
        thread.start()
        return thread

    def thread_update_ongoing_games(self):
        while(True):
            self.update_ongoing_games()
            time.sleep(1)

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
        if(game_id is None or game_id not in self.ongoing_games.keys()):
            if(game_id not in self.ongoing_games.keys()):
                print_debug(f'State of game {game_id} not available to ' +
                            'get is move valid', 'DEBUG')
                return False
            board = chess.Board()
        elif(self.is_my_turn(game_id)):
            game = self.ongoing_games[game_id]
            board = chess.Board(fen=game['fen'])
            board.turn = game['color'] == 'white'
        else:
            print_debug(f'Not my turn in game {game_id}', 'DEBUG')
            return False

        return move.lower() in self.get_legal_moves(board)

    def get_legal_moves(self, board):
        # board.legal_moves prints <LegalMoveGenerator at 0x7ff666656908 (Nh3, ..., a5)>
        # returns ['nh3', ... , 'a5']
        return str(board.legal_moves).split("(")[-1].split(")")[0].replace(
            ',','').lower().split(' ')

    def update_ongoing_games(self):
        try:
            with self.lock_ongoing_games:
                games = self.client.games.get_ongoing()
                for game in games:
                    self.ongoing_games[game['gameId']] = game
        except Exception as e:
            print_debug('Unable to get ongoing games\nException: {}'.format(e),
                        'EXCEPTION')

    def seek_game(self):
        pass

    def is_my_turn(self, game_id):
        if game_id in self.ongoing_games.keys():
            return self.ongoing_games[game_id]['isMyTurn']
