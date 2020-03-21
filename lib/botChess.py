import requests
import certifi
import json
import pprint
import chess
import re

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
    # ROUTE_ONGOING_GAMES = ROUTE_ACCOUNT + '/playing'

    pp = pprint.PrettyPrinter()

    def __init__(self, config):
        self.auth_header = {'Authorization': 'Bearer ' + config['token']}
        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')
        
        self.board = chess.Board()
        # BotChess.pp.pprint(ret)

    def start_session(self):
        try:
            r = requests.request(
                'GET', BotChess.ROUTE_ACCOUNT, headers=self.auth_header, 
                verify=True, allow_redirects=False)

            if(r.status_code != 200):
                print_debug('Unable to stablish session\nMessage: {}'.format(
                    r.text), 'ERROR')
                return None

            return json.loads(r.text)

        except Exception as e:
            print_debug('Unable to get token\nException: {}'.format(e), 'ERROR')
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

    def make_move(self, move):
        pass

    def get_is_move_valid(self, move):
        # board.legal_moves prints <LegalMoveGenerator at 0x7ff666656908 (Nh3, ...)>
        return move in str(self.board.legal_moves).split("(")[-1].split(")")[0]

    def get_current_game(self, format='pgn'):
        pass

    def seek_game(self):
        pass

    def get_is_my_turn(self):
        pass