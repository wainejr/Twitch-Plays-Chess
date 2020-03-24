import requests
import certifi
import json
import pprint
import chess
import re
import berserk

from lib.misc import print_debug

class BotChess:

    URL_BASE = 'https://lichess.org'
    
    # Base routes
    ROUTE_API = URL_BASE + '/api'
    ROUTE_ACCOUNT = URL_BASE + '/api/account'
    ROUTE_BOT = URL_BASE + '/api/bot'
    ROUTE_STREAM = URL_BASE + '/api/stream'

    # Game related routes
    ROUTE_MOVE = lambda game_id, move: BotChess.ROUTE_BOT \
                + '/game/' + game_id + '/move/' + move

    ROUTE_RESIGN = lambda game_id: BotChess.ROUTE_BOT \
                + '/game/' + game_id + '/abort'

    ROUTE_GAME_LIVE = lambda game_id: BotChess.ROUTE_BOT \
                + '/game/stream/' + game_id

    ROUTE_DRAW_OFFER = lambda game_id, msg: BotChess.ROUTE_BOT \
                + '/game/stream/' + game_id + '/draw/' + msg

    # Stram related routes
    ROUTE_STREAM_EVENTS = ROUTE_STREAM + '/event'
    
    # Challenge related routes
    ROUTE_SEEK_GAME = ROUTE_API + '/board/seek'

    # Game state related routes
    ROUTE_ONGOING_GAMES = ROUTE_ACCOUNT + '/playing'

    pp = pprint.PrettyPrinter()

    def __init__(self, config):
        self.config = config
        self.auth_header = {'Authorization': 'Bearer ' + config['token']}
        
        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')

        self.board = chess.Board()
        self.ongoing_games = None
        self.update_ongoing_games()
        # id_test = self.__get_game_id_test()
        id_test = self.get_ongoing_games_ids()[0]
        game = self.get_game_moves(id_test)
        print(game)
        # BotChess.pp.pprint(ret)

    def start_session(self):
        try:
            self.session = berserk.TokenSession(self.config['token'])
            self.client = berserk.Client(self.session)
            return True
        except Exception as e:
            print_debug('Unable to stablish session\nException: {}'.format(e),
                        'EXCEPTION')
            return None

    def ping_session(self):
        pass

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
            r = requests.post(
                BotChess.ROUTE_MOVE(game_id, move),
                headers=self.auth_header
            )

            if(r.status_code != 200):
                print_debug(
                    'Error making move {} in game {}\nMessage: {}'.format(
                    move, game_id, r.text), 'ERROR')
            else:
                print_debug('Moved {} in game {}'.format(
                    move, game_id), 'INFO')

        except Exception as e:
            print_debug(str(e), 'EXCEPTION')

    def get_is_move_valid(self, move):
        # board.legal_moves prints <LegalMoveGenerator at 0x7ff666656908 (Nh3, ...)>
        return move in str(self.board.legal_moves).split("(")[-1].split(")")[0]

    def stream_game_state(self, game_id, format='pgn'):
        try:
            for event in self.client.bots.stream_game_state(game_id):
                print(event)
                print("s")
            return True
        except Exception as e:
            print_debug(str(e), 'EXCEPTION')
            return None

    def update_ongoing_games(self):
        try:
            r = requests.get(
                BotChess.ROUTE_ONGOING_GAMES,
                headers=self.auth_header)

            if(r.status_code != 200):
                print_debug('Unable to get ongoing games\nMessage: {}'.format(
                    r.text), 'ERROR')
            else:
                self.ongoing_games = r.json()['nowPlaying']
                print_debug('Updated ongoing games', 'DEBUG')
        except Exception as e:
            print_debug('Unable to get ongoing games\nException: {}'.format(e),
                        'EXCEPTION')

    def get_ongoing_games_ids(self):
        if(self.ongoing_games is not None):
            return [i['gameId'] for i in self.ongoing_games]

    def __get_game_id_test(self):
        try:
            r = requests.get(
                BotChess.URL_BASE + '/tv/channels',
                headers=self.auth_header
            )

            return r.json()["Blitz"]["gameId"]

        except Exception as e:
            print_debug(str(e), 'EXCEPTION')
            return None

    def seek_game(self):
        pass

    def get_is_my_turn(self):
        pass