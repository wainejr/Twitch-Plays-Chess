#!/usr/bin/env python

from sys import exit
from config.config import config
from bots.botHandler import BotHandler

# Twitch Plays

try:
    BotHandler().run()
except KeyboardInterrupt:
    exit()
