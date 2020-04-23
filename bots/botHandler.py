import time
import os
from threading import Lock, Thread
import copy as cp

import json

from config.config import config
from bots.botIRC import BotIRC
from bots.botChess import BotChess
from lib.misc import print_debug


class BotHandler:
    """ Class to handle Bots """

    # json file used by OBS to update its scenes
    PATH_OBS_JSON = './obs/info.json'

    # Interval (seconds) to change URL in OBS json and then change back to the
    # one before. This is needed because OBS does not refresh
    # page after some time
    REFRESH_URL_INTERVAL = 1800 # 30 minutes

    # COMMANDS MUST START WITH '!'
    MSG_COMMANDS = ['!resign', '!challenge', '!start']

    def __init__(self):
        """ BotHandler constructor """

        # Bots configurations
        self.config = config

        # Create BotChess object
        self.bot_chess = BotChess(config['lichess'], self)
        # Create BotIRC object
        self.bot_irc = BotIRC(config['twitch'])

        # Current game ids
        self.game_ids = []
        self.lock_game_ids = Lock()

        # Users that already voted in certain games
        self.users_already_voted = {}
        self.lock_users_already_voted = Lock()

    def run(self):
        """ Run BotHandler (start program) """
        # Start game_id checking thread
        self.thread_games = Thread(
            target=self.thread_update_game_ids, daemon=True)
        self.thread_games.start()
        # Start OBS thread to update wins, draws and losses
        self.thread_obs_wdl = Thread(
            target=self.thread_obs_update_WDL, daemon=True)
        self.thread_obs_wdl.start()
        # Start OBS thread to update URL
        self.thread_obs_url = Thread(
            target=self.thread_obs_update_URL, daemon=True)
        self.thread_obs_url.start()
        # Start Twitch thread
        self.thread_twitch = Thread(
            target=self.thread_twitch_chat, daemon=True)
        self.thread_twitch.start()

        # Keeps running, because all threads are daemon
        while True:
            time.sleep(10)

    def thread_update_game_ids(self):
        """ Thread to update current games IDs """

        while True:
            time.sleep(0.2)
            self.update_game_ids()

    def thread_twitch_chat(self):
        """ Thread to listen messages in Twitch chat and treat them """

        while True:
            time.sleep(0.2)

            # Check for new messages
            new_messages = self.bot_irc.recv_messages(1024)

            # If there's no messages, continues
            if new_messages is None:
                continue

            for message in new_messages:
                print_debug(f"Message: {message}", "DEBUG")

                # Tries to get command from message
                command = self.get_command_from_msg(message['message'])

                if(command is not None):
                    self.treat_command(command, message)
                    continue

                # Tries to get move from the message
                move = self.bot_chess.get_move_from_msg(message['message'])
                if(move is not None):
                    self.treat_move_msg(move, message)

    def thread_obs_update_WDL(self):
        """ Thread to update wins, draws and losses in OBS json """

        last_json = self.get_obs_info_json()

        while(True):
            time.sleep(5)
            # Updates wins, draws and losses at the beginning
            acc_info = self.bot_chess.get_account_info()
            if(acc_info is not None):
                # Gets wins, draws and losses
                wins, draws, losses = acc_info['count']['win'], \
                    acc_info['count']['draw'], acc_info['count']['loss']
                if(wins != last_json['wins'] or draws != last_json['draws'] 
                   or losses != last_json['losses']):
                    # Updates local json
                    self.update_obs_json_WDL(wins, draws, losses)
                    last_json = self.get_obs_info_json()

    def thread_obs_update_URL(self):
        """ Thread to update OBS json file """

        last_game_id = self.get_game_id_from_url(self.get_obs_info_json()['url'])
        refresh_time = time.time()
        color = 'white'

        while True:
            time.sleep(0.5)

            # If refresh time has passed, updated URL, wait some time and then
            # go back to the page
            if(time.time()-refresh_time >= BotHandler.REFRESH_URL_INTERVAL):
                # Updates URL to user page
                self.update_obs_json_url(last_game_id)
                time.sleep(3)
                # Updated URL back to game_id
                self.update_obs_json_url(last_game_id+'/'+color)
                refresh_time = time.time()

            # Get current ongoing games
            games_ids = self.get_game_ids()

            # Update URL that OBS is reading from
            if(len(games_ids) > 0):
                # Gets current game ID
                game_id = games_ids[0]
                # If the game_id has changed, updates OBS json
                if(game_id != last_game_id):
                    # Tries to get color in ongoing game
                    color_aux = self.bot_chess.get_color_in_ongoing_game(game_id)
                    if(color_aux is not None):
                        color = color_aux
                    # Updated URL
                    self.update_obs_json_url(game_id+'/'+color)
                    # Updates last game ID
                    last_game_id = game_id

    def treat_move_msg(self, move, msg_dict):
        """ Treats message with a move

        Arguments:
            move {str} -- Move string
            msg_dict {dict} -- Dictionary with message info
        """

        # Get copy of current game ids
        cp_game_ids = self.get_game_ids()
        if(len(cp_game_ids) == 0):
            return

        # Select game_id
        # TODO: more robust way to define game_id 
        # (needed if there's more than one game)
        game_id = cp_game_ids[0]
        
        # If the user has already voted in that game, it does not
        # let him vote again
        if(self.get_has_user_already_voted(game_id, msg_dict['username'])):
            print_debug(f"{msg_dict['username']} trying to vote again", "DEBUG")
            return
        # Votes for move in the game
        ret = self.bot_chess.vote_for_move(game_id, move)
        if(ret):
            # Set user as already voted in the game
            self.set_user_as_already_voted(game_id, msg_dict['username'])

    def update_game_ids(self):
        """ Update current game ids """
        with self.lock_game_ids:
            self.game_ids = self.bot_chess.get_ongoing_game_ids()

    def treat_command(self, command, msg_dict):
        """ Treats command from message

        Arguments:
            command {dict} -- Dictionary as {"!command_name": command_msg}
            msg_dict {dict} -- Dictionary with message info
        """

        # Treats !resign command
        if('!resign' in command.keys()):
            # Gets copy of current game ids
            cp_game_ids = self.get_game_ids()
            # If there's no game, don't do nothing
            if(len(cp_game_ids) == 0):
                print_debug("There is no game, unable to resign", "DEBUG")
                return

            # Select game_id
            # TODO: more robust way to define game_id 
            # (needed if there's more than one game)
            game_id = cp_game_ids[0]
            ret = self.bot_chess.vote_for_resign(game_id)
            if(ret):
                self.set_user_as_already_voted(game_id, msg_dict["username"])
        elif('!start' in command.keys()):
            # Gets copy of current game ids
            cp_game_ids = self.get_game_ids()
            # If there are no ongoing games, start new game against AI
            if(len(cp_game_ids) == 0):
                self.bot_chess.tmp_start_new_game_AI()
                # Updates ongoing games and game_ids to avoid starting 
                # two games in a row
                self.bot_chess.update_ongoing_games()
                self.update_game_ids()

        # TODO: Treatment of !challenge command
        elif('!challenge' in command.keys()):
            pass

    def reset_users_voted_moves(self, game_id):
        """ Reset users that voted in given game

        Arguments:
            game_id {str} -- Game ID in Lichess
        """

        with self.lock_users_already_voted:
            if(game_id not in self.users_already_voted.keys()):
                return
            self.users_already_voted[game_id] = []

    def set_user_as_already_voted(self, game_id, user):
        """ Set given user as already voted in given game 

        Arguments:
            game_id {str} -- Game ID in Lichess
            user {str} -- User in Twitch
        """

        with self.lock_users_already_voted:
            # Adds list of users that already voted in game_id
            # if it has not been created yet
            if(game_id not in self.users_already_voted.keys()):
                self.users_already_voted[game_id] = []
            # Appends user to the list of users that already voted in
            # game_id, if he is not already in it
            if(user not in self.users_already_voted[game_id]):
                self.users_already_voted[game_id].append(user)

    def get_has_user_already_voted(self, game_id, user):
        """ Get if given user has already voted in given game

        Arguments:
            game_id {str} -- Game ID in Lichess
            user {str} -- User in Twitch

        Returns:
            bool -- True if user has already voted, False otherwise
        """

        with self.lock_users_already_voted:
            # If there's no list of users yet
            if(game_id not in self.users_already_voted.keys()):
                return False
            # If the' user is not in the list of user that 
            # already voted in game_id
            if(user not in self.users_already_voted[game_id]):
                return False
        return True

    def update_obs_json_url(self, lichess_route):
        """ Upate URL in OBS json to stream given Lichess route

        Arguments:
            lichess_route {str} -- Route in lichess.org
        """

        try:
            # Gets OBS json as dictionary
            json_info = self.get_obs_info_json()

            # Updates URL
            url = f"http://www.lichess.org/{lichess_route}"
            json_info["url"] = url

            # Updates OBS json
            with open(BotHandler.PATH_OBS_JSON, "w") as f:
                json.dump(json_info, f)

            print_debug(f"Wrote {url} to {BotHandler.PATH_OBS_JSON}", "DEBUG")

        except Exception as e:
            print_debug(f"Unable to update url in {BotHandler.PATH_OBS_JSON}."
                + f" Exception: {e}")

    def update_obs_json_WDL(self, wins, draws, losses):
        """ Upate wins, draws and losses in OBS json

        Arguments:
            wins {int} -- Number of wins
            draws {int} -- Number of draws
            losses {int} -- Number of losses
        """

        try:
            # Gets OBS json as dictionary
            json_info = self.get_obs_info_json()

            # Updates wins, draws and losses
            json_info["wins"] = wins
            json_info["draws"] = draws
            json_info["losses"] = losses

            # Updates OBS json
            with open(BotHandler.PATH_OBS_JSON, "w") as f:
                json.dump(json_info, f)

            print_debug(f"Updated W-D-L of {BotHandler.PATH_OBS_JSON}",
                "DEBUG")

        except Exception as e:
            print_debug(f"Unable to update WDL in {BotHandler.PATH_OBS_JSON}."
                + f" Exception: {e}")

    def create_obs_info_json(self):
        """ Creates OBS json file """

        with open(BotHandler.PATH_OBS_JSON, "w") as f:
            # Get last played game ID 
            last_id = self.bot_chess.get_id_last_game_played()
            # Creates OBS json file with URL from last game played
            json.dump(
                {"wins": 0, "losses": 0, "draws": 0, 
                "url": "http://www.lichess.org/"
                    + (last_id if last_id is not None else "")}
                , f)
        print_debug(f"Create {BotHandler.PATH_OBS_JSON} as OBS json", "DEBUG")

    def get_obs_info_json(self):
        """ Gets OBS json as dictionary

        Returns:
            dict or None -- OBS json information or None in case of error
        """

        if(not os.path.exists(BotHandler.PATH_OBS_JSON)):
            print_debug(f"File {BotHandler.PATH_OBS_JSON} does not exists",
                "DEBUG")
            self.create_obs_info_json()

        with open(BotHandler.PATH_OBS_JSON, "r") as f:
            try:
                json_info = json.load(f)
            except Exception as e:
                print_debug(f"Unable to read OBS json. Excepction: {e}", "DEBUG")
                self.create_obs_info_json()
                try:
                    json_info = json.load(f)
                except Exception as e2:
                    print_debug(f"I give up on reading OBS json. Exception {e2}",
                        "ERROR")
                    return None
            return json_info

    def get_game_id_from_url(self, url):
        """ Get Lichess game ID from given URL
        
        Arguments:
            url {str} -- Lichess game URL
        
        Returns:
            str -- Game ID
        """
        return url.split("/")[-1]

    def get_game_ids(self):
        """ Get current Lichess games IDs
        
        Returns:
            list -- List of games IDs
        """

        cp_game_ids = None
        with self.lock_game_ids:
            cp_game_ids = cp.deepcopy(self.game_ids)
        return cp_game_ids

    def get_command_from_msg(self, msg):
        """ Gets command from given message

        Arguments:
            msg {str} -- Message to get command from
        
        Returns:
            dict or None -- Command dict as {"!command": command_msg} in case
                a command is found, None otherwise
        """

        # COMMANDS MUST START WITH !
        if(msg[0] != '!'):
            return None
        
        parse_msg = msg.split(" ")
        if(len(parse_msg) == 0):
            return None
        for command in BotHandler.MSG_COMMANDS:
            if(parse_msg[0].lower() == command):
                return {command:
                    parse_msg[1] if len(parse_msg) >= 2 else None}
