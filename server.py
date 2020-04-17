from sys import exit
from bots.botHandler import BotHandler

# Twitch Plays

try:
    BotHandler().run()
except KeyboardInterrupt:
    exit()
