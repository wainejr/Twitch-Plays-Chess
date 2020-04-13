import time
from threading import Thread, Lock
import os

import requests
import json
import pprint
import chess
import re
import berserk

from lib.misc import print_debug

pp = pprint.PrettyPrinter()

class BotChess:

    UCI_PATTERN = re.compile("[a-h][1-8][a-h][1-8]")

    def __init__(self, config, mode='anarchy'):
        self.config = config
        self.mode = mode

        self.ongoing_games = {}
        self.lock_ongoing_games = Lock()

        self.game_move_votes = {}
        self.lock_game_move_votes = Lock()

        self.thread_games = []
        self.lock_thread_games = Lock()

        ret = self.start_session()
        if(ret is None):
            raise Exception(
                'Unable to connect to lichess API. Check your personal token')

        # Start threads
        self.start_thread(self.thread_update_ongoing_games)
        self.start_thread(self.thread_games_handler)
        self.start_thread(self.thread_treat_incoming_events)

    def start_thread(self, thread_func, daemon=True, args=()):
        thread = Thread(target=thread_func, args=args)
        thread.daemon = daemon
        thread.start()
        return thread

    def thread_treat_incoming_events(self):
        for event in self.client.bots.stream_incoming_events():
            # If the event is a challenge
            if(event["type"] == "challenge"):
                # If the challenge is validated, accepts it
                if(self.validate_challenge_event(event)):
                    self.client.challenges.accept(event['challenge']['id'])
                    print_debug("Accepted challenge by" +
                        f"{event['challenge']['challenger']['id']}")
                else:  # Otherwise, declines it
                    self.client.challenges.decline(event['challenge']['id'])
                    print_debug("Declined challenge by" +
                        f"{event['challenge']['challenger']['id']}")

    def thread_update_ongoing_games(self):
        while(True):
            self.update_ongoing_games()
            time.sleep(1)

    def thread_games_handler(self):
        while(True):
            time.sleep(0.5)
            with(self.lock_ongoing_games):
                for game_id in self.ongoing_games.keys():
                    # Add thread to treat moves if not started yet
                    if(game_id not in self.thread_games):
                        # Adds game_id to ongoing game_ids threads
                        with(self.lock_thread_games):
                            self.thread_games.append(game_id)
                        # Starts thread to handle moves for game_id
                        self.start_thread(
                            self.thread_make_move_handler, args=(game_id, ))

                    # Gets opponent ID
                    player_id = self.ongoing_games[game_id]["opponent"]["id"]
                    try:
                        # Gets opponent player information
                        player = self.client.users.get_by_id(player_id)
                        # If opponent player is not online, resigns
                        if(not player[0]['online']):
                            print_debug(f"Opponent {player_id} offline."
                                + " Resigning", "DEBUG")
                            self.resign_game(game_id)
                    except Exception as e:
                        print_debug(f"Unable to get player {player_id}." 
                            + f" Exception: {e}")

    def thread_make_move_handler(self, game_id):
        while(True): # Runs ultil game has ended
            time.sleep(0.5)

            # If game has ended, stops while(True)
            with(self.lock_ongoing_games):
                if(game_id not in self.ongoing_games.keys()):
                    break

            with(self.lock_game_move_votes):
                # If move votes weren't created yet
                if(game_id not in self.game_move_votes.keys()):
                    continue

                # Gets list of voted moves
                moves = list(self.game_move_votes[game_id].keys())
                if(len(moves) == 0):
                    continue

                # Performs "random" voted move if mode is anarchy
                if(self.mode == 'anarchy'):
                    move = moves[0]
                    ret = self.make_move(game_id, move)
                    if(ret):# remove all votes if succeeded
                        self.game_move_votes[game_id] = {}
                    else: # remove move if not succeeded
                        del self.game_move_votes[game_id][move]
                # TODO: Democracy mode

        # Removes game from thread_games and finishes the thread
        with(self.lock_thread_games):
            self.thread_games.remove(game_id)
        print_debug(f'Finished game {game_id}', 'DEBUG')

    def validate_challenge_event(self, event):
        # The event must be a challenge, must not be rated and 
        # there must be no games going on
        with self.lock_ongoing_games:
            # Updates ongoing games to avoid concurrence problems
            self.update_ongoing_games()
            ret = len(self.ongoing_games) == 0
        ret = ret and event["type"] == "challenge" \
            and (not event["challenge"]["rated"])
        return ret

    def get_account_info(self):
        try:
            # Gets current user account info
            return self.client.account.get()
        except Exception as e:
            print_debug(f'Unable to get account info. Exception: {e}',
                'EXCEPTION')
            return None

    def vote_for_move(self, game_id, move):
        with(self.lock_game_move_votes):
            # Validates move
            if(not self.get_is_move_fmt_valid(move)):
                print_debug(f'Unable to vote for {move} in game {game_id}. ' +
                    'Invalid format.', 'DEBUG')
                return False

            # Parse from SAN to UCI if necessary
            if(not self.get_is_uci(move)):
                # Gets game current board (position)
                board = self.get_board_from_game(game_id)
                if(board is None):
                    print_debug(f'Unable to get board from {game_id}. ' + 
                        'Unable to make move', 'ERROR')
                try:
                    # Tries to make move, if not succeeded, move is invalid.
                    move = board.parse_san(move)
                except Exception as e:
                    print_debug(f'Unable to vote for {move} in game '
                        f'{game_id}. Exception: {e}', 'DEBUG')
                    return False

            # Creates dict of voted moves for game, if it does not exists
            if(game_id not in self.game_move_votes.keys()):
                self.game_move_votes[game_id] = dict()
            # Add move to list of voted moves, if not voted yet 
            if(move not in self.game_move_votes[game_id].keys()):
                self.game_move_votes[game_id][move] = 0
            # Votes for move
            self.game_move_votes[game_id][move] += 1

        print_debug(f'Voted for {move} in game {game_id}', 'DEBUG')
        return True

    def start_session(self):
        try:
            # Stablish session
            self.session = berserk.TokenSession(self.config['token'])
            # Stablish client
            self.client = berserk.Client(self.session)
            return True
        except Exception as e:
            print_debug(f'Unable to stablish session\nException: {e}',
                        'EXCEPTION')
            return None

    def get_move_from_msg(self, message, uci=False):
        # Messages must be as "e4" "Nc3" "e7e5", 
        # not "move Nc4" "e7 is a great move"
        if(" " in message):
            return None

        # Gets only UCI format
        if(uci):
            move = re.findall(r'[a-h][1-8][a-h][1-8]', message)
        else:
            # Gets any first word
            move = re.findall(r'[a-zA-Z0-9#+!?\-]+' , message)
        if(len(move) == 0):
            return None

        return move[0]

    def make_move(self, game_id, move):
        try:
            # Must recieve an UCI
            self.client.bots.make_move(game_id, move)
            return True
        except Exception as e:
            print_debug(f"Unable to make move {move} in game {game_id}."
                f" Exception: {e}", 'EXCEPTION')
            return False

    def get_is_move_fmt_valid(self, move):
        # If move is UCI, considers valid
        if(not self.get_is_uci(move)):
            # Tries to parse SAN move
            # PROBLEMS WITH CASTLING (0-0-0, 0-0)
            if(chess.SAN_REGEX.match(move) is None):
                return False
        return True

    def update_ongoing_games(self):
        try:
            with self.lock_ongoing_games:
                # First empty the dict of ongoing games
                self.ongoing_games = {}
                # Gets ongoing games
                games = self.client.games.get_ongoing()
                # Add all games to ongoing games dictionary
                for game in games:
                    self.ongoing_games[game['gameId']] = game

        except Exception as e:
            print_debug(f'Unable to get ongoing games\nException: {e}',
                        'EXCEPTION')

    def create_challenge(self, username, rated=True, clock_sec=180, 
                         clock_incr_sec=2):
        try:
            self.client.challenges.create(
                username, rated, clock_limit=clock_sec,
                clock_increment=clock_incr_sec)
            print_debug(f"Created challenge against {username}")

        except Exception as e:
            print_debug(f'Unable to create challenge. Exception: {e}', 
                'EXCEPTION')

    def seek_game(self, rated=True, clock_min=3, clock_incr_sec=2):
        try:
            # Tries to seek game. Unable to do so using BOT accounts :(
            r = requests.post("http://www.lichess.org/api/board/seek", 
                params={'rated': str(rated), 
                    'time': clock_min, 
                    'incremet': clock_incr_sec},
                headers={'Authorization': 'Bearer ' + self.config['token']})
            print(r.text)
        except Exception as e:
            print_debug(f'Unable to seek game. Exception: {e}', 'EXCEPTION')

    def is_my_turn(self, game_id):
        with self.lock_ongoing_games:
            if game_id in self.ongoing_games.keys():
                return self.ongoing_games[game_id]['isMyTurn']

    def resign_game(self, game_id):
        try:
            self.client.bots.resign_game(game_id)
            print_debug(f"Resigned in game {game_id}", "DEBUG")
        except Exception as e:
            print_debug(f"Unable to resign game {game_id}." 
                + f" Exception: {e}")

    def get_ongoing_game_ids(self):
        with self.lock_ongoing_games:
            return list(self.ongoing_games.keys())
    
    def get_board_from_game(self, game_id):
        with(self.lock_ongoing_games):
            # Check if game exists
            if(game_id in self.ongoing_games.keys()):
                # Gets game
                game = self.ongoing_games[game_id]
                # Creates a Board with the current FEN
                board = chess.Board(game['fen'])
                # Set current board turn
                board.turn = game['color'] == 'white'
                return board
        return None

    def get_is_uci(self, move):
        return BotChess.UCI_PATTERN.match(move)
