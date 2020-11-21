import sqlite3
from datetime import datetime, timedelta

PATH_DB = "./db/database.db"


class DbHandler:
    def __init__(self, path=PATH_DB):
        self.path = path
        self.create_tables()

    def create_tables(self):
        self.conn = sqlite3.connect(self.path)

        cursor = self.conn.cursor()
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS votes (
            user VARCHAR(100),
            move VARCHAR(4),
            date_vote DATETIME,
            game VARCHAR(15));
        """
        )
        self.conn.commit()
        self.conn.close()

    def add_move_vote(self, user, move, datetime, game):
        self.conn = sqlite3.connect(self.path)

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO votes VALUES (?, ?, ?, ?)
        """,
            (user, move, datetime, game),
        )

        self.conn.commit()
        self.conn.close()

    def get_move_votes(self):
        self.conn = sqlite3.connect(self.path)
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM votes;
        """
        )
        res = cursor.fetchall()
        self.conn.commit()
        self.conn.close()
        return res

    def get_number_of_votes(self, datetime_init, datetime_end):
        self.conn = sqlite3.connect(self.path)
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT user, COUNT(*) AS votes FROM votes
            WHERE strftime('%s', date_vote) BETWEEN strftime('%s', ?) AND strftime('%s', ?)
            GROUP BY user
            ORDER BY votes DESC;
        """,
            (datetime_init, datetime_end),
        )
        res = cursor.fetchall()
        self.conn.commit()
        self.conn.close()
        return res
