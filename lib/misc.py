import time
import os

LOG_FILE = './server.log'

# TODO: improve log file, its creation and logging
# Create LOG_FILE
if(not os.path.exists(LOG_FILE)):
    with open(LOG_FILE, 'w') as f:
        f.write('')


def print_debug(message, mtype='INFO'):
    mtype = mtype.upper()
    msg = '[{}] [{}] {}'.format(time.strftime('%H:%M:%S', time.gmtime()),
                                mtype, message)
    print(msg, flush=True)
    with open(LOG_FILE, 'a+') as f:
        f.write(msg+'\n')


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
