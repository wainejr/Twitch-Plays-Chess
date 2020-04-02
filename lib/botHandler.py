import time

import sqlite3
import pprint
pp = pprint.PrettyPrinter()

from config.config import config
from lib.botIRC import BotIRC
from lib.botChess import BotChess


class BotHandler:

    DATABASE_PATH = './db/localdb.db'

    def __init__(self):
        self.config = config
        self.bot_chess = BotChess(config['lichess'])
        self.bot_irc = BotIRC(config['twitch'])

    def init_local_database(self):
        pass

    def add_msgs_to_database(self):
        pass

    def run(self):
        while True:
            new_messages = self.bot_irc.recv_messages(1024)

            if not new_messages:
                continue

            print(new_messages)
            for message in new_messages:
                move = self.bot_chess.get_move_from_msg(message['message'])
                games_ids = self.bot_chess.get_ongoing_game_ids()
                print(move, games_ids)
                if(move is not None and len(games_ids) > 0):
                    self.bot_chess.vote_for_move(games_ids[0], move)
