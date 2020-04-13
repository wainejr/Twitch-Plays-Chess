import time
import os
from threading import Lock, Thread
import copy as cp

import sqlite3
import json
import pprint
pp = pprint.PrettyPrinter()

from config.config import config
from lib.botIRC import BotIRC
from lib.botChess import BotChess
from lib.misc import print_debug


class BotHandler:

    PATH_OBS_JSON = './obs/info.json'

    def __init__(self):
        self.config = config
        self.bot_chess = BotChess(config['lichess'], self)
        self.bot_irc = BotIRC(config['twitch'])

        # Current game ids
        self.game_ids = []
        self.lock_game_ids = Lock()

        # Users that already voted in certain games
        self.users_already_voted = {}
        self.lock_users_already_voted = Lock()

    def thread_update_game_ids(self):
        while True:
            time.sleep(0.2)
            with self.lock_game_ids:
                self.game_ids = self.bot_chess.get_ongoing_game_ids()

    def reset_users_voted_moves(self, game_id):
        with self.lock_users_already_voted:
            if(game_id not in self.users_already_voted.keys()):
                return None
            self.users_already_voted[game_id] = []

    def set_user_as_already_voted(self, game_id, user):
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
        with self.lock_users_already_voted:
            # If there's no list of users yet
            if(game_id not in self.users_already_voted.keys()):
                return False
            # If the user is not in the list of user that 
            # already voted in game_id
            if(user not in self.users_already_voted[game_id]):
                return False
        return True

    def update_obs_json_url(self, game_id):
        try:
            json_info = self.get_obs_info_json()
            json_info["url"] = f"http://www.lichess.org/{game_id}"

            with open(BotHandler.PATH_OBS_JSON, "w") as f:
                json.dump(json_info, f)

            print_debug(f"Wrote http://www.lichess.org/{game_id} to " +
                f"{BotHandler.PATH_OBS_JSON}", "DEBUG")

        except Exception as e:
            print_debug(f"Unable to update url in {BotHandler.PATH_OBS_JSON}."
                + f" Exception: {e}")

    def update_obs_json_WDL(self, wins, draws, losses):
        try:
            json_info = self.get_obs_info_json()
            json_info["wins"] = wins
            json_info["draws"] = draws
            json_info["losses"] = losses

            with open(BotHandler.PATH_OBS_JSON, "w") as f:
                json.dump(json_info, f)

            print_debug(f"Updated W-D-L of {BotHandler.PATH_OBS_JSON}",
                "DEBUG")

        except Exception as e:
            print_debug(f"Unable to update WDL in {BotHandler.PATH_OBS_JSON}."
                + f" Exception: {e}")

    def get_obs_info_json(self):
        with open(BotHandler.PATH_OBS_JSON, "r") as f:
            json_info = json.load(f)
            return json_info

    def get_game_id_from_url(self, url):
        return url.split("/")[-1]

    def get_game_ids(self):
        cp_game_ids = None
        with self.lock_game_ids:
            cp_game_ids = cp.deepcopy(self.game_ids)
        return cp_game_ids

    def thread_twitch_chat(self):
        while True:
            time.sleep(0.2)

            # Check for new messages
            new_messages = self.bot_irc.recv_messages(1024)

            # If there's no messages, continues
            if new_messages is None:
                continue

            # Get a copy of the current game ids
            cp_game_ids = self.get_game_ids()

            for message in new_messages:
                print_debug(f"Message: {message}", "DEBUG")
                # Tries to get move from the message
                move = self.bot_chess.get_move_from_msg(message['message'])
                # Gets username
                username = message['username']

                if(move is not None and len(cp_game_ids) > 0):
                    # Select game_id
                    # TODO: more robust way to define game_id 
                    # (needed if there's more than one game)
                    game_id = cp_game_ids[0]

                    # If the user has already voted in that game, it does not
                    # let him vote again
                    if(self.get_has_user_already_voted(game_id, username)):
                        continue
                    # Votes for move in the game
                    ret = self.bot_chess.vote_for_move(game_id, move)
                    if(ret):
                        # Set user as already voted in the game
                        self.set_user_as_already_voted(game_id, username)

    def thread_obs_update(self):
        last_json = self.get_obs_info_json()
        has_updated_wdl = False

        while True:
            time.sleep(0.2)

            # Get current ongoing games
            games_ids = self.get_game_ids()

            # If there are no games and Wins, Draws and Losses 
            # were not updated yet
            if not has_updated_wdl and len(games_ids) == 0:
                # Gets account info
                acc_info = self.bot_chess.get_account_info()

                if(acc_info is not None):
                    # Gets wins, draws and losses
                    wins, draws, losses = acc_info['count']['win'], \
                        acc_info['count']['draw'], acc_info['count']['loss']
                    # Updates local json
                    self.update_obs_json_WDL(wins, draws, losses)

                    has_updated_wdl = True

            # Update URL that OBS is reading from
            if(len(games_ids) > 0):
                # Set the Wins, Draws and losses as not updated
                game_id = games_ids[0]
                # If the game_id has changed, updates OBS json
                if(game_id != self.get_game_id_from_url(last_json["url"])):
                    self.update_obs_json_url(game_id)
                    last_json = self.get_obs_info_json()

    def run(self):
        # Start game_id checking thread
        self.thread_games = Thread(
            target=self.thread_update_game_ids, daemon=True)
        self.thread_games.start()
        # Start OBS thread
        self.thread_obs = Thread(
            target=self.thread_obs_update, daemon=True)
        self.thread_obs.start()
        # Start Twitch thread
        self.thread_twitch = Thread(
            target=self.thread_twitch_chat, daemon=True)
        self.thread_twitch.start()

        # Keeps running, because all threads are daemon
        while True:
            time.sleep(10)
