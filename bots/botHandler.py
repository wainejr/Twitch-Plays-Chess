import time
import os
from threading import Lock, Thread
import copy as cp
from datetime import datetime
from typing import Optional

import json

from config import config
from bots.botIRC import BotIRC
from bots.botChess import BotChess
from db.dbHandler import DbHandler
from lib.misc import print_debug, start_thread


class BotHandler:
    """ Class to handle Bots """

    # json file used by OBS to update its scenes
    PATH_OBS_JSON = "./obs/info.json"

    # Interval (seconds) to change URL in OBS json and then change back to the
    # one before. This is needed because OBS does not refresh
    # page after some time
    REFRESH_URL_INTERVAL = 1800  # 30 minutes

    # Keeps an open Challenge for at maximum 120 seconds
    MAX_INTERVAL_OPEN_CHALLENGE = 60

    # COMMANDS MUST START WITH '!'
    MSG_COMMANDS = ["!resign", "!newgame", "!challenge"]

    def __init__(self):
        """ BotHandler constructor """

        # Bots configurations
        self.config = config

        # Create BotChess object
        self.bot_chess = BotChess(config["lichess"], self)

        # Create BotIRC object
        self.bot_irc = BotIRC(config["twitch"])

        # Create Database Handler
        self.db_handler = DbHandler()

        # Current game ID
        self.curr_game_id = None
        self.lock_curr_game_id = Lock()

        # ID of open challenge created by BotChess
        self.open_challenge_id = None
        self.lock_open_challenge = Lock()

        # Users that already voted in certain games
        self.users_already_voted = {}
        self.lock_users_already_voted = Lock()

    def run(self):
        """ Run BotHandler (start program) """

        # Start OBS thread to update wins, draws and losses
        self.thread_obs_wdl = start_thread(self.thread_obs_update_WDL)
        # Start OBS thread to update URL
        self.thread_obs_url = start_thread(self.thread_obs_update_URL)
        # Start Twitch thread
        self.thread_twitch = start_thread(self.thread_twitch_chat)

        # Keeps program running, because all threads are daemon
        while True:
            time.sleep(5)

    def thread_check_open_challenge(self):
        """ Checks if open challenge was already accepted or not """

        last_open_challenge = time.time()

        while True:
            time.sleep(1)

            with self.lock_open_challenge:
                # If there is an open challenge and its ID is the current
                # game ID, that means that the challenge was accepted.
                # So it resets the open challenge since it is not open anymore
                if (
                    self.open_challenge_id is not None
                    and self.open_challenge_id == self.curr_game_id
                ):
                    self.open_challenge_id = None
                    print_debug(
                        f"Open challenge {self.open_challenge_id}" + " accepted", "INFO"
                    )
                # If the open challenge interval has passed with an open
                # challenge, resets the open challenge.
                elif (
                    self.open_challenge_id is not None
                    and time.time() - last_open_challenge
                    > BotHandler.MAX_INTERVAL_OPEN_CHALLENGE
                ):
                    self.open_challenge_id = None
                    print_debug(
                        "Reseted open challenge " + f"{self.open_challenge_id}.", "INFO"
                    )
                # Resets the time of the last open challenge, if there is no
                # open challenge
                elif self.open_challenge_id is None:
                    last_open_challenge = time.time()

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
                command = self.get_command_from_msg(message["message"])

                if command is not None:
                    self.treat_command(command, message)
                    continue

                # Tries to get move from the message
                move = self.bot_chess.get_move_from_msg(message["message"])
                if move is not None:
                    self.treat_move_msg(move, message)

    def thread_obs_update_WDL(self):
        """ Thread to update wins, draws and losses in OBS json """

        last_json = self.get_obs_info_json()

        while True:
            time.sleep(5)
            # Updates wins, draws and losses at the beginning
            acc_info = self.bot_chess.get_account_info()
            if acc_info is not None:
                # Gets wins, draws and losses
                wins, draws, losses = (
                    acc_info["count"]["win"],
                    acc_info["count"]["draw"],
                    acc_info["count"]["loss"],
                )
                if (
                    wins != last_json["wins"]
                    or draws != last_json["draws"]
                    or losses != last_json["losses"]
                ):
                    # Updates local json
                    self.update_obs_json_WDL(wins, draws, losses)
                    last_json = self.get_obs_info_json()

    def thread_obs_update_URL(self):
        """ Thread to update OBS json file """

        last_game_id = self.get_game_id_from_url(self.get_obs_info_json()["url"])
        refresh_time = time.time()
        color = "white"

        while True:
            time.sleep(0.5)

            # If refresh time has passed, updates URL, wait some time and then
            # go back to the previous page. This is because OBS stops updating
            # the page after sometime
            if time.time() - refresh_time >= BotHandler.REFRESH_URL_INTERVAL:
                # Updates URL to game_id without color
                self.update_obs_json_url(last_game_id)
                time.sleep(3)
                # Updates URL back to game_id
                self.update_obs_json_url(last_game_id + "/" + color)
                refresh_time = time.time()

            game_id = self.curr_game_id

            if game_id != last_game_id:
                # Tries to get color in ongoing game
                color_aux = self.bot_chess.get_color_in_current_game(game_id)
                if color_aux is not None:
                    color = color_aux
                    # Updated URL
                    self.update_obs_json_url(game_id + "/" + color)
                    # Updates last game ID
                    last_game_id = game_id

    def update_game_id(self, game_id: Optional[int]):
        """ Thread to update current games IDs and handle them """

        self.curr_game_id = game_id

    def treat_move_msg(self, move, msg_dict):
        """ Treats message with a move

        Arguments:
            move {str} -- Move string
            msg_dict {dict} -- Dictionary with message info
        """

        # Get copy of current game id
        game_id = self.curr_game_id
        if game_id is None:
            return

        # If the user has already voted in that game, it does not
        # let him vote again
        if self.get_has_user_already_voted(msg_dict["username"]):
            print_debug(f"{msg_dict['username']} trying to vote again", "DEBUG")
            self.bot_irc.send_message(f"{msg_dict['username']} already voted")
            return

        # Votes for move in the game
        ret, move = self.bot_chess.vote_for_move(move)
        if ret:
            # Set user as already voted in the game
            self.set_user_as_already_voted(msg_dict["username"])
            # Send message to Twitch Chat
            self.bot_irc.send_message(f"{msg_dict['username']} voted for {move}")
            # Register vote in database
            self.db_handler.add_move_vote(
                msg_dict["username"], move, datetime.utcnow(), game_id
            )

    def treat_command(self, command, msg_dict):
        """ Treats command from message

        Arguments:
            command {dict} -- Dictionary as {"!command_name": command_msg}
            msg_dict {dict} -- Dictionary with message info
        """

        # Gets copy of current game ids
        game_id = self.curr_game_id

        # Treats !resign command
        if "!resign" in command.keys():
            # If there's no game, don't do nothing
            if game_id is None:
                print_debug("There is no game, unable to resign", "INFO")
                self.bot_irc.send_message(
                    "There's no ongoing game. Unable to resign", 0.3
                )
                return

            ret = self.bot_chess.vote_for_resign()
            if ret:
                self.set_user_as_already_voted(msg_dict["username"])

        elif "!newgame" in command.keys():
            # If there are no ongoing games, start new game against AI
            if game_id is None:
                self.bot_chess.create_challenge_ai()
            else:
                print_debug(
                    "There is an ongoing game, unable to start new game", "INFO"
                )
                self.bot_irc.send_message(
                    "There's already an ongoing game. Finish it first to start a new game!",
                    0.3,
                )

        elif "!challenge" in command.keys():
            if game_id is None:
                self.bot_irc.send_message(
                    "There's already an ongoing game."
                    + " Finish it first to challenge me!",
                    0.3,
                )
                return

            # If there are no ongoing games, create open challenge and join it
            if self.open_challenge_id is None:
                r = self.bot_chess.create_challenge()
                if r is not None:
                    # Accepts challenge in a thread (it takes a while so it is
                    # best to do it in a thread)
                    start_thread(
                        self.bot_chess.treat_challenge,
                        args=[r["challenge"]["id"], True, True],
                    )
                    self.open_challenge_id = r["challenge"]["id"]
            else:
                print_debug(
                    "There is already an open challenge, unable to start a new one",
                    "INFO",
                )

            if self.open_challenge_id is not None:
                self.bot_irc.send_message(
                    f"Go to https://lichess.org/{self.open_challenge_id} "
                    + "and accept the challenge!",
                    0.3,
                )

    def reset_users_voted_moves(self):
        """ Reset users that voted in current game """

        with self.lock_users_already_voted:
            self.users_already_voted = []

    def set_user_as_already_voted(self, user):
        """ Set given user as already voted in current game 

        Arguments:
            user {str} -- User in Twitch
        """

        with self.lock_users_already_voted:
            # Appends user to the list of users that already voted in
            # game_id, if he is not already in it
            if user not in self.users_already_voted:
                self.users_already_voted.append(user)

    def get_has_user_already_voted(self, user):
        """ Get if given user has already voted in current game

        Arguments:
            user {str} -- User in Twitch

        Returns:
            bool -- True if user has already voted, False otherwise
        """

        with self.lock_users_already_voted:
            # If the' user is not in the list of user that
            # already voted in current game
            if user not in self.users_already_voted:
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
            print_debug(
                f"Unable to update url in {BotHandler.PATH_OBS_JSON}."
                + f" Exception: {e}"
            )

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

            print_debug(f"Updated W-D-L of {BotHandler.PATH_OBS_JSON}", "DEBUG")

        except Exception as e:
            print_debug(
                f"Unable to update WDL in {BotHandler.PATH_OBS_JSON}."
                + f" Exception: {e}"
            )

    def create_obs_info_json(self):
        """ Creates OBS json file """

        with open(BotHandler.PATH_OBS_JSON, "w") as f:
            # Get last played game ID
            last_id = self.bot_chess.get_id_last_game_played()
            # Creates OBS json file with URL from last game played
            json.dump(
                {
                    "wins": 0,
                    "losses": 0,
                    "draws": 0,
                    "url": "http://www.lichess.org/"
                    + (last_id if last_id is not None else ""),
                },
                f,
            )
        print_debug(f"Create {BotHandler.PATH_OBS_JSON} as OBS json", "DEBUG")

    def get_obs_info_json(self):
        """ Gets OBS json as dictionary

        Returns:
            dict or None -- OBS json information or None in case of error
        """

        if not os.path.exists(BotHandler.PATH_OBS_JSON):
            print_debug(f"File {BotHandler.PATH_OBS_JSON} does not exists", "DEBUG")
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
                    print_debug(
                        f"I give up on reading OBS json. Exception {e2}", "ERROR"
                    )
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

    def get_command_from_msg(self, msg):
        """ Gets command from given message

        Arguments:
            msg {str} -- Message to get command from
        
        Returns:
            dict or None -- Command dict as {"!command": command_msg} in case
                a command is found, None otherwise
        """

        # COMMANDS MUST START WITH !
        if msg[0] != "!":
            return None

        parse_msg = msg.split(" ")
        if len(parse_msg) == 0:
            return None
        for command in BotHandler.MSG_COMMANDS:
            if parse_msg[0].lower() == command:
                return {command: parse_msg[1] if len(parse_msg) >= 2 else None}
