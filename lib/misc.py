import time
import os
from threading import Thread

LOG_FILE = "./server.log"
COOKIE_FILE = "./cookie_login"

# TODO: improve log file, its creation and logging
# Create LOG_FILE
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w") as f:
        f.write("")


def print_debug(message, mtype="INFO"):
    """ Prints and logs given message
    
    Arguments:
        message {str} -- Message to print and log
    
    Keyword Arguments:
        mtype {str} -- Message type (default: {'INFO'})
    """

    mtype = mtype.upper()
    msg = "[{}] [{}] {}".format(
        time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), mtype, message
    )
    print(msg, flush=True)
    with open(LOG_FILE, "a+") as f:
        f.write(msg + "\n")


def get_lichess_login_cookie():
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r") as f:
            return f.read()
    return ""


def start_thread(thread_func, daemon=True, args=()):
    """ Starts new thread

    Arguments:
        thread_func {function} -- Thread target function
    
    Keyword Arguments:
        daemon {bool} -- Thread is daemonized or not (daemonized threads
            allows the program to end without it being finished)
            (default: {True})
        args {tuple} -- Functions arguments (default: {()})
    
    Returns:
        Thread -- Object of the started thread 
    """

    thread = Thread(target=thread_func, args=args)
    thread.daemon = daemon
    thread.start()
    return thread
