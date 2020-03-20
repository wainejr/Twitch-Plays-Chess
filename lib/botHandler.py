import time

from config.config import config
from lib.botIRC import BotIRC
from lib.botChess import BotChess


class BotHandler:

    def __init__(self):
        self.config = config
        self.chess = BotChess(config['lichess'])
        exit()
        self.irc = BotIRC(config['twitch'])
        self.message_buffer = [
            {'username': '', 'button': ''}] \
            * self.config['twitch']['misc']['chat_height']

    def set_message_buffer(self, message):
        self.message_buffer.insert(
            self.config['twitch']['misc']['chat_height'] - 1, message)
        self.message_buffer.pop(0)

    def run(self):
        pass
        while True:
            new_messages = self.irc.recv_messages(1024)

            if not new_messages:
                continue
