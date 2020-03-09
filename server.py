#!/usr/bin/env python

from sys import exit
from config.config import config
from lib.bot import Bot

# Twitch Plays

try:
    Bot().run()
except KeyboardInterrupt:
    exit()
