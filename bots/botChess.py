import time
from threading import Thread, Lock
from typing import Dict, List
import copy as cp

import requests
import chess
import re
import berserk

from lib.misc import print_debug, get_lichess_login_cookie, start_thread


class BotChess:

    UCI_PATTERN = re.compile("[a-h][1-8][a-h][1-8]")
    RESIGN_MOVE_STR = "resign"
    MIN_RESIGN_VOTES = 1
    MIN_RESIGN_PERCENTAGE_VOTES = 0.1

    # Interval without game to search for a new one
    INTERVAL_SEARCH_GAME = 120

    def __init__(self, config, bot_handler, mode="anarchy"):
        """ BotChess constructor
        
        Arguments:
            config {dict} -- Lichess API configuration ('token')
            bot_handler {BotHandler} -- Bot Handler to inform when a 
                move is made.
        
        Keyword Arguments:
            mode {str} -- Mode to process game move votes 
                (default: {'anarchy'})
        
        Raises:
            Exception: Unable to connect to Lichess API
        """

        self.config: Dict = config
        self.mode: str = mode
        self.bot_handler = bot_handler

        self.current_game: Dict = None
        self.lock_current_game = Lock()

        self.game_move_votes: Dict = {}
        self.lock_game_move_votes = Lock()

        ret = self.start_session()
        if not ret:
            raise Exception(
                "Unable to connect to lichess API. Check your personal token"
            )

        # Start threads
        start_thread(self.thread_make_move_handler)
        start_thread(self.thread_game_handler)
        start_thread(self.thread_treat_incoming_events)
        start_thread(self.thread_challenge_ai)

        time.sleep(5)

    def start_thread(self, thread_func, daemon=True, args=()):
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

    def thread_treat_incoming_events(self):
        """ Thread to treat incoming events from Lichess API """
        while True:
            try:
                for event in self.client.bots.stream_incoming_events():
                    self.treat_incoming_event(event)
            except Exception as e:
                print_debug(f"Exception in incoming events. Exception: {e}", "ERROR")
                time.sleep(1)

    def thread_challenge_ai(self):
        """ Thread for starting new game against AI given class rules """

        # Set last game ended now
        last_game = time.time()

        while True:
            time.sleep(1)

            # Check if there is an ongoing game
            if self.current_game is not None:
                # If there is an ongoing games, updates time last_game
                last_game = time.time()
            # If there are games and INTERVAL_SEARCH_GAME has passed from the
            # last game played, starts a new game against AI (or tries to)
            elif time.time() - last_game > BotChess.INTERVAL_SEARCH_GAME:
                self.create_challenge_ai()

    def thread_game_handler(self):
        """ Thread to handle current game 
            (resign, start other threads, etc.)
        """

        while True:
            time.sleep(0.5)

            # If there is no current game, waits...
            if self.current_game is None:
                continue

            # Gets opponent ID
            player_id = self.current_game["opponent"]["id"]
            # If ID is none, probably is playing against the
            # computer or anonymous session
            if player_id is None:
                continue

            try:
                # Gets opponent player information
                player = self.client.users.get_by_id(player_id)
                # If opponent player is not online, resigns
                if not player[0]["online"]:
                    print_debug(f"Opponent {player_id} offline. Resigning", "DEBUG")
                    self.resign_game()
            except Exception as e:
                print_debug(f"Unable to get player {player_id}. Exception: {e}")

    def thread_make_move_handler(self):
        """ Handle move votes and makes moves in current game """

        while True:  # Runs ultil game has ended
            time.sleep(0.5)

            # If there is no current game, waits...
            if self.current_game is None:
                continue

            moves = list(self.game_move_votes.keys())
            # If there are no move votes currently
            if len(moves) == 0:
                continue

            with (self.lock_game_move_votes):
                # Treats resign move vote
                if BotChess.RESIGN_MOVE_STR in moves:
                    # Get total number of votes
                    total_votes = sum([self.game_move_votes[m] for m in moves])
                    # Get number of resign votes
                    resign_votes = self.game_move_votes[BotChess.RESIGN_MOVE_STR]
                    # If there is more than the minimum resign votes and
                    # the percentage of resign votes is more than required,
                    # resigns the game
                    if (
                        total_votes >= BotChess.MIN_RESIGN_VOTES
                        and resign_votes / total_votes
                        >= BotChess.MIN_RESIGN_PERCENTAGE_VOTES
                    ):
                        self.resign_game()

                # Performs "random" voted move if mode is anarchy
                if self.mode == "anarchy":
                    move = moves[0]

                    # If the move chosen was to resign, but there is more than
                    # one move to choose, pick another
                    if move == BotChess.RESIGN_MOVE_STR:
                        if len(moves) >= 2:
                            move = moves[1]
                        else:  # If there is only resign move, continues
                            continue

                    # Makes move
                    ret = self.make_move(move)

                    with self.lock_game_move_votes:
                        if ret:  # remove all votes if succeeded
                            self.game_move_votes = {}
                        else:  # remove move if not succeeded
                            del self.game_move_votes[move]

                # TODO: Democracy mode

                # Resets the users that voted for a move in this game
                # because if it gets to here, a move was made or at least tried
                self.bot_handler.reset_users_voted_moves()

    def treat_incoming_event(self, event):
        """ Treats an incoming event from Lichess API

        Arguments:
            event {dict} -- Dictionary with event informations
        """

        # If the event is a challenge
        if event["type"] == "challenge":
            with self.lock_current_game:
                # Validate challenge to accept or decline it
                ret = self.validate_challenge_event(event)
                self.treat_challenge(event["challenge"]["id"], ret)

    def validate_challenge_event(self, event):
        """ Validates a challenge incming event, if it must be accepted
            or declined

        Arguments:
            event {dict} -- Dictionary with event informations

        Returns:
            bool -- True to accept, False to decline
        """

        # The event must be a challenge, must not be rated and
        # there must be no games going on
        if self.current_game is not None:
            return False
        ret = event["type"] == "challenge" and (not event["challenge"]["rated"])

        return ret

    def treat_challenge(self, id, accept, is_open=False):
        """ Accepts or decline a challenge from Lichess site

        Arguments:
            id {str} -- Challenge ID in Lichess
            accept {bool} -- True to accept challenge, False to decline 
                (default: {False})

        Keyword Arguments:
            is_open {bool} -- True if is an open challenge, False otherwise 
                (default: {False})

        Returns:
            bool -- True if success, False otherwise
        """

        try:
            if is_open:
                header = {
                    "cookie": get_lichess_login_cookie(),
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                r = requests.post(
                    f"https://lichess.org/challenge/{id}/accept", headers=header
                )
                if r.status_code != 200:
                    raise Exception(f"Unable to accept open challenge")
                print_debug(f"Accepted open challenge {id}", "INFO")
            else:
                if accept:
                    self.client.challenges.accept(id)
                    print_debug(f"Accepted challenge {id}.", "INFO")
                else:
                    self.client.challenges.decline(id)
                    print_debug(f"Declined challenge {id}.", "INFO")
        except Exception as e:
            print_debug(f"Unable to treat challenge {id}. Exception: {e}", "ERROR")
            return False
        return True

    def get_account_info(self):
        """ Get current account info

        Returns:
            dict or None -- Dictionary with account info or 
                None in case of error
        """

        try:
            # Gets current user account info
            return self.client.account.get()
        except Exception as e:
            print_debug(f"Unable to get account info. Exception: {e}", "ERROR")
            return None

    def vote_for_resign(self):
        """ Vote to resign in current game

        Returns:
            bool -- True
        """

        game_id = self.current_game["gameId"]
        with (self.lock_game_move_votes):
            # Creates 'resign' move for game_id, if it does not exists
            if BotChess.RESIGN_MOVE_STR not in self.game_move_votes.keys():
                self.game_move_votes[BotChess.RESIGN_MOVE_STR] = 0
            # Votes for resign
            self.game_move_votes[BotChess.RESIGN_MOVE_STR] += 1

            print_debug(f"Voted for resign in game {game_id}", "DEBUG")

        return True

    def vote_for_move(self, move):
        """ Votes for given move in given game
        
        Arguments:
            game_id {str} -- Game ID in Lichess
            move {str} -- Move in UCI or SAN
        
        Returns:
            (bool, str) -- (True, move) in case of success, 
                           (False, None) otherwise
        """

        game_id = self.current_game["gameId"]

        # Validates move notation
        if not self.get_is_move_fmt_valid(move):
            print_debug(
                f"Unable to vote for {move} in game {game_id}. " + "Invalid format.",
                "DEBUG",
            )
            return False, None

        # Parses castle from SAN to UCI
        if move == "0-0-0" or move.lower() == "o-o-o":
            color = self.get_color_in_current_game()
            if color == "white":
                move = "e1c1"
            elif color == "black":
                move = "e8c8"
        elif move == "0-0" or move.lower() == "o-o":
            color = self.get_color_in_current_game()
            if color == "white":
                move = "e1g1"
            elif color == "black":
                move = "e8g8"

        # Parse from SAN to UCI if necessary
        if not self.get_is_uci(move):
            # Gets game current board (position)
            board = self.get_board_from_game(game_id)
            if board is None:
                print_debug(
                    f"Unable to get board from {game_id}. " + "Unable to make move",
                    "ERROR",
                )
                return False, None
            try:
                # Tries to make move, if not succeeded, move is invalid.
                move = board.parse_san(move)
            except Exception as e:
                print_debug(
                    f"Unable to vote for {move} in game " f"{game_id}. Exception: {e}",
                    "ERROR",
                )
                return False, None

        with (self.lock_game_move_votes):
            # Add move to list of voted moves, if not voted yet
            if move not in self.game_move_votes.keys():
                self.game_move_votes[game_id][move] = 0
            # Votes for move
            self.game_move_votes[move] += 1

        print_debug(f"Voted for {move} in game {game_id}", "DEBUG")
        return True, move

    def start_session(self):
        """ Starts session with Lichess API

        Returns:
            bool -- True in case of success, False otherwise
        """

        try:
            # Stablish session
            self.session = berserk.TokenSession(self.config["token"])
            # Stablish client
            self.client = berserk.Client(self.session)
            return True
        except Exception as e:
            print_debug(f"Unable to stablish session\nException: {e}", "ERROR")
            return False

    def get_move_from_msg(self, message, uci=False):
        """ Gets move from message

        Arguments:
            message {str} -- Message to get move from

        Keyword Arguments:
            uci {bool} -- True to only get UCI moves (default: {False})

        Returns:
            str or None -- Move string or None in case it did not find move
        """

        # Messages must be as "e4" "Nc3" "e7e5",
        # not "move Nc4" "e7 is a great move"
        if " " in message:
            return None

        # Gets only UCI format
        if uci:
            # TODO: use pattern in BotChes.UCI_PATTERN
            move = re.findall(r"[a-h][1-8][a-h][1-8]", message)
        else:
            # Gets any first word
            move = re.findall(r"[a-zA-Z0-9#+!?\-]+", message)
        if len(move) == 0:
            return None

        move = move[0]
        return move

    def make_move(self, move):
        """ Makes given move in current game

        Arguments:
            move {str} -- Move in UCI

        Returns:
            bool -- True in case of success, False otherwise
        """

        try:
            game_id = self.current_game["gameId"]
            # Must recieve an UCI
            self.client.bots.make_move(game_id, move)
            return True
        except Exception as e:
            print_debug(
                f"Unable to make move {move} in game {game_id}." f" Exception: {e}",
                "ERROR",
            )
            return False

    def get_is_move_fmt_valid(self, move):
        """ Check if move string format is valid

        Arguments:
            move {str} -- Move string

        Returns:
            bool -- True if move format is valid, False otherwise
        """

        # If move is UCI, considers valid
        if not self.get_is_uci(move):
            # Tries to parse SAN move
            # PROBLEMS WITH CASTLING (0-0-0, 0-0)
            if chess.SAN_REGEX.match(move) is None and move.lower() not in (
                "0-0-0",
                "0-0",
                "o-o-o",
                "o-o",
            ):
                return False
        return True

    def create_challenge(
        self, username=None, rated=False, clock_sec=None, clock_incr_sec=None
    ):
        """ Creates challenge against user with given parameters

        Keyword Arguments:
            username {str} -- User to create challenge against or None to
                open challenge (default: {None})
            rated {bool} -- Game is rated or not (default: {False})
            clock_sec {int} -- Clock time in seconds or None for 
                correspondence (default: {None})
            clock_incr_sec {int} -- Clock increment in seconds 
                or None for no increment (default: {None})

        Returns:
            dict -- Challenge info in dictionary or None in case of error
        """

        try:
            if username is not None:
                r = self.client.challenges.create(
                    username,
                    rated=rated,
                    clock_limit=clock_sec,
                    clock_increment=clock_incr_sec,
                )
                print_debug(f"Created challenge against {username}", "INFO")
                return r
            else:
                r = self.client.challenges.create_open(
                    clock_limit=clock_sec, clock_increment=clock_incr_sec
                )
                print_debug(
                    "Created open challenge " + f"in {r['challenge']['url']}", "INFO"
                )
                return r
        except Exception as e:
            print_debug(f"Unable to create challenge. Exception: {e}", "ERROR")
            return None

    def create_challenge_ai(self, level=6, clock_sec=None, clock_incr_sec=None):
        """ Start a new correspondence game against Lichess AI

        Keyword Arguments:
            level {int} -- AI level, 1 to 8 (default: {6})
            clock_sec {int} -- Clock time in seconds or None for 
                correspondence (default: {None})
            clock_incr_sec {int} -- Clock increment in seconds 
                or None for no increment (default: {None})

        Returns:
            dict -- Challenge info in dictionary or None in case of error
        """

        print_debug("Starting new game against AI", "INFO")

        try:
            return self.client.challenges.create_ai(
                level=level, clock_limit=clock_sec, clock_increment=clock_incr_sec
            )
        except Exception as e:
            print_debug(f"Unable to start new game against AI. Exception: {e}", "ERROR")
        return None

    def is_my_turn(self):
        """ Get if is my turn in current game

        Returns:
            bool -- True if it is my turn, False otherwise
        """

        if self.current_game is None:
            return False
        return self.current_game["isMyTurn"]

    def resign_game(self):
        """ Resign in current game

        Returns:
            bool -- True in case of success, False otherwise
        """

        try:
            game_id = self.current_game["gameId"]
            self.client.bots.resign_game(game_id)
            print_debug(f"Resigned in game {game_id}", "DEBUG")
            with self.lock_current_game:
                self.current_game = None
                self.bot_handler.update_game_id(None)
            return True
        except Exception as e:
            print_debug(f"Unable to resign game {game_id}." + f" Exception: {e}")
            return False

    def get_color_in_current_game(self):
        """ Gets color in current game

        Returns:
            str or None -- 'white' or 'black' or None in case there is no game
        """

        if self.current_game is None:
            return None
        return self.current_game["color"]

    def get_id_last_game_played(self):
        """ Get Lichess game ID of the last game played
        
        Returns:
            str -- Lichess game ID
        """

        account = self.get_account_info()
        games = self.client.games.export_by_player(account["username"], max=1)
        for game in games:
            return game["id"]

    def get_board_from_current_game(self):
        """ Gets board from given game

        Returns:
            chess.Board or None -- Game board in case of success, 
                None otherwise
        """

        if self.current_game is None:
            return None

        try:
            board = chess.Board(self.current_game["fen"])
            board.turn = self.current_game["color"] == "white"
            return board
        except Exception as e:
            print_debug(f"Unable to get current board. Exception {e}", "ERROR")
            return None

    def get_is_uci(self, move):
        """ Check if move string is UCI
        
        Arguments:
            move {str} -- Move string
        
        Returns:
            bool -- True if it is UCI move, False otherwise
        """
        return BotChess.UCI_PATTERN.match(move)
