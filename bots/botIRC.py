import socket
import sys
import re
import time

from lib.misc import print_debug


class BotIRC:

    socket_retry_count = 0

    def __init__(self, config):
        self.config = config
        self.sock = None
        self.set_socket_object()

    def set_socket_object(self):
        """ Sets socket object """

        self.username = self.config["account"]["username"].lower()
        self.password = self.config["account"]["password"]

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.sock.settimeout(10)

        server = self.config["irc"]["server"]
        port = self.config["irc"]["port"]

        try:
            self.sock.connect((server, port))
        except BaseException:
            print_debug(
                "Error connecting to IRC server. ({}:{}) ({})".format(
                    server, port, self.socket_retry_count + 1
                ),
                "error",
            )

            if BotIRC.socket_retry_count < 2:
                BotIRC.socket_retry_count += 1
                return self.set_socket_object()
            else:
                sys.exit()

        self.sock.settimeout(None)

        self.sock.send(bytes(f"USER {self.username}\r\n", encoding="utf-8"))
        self.sock.send(bytes(f"PASS {self.password}\r\n", encoding="utf-8"))
        self.sock.send(bytes(f"NICK {self.username}\r\n", encoding="utf-8"))

        if not self.check_login_status(self.recv()):
            print_debug("Invalid login.", "ERROR")
            sys.exit()
        else:
            print_debug("Login successful!")

        self.sock.send(bytes(f"JOIN #{self.username}\r\n", encoding="utf-8"))
        print_debug(f"Joined #{self.username}")

    def ping(self, data):
        """ Pings socket
        
        Arguments:
            data {bytes} -- Data to ping
        """

        if data.startswith("PING"):
            self.sock.send(bytes(data.replace("PING", "PONG"), encoding="utf-8"))

    def recv(self, amount=1024):
        """ Recieves data from socket with given ammount size
        
        Keyword Arguments:
            amount {int} -- Data ammount size (default: {1024})
        
        Returns:
            str -- Bytes recieved in 'utf-8'
        """

        return self.sock.recv(amount).decode("utf-8")

    def send_message(self, data, delay=0):
        time.sleep(delay)
        self.sock.send(bytes(f"PRIVMSG #{self.username} :{data}\r\n", encoding="utf-8"))

    def recv_messages(self, amount=1024):
        """ Recieves messages from socket and parses it
        
        Keyword Arguments:
            amount {int} -- Data ammount size (default: {1024})
        
        Returns:
            list(dict) -- List of parsed messages
        """
        data = self.recv(amount)

        if not data:
            print_debug("Lost connection, reconnecting.", "ERROR")
            return self.set_socket_object()

        self.ping(data)

        if self.check_has_message(data) is not None:
            return [
                self.parse_message(line) for line in filter(None, data.split("\r\n"))
            ]
        return None

    def check_login_status(self, data):
        """ Check if login was successful or not

        Arguments:
            data {str} -- Data recieved from socket

        Returns:
            bool -- True in case of successful login, False otherwise
        """

        if not re.match(
            r"^:(testserver\.local|tmi\.twitch\.tv)"
            + r" NOTICE \* :Login unsuccessful\r\n$",
            data,
        ):
            return True
        return False

    def check_has_message(self, data):
        """ Check if given data has message

        Arguments:
            data {str} -- Data to checkc

        Returns:
            Match object or None -- Match object if message was found, 
                None otherwise
        """
        return re.match(
            r"^:[a-zA-Z0-9_]+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]"
            + r"+(\.tmi\.twitch\.tv|\.testserver\.local) "
            + r"PRIVMSG #[a-zA-Z0-9_]+ :.+$",
            data,
        )

    def parse_message(self, data):
        """ Parses message from given data
        
        Arguments:
            data {str} -- Message to parse
        
        Returns:
            dict -- Dictionary as {'channel': channel,
                'username': username,
                'message': message}
        """

        return {
            "channel": re.findall(
                r"^:.+\![a-zA-Z0-9_]+@[a-zA-Z0-9_]" + r"+.+ PRIVMSG (.*?) :", data
            )[0],
            "username": re.findall(r"^:([a-zA-Z0-9_]+)\!", data)[0],
            "message": re.findall(r"PRIVMSG #[a-zA-Z0-9_]+ :(.+)", data)[0],
        }
