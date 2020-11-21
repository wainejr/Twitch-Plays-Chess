import os
from datetime import datetime, timedelta

abs_path = os.path.dirname(os.path.abspath(__file__))
import json
import obspython as obs


##########################################################################
# COPIED FROM db/dbHandler.py
# I know, it's pretty ugly. Blame on OBS
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


##########################################################################

rel_path_db = "../db/database.db"

source_users_name = ""
interval = 5
source_n_votes_name = ""
number_voters = 10
db_handler = DbHandler(os.path.join(abs_path, rel_path_db))


def update_curr_text(source, new_text):
    try:
        settings = obs.obs_data_create()
        obs.obs_data_set_string(settings, "text", new_text)
        obs.obs_source_update(source, settings)
        obs.obs_data_release(settings)

    except Exception as e:
        obs.script_log(obs.LOG_WARNING, str(e))
        obs.remove_current_callback()


# ------------------------------------------------------------


def update_text():
    global source_users_name
    global interval
    global source_n_votes_name
    global number_voters
    global db_handler

    votes = db_handler.get_number_of_votes(
        datetime.utcnow() - timedelta(days=30), datetime.utcnow()
    )
    print(votes)

    # trim username in 16 characters
    users = [v[0][:16] for v in votes][0:number_voters]
    n_votes = [str(v[1]) for v in votes][0:number_voters]

    source = obs.obs_get_source_by_name(source_users_name)
    if source is not None:
        string = "\n".join(users) + "\n" + " " * 32
        update_curr_text(source, string)
        obs.obs_source_release(source)

    source = obs.obs_get_source_by_name(source_n_votes_name)
    if source is not None:
        string = "\n".join(n_votes)
        update_curr_text(source, string)
        obs.obs_source_release(source)


def refresh_pressed(props, prop):
    update_text()


# ------------------------------------------------------------


def script_description():
    return "Updates number of votes, reading data from database\n\nby Waine"


def script_update(settings):
    global source_users_name
    global interval
    global source_n_votes_name
    global number_voters

    interval = obs.obs_data_get_int(settings, "interval")
    source_users_name = obs.obs_data_get_string(settings, "source_users")
    source_n_votes_name = obs.obs_data_get_string(settings, "source_n_votes")
    number_voters = obs.obs_data_get_int(settings, "number_voters")

    obs.timer_remove(update_text)

    if source_users_name != "" or source_n_votes_name != "":
        obs.timer_add(update_text, interval * 1000)


def script_defaults(settings):
    obs.obs_data_set_default_int(settings, "interval", 5)
    obs.obs_data_set_default_int(settings, "number_voters", 10)


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_int(
        props, "interval", "Update Interval (seconds)", 5, 3600, 1
    )
    obs.obs_properties_add_int(props, "number_voters", "Number of voters", 10, 50, 1)

    p1 = obs.obs_properties_add_list(
        props,
        "source_users",
        "Users source",
        obs.OBS_COMBO_TYPE_EDITABLE,
        obs.OBS_COMBO_FORMAT_STRING,
    )
    p2 = obs.obs_properties_add_list(
        props,
        "source_n_votes",
        "Votes source",
        obs.OBS_COMBO_TYPE_EDITABLE,
        obs.OBS_COMBO_FORMAT_STRING,
    )

    sources = obs.obs_enum_sources()

    if sources is not None:
        for source in sources:
            source_id = obs.obs_source_get_unversioned_id(source)
            if source_id == "text_gdiplus":
                name = obs.obs_source_get_name(source)
                obs.obs_property_list_add_string(p1, name, name)
                obs.obs_property_list_add_string(p2, name, name)

        obs.source_list_release(sources)

    obs.obs_properties_add_button(props, "button", "Refresh", refresh_pressed)
    return props
