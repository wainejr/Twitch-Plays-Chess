import requests
import certifi

from lib.misc import pp


class BotChess:

    ROUTE_BASE = 'https://lichess.org'
    ROUTE_ACCOUNT = ROUTE_BASE + '/api/account'

    def __init__(self, config):
        self.auth_header = {'Authorization': 'Bearer ' + config['token']}
        self.start_session()

    def start_session(self):
        try:
            r = requests.request(
                'GET', BotChess.ROUTE_ACCOUNT, headers=self.auth_header, 
                verify=True, allow_redirects=False)
            
            if(r.status_code != 200):
                pp('Unable to stablish session\nMessage: {}'.format(
                    r.text), 'ERROR')
            
        except Exception as e:
            pp('Unable to get token\nException: {}'.format(e), 'ERROR')

    def ping_session(self):
        pass

    def get_move_from_msg(self, message):
        pass

    def make_move(self, move):
        pass

    def get_is_move_valid(self, move):
        pass

    def get_current_game(self, format='pgn'):
        pass

    def start_game(self):
        pass