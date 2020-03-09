import time

from config.config import config
from lib.irc import Irc


class Bot:

    def __init__(self):
        self.config = config
        self.irc = Irc(config)
        self.message_buffer = [
            {'username': '', 'button': ''}] * self.config['misc']['chat_height']

    def set_message_buffer(self, message):
        self.message_buffer.insert(
            self.config['misc']['chat_height'] - 1, message)
        self.message_buffer.pop(0)

    def run(self):

        while True:
            new_messages = self.irc.recv_messages(1024)

            if not new_messages:
                continue
