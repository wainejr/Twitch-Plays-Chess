import time
import os
from datetime import datetime

LOG_FILE = "./server.log"

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
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), mtype, message
    )
    print(msg, flush=True)
    with open(LOG_FILE, "a+") as f:
        f.write(msg + "\n")
