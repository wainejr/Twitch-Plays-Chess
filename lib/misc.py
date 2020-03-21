import time
from os import system


def print_debug(message, mtype='INFO'):
    mtype = mtype.upper()
    print('[{}] [{}] {}'.format(time.strftime('%H:%M:%S', time.gmtime()),
                                mtype, message), flush=True)


def ppi(channel, message, username):
    print('[{} {}] <{}> {}'.format(time.strftime('%H:%M:%S', time.gmtime()),
                                   channel, username.lower(), message), flush=True)


def pbot(message, channel=''):
    if channel:
        msg = '[{} {}] <{}> {}'.format(time.strftime('%H:%M:%S', time.gmtime()),
                                       channel, 'BOT', message)
    else:
        msg = '[{}] <{}> {}'.format(time.strftime('%H:%M:%S', time.gmtime()),
                                    'BOT', message)

    print(msg, flush=True)
