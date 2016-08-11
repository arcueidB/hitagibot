# -*- coding: utf-8 -*-
"""
Allows chat admins to kick and warn chat members.
"""

import datetime
import uuid


def main(tg):
    """
    Routes a message to appropriate method
    """
    if tg.message['time_id']:
        unban_member(tg)
    elif check_message(tg):
        if 'reply_to_message' in tg.message:
            if tg.message['matched_regex'] in arguments['text'][0:2]:
                warn_user(tg)
            else:
                kick_user(tg)


def warn_user(tg):
    """
    Warns a user. Kicks if necessary.
    """
    max_warnings = 3
    first_name = tg.message['reply_to_message']['from']['first_name']

    warn_id = str(uuid.uuid4())
    user_id = tg.message['reply_to_message']['from']['id']
    warned_by_id = tg.message['from']['id']
    warned_message_id = tg.message['reply_to_message']['message_id']
    chat_id = tg.message['chat']['id']
    warning_time = tg.message['date']
    if tg.message['matched_regex'] == arguments['text'][1]:
        warning_reason = tg.message['match']
    else:
        warning_reason = None
    active_warning = True

    values = (warn_id, user_id, warned_by_id, warned_message_id, chat_id, warning_time, warning_reason, active_warning)
    tg.cursor.execute("INSERT INTO warnings VALUES(%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s)", values)

    tg.database.query("SELECT COUNT(*) FROM warnings WHERE user_id={} AND chat_id={} AND active_warning=1".format(
        user_id, chat_id))
    query = tg.database.store_result()
    rows = query.fetch_row()
    warning_count = rows[0][0]

    if warning_count >= max_warnings:
        kick_user(tg, from_warning=True)
    else:
        remaining_warnings = max_warnings - warning_count
        message = "{} has been warned. ".format(first_name)
        if remaining_warnings == 1:
            message += "1 warning remaining."
        else:
            message += "{} warnings remaining.".format(remaining_warnings)
        tg.send_message(message)


def kick_user(tg, from_warning=False):
    """
    Kicks a user based on inputed time or total kick infractions.
    """
    stepping_stones = [10800, 43200, 86400, 259200, 604800, 1209600]

    first_name = tg.message['reply_to_message']['from']['first_name']
    kick_id = None
    user_id = tg.message['reply_to_message']['from']['id']
    kicked_by_id = tg.message['from']['id']
    kicked_message_id = tg.message['reply_to_message']['message_id']
    chat_id = tg.message['chat']['id']
    kicked_time = tg.message['date']
    kicked_duration = None
    kicked_reason = None
    active_kick = 1

    tg.database.query("SELECT COUNT(*) FROM kicks WHERE user_id={} AND chat_id={} AND active_kick=1".format(user_id,
                                                                                                            chat_id))
    query = tg.database.store_result()
    rows = query.fetch_row()
    kick_count = rows[0][0]
    try:
        kicked_duration = stepping_stones[kick_count]
        if kicked_duration <= 0:
            tg.send_message("Invalid time")
            return
    except IndexError:
        kicked_duration = -1

    kick = tg.kick_chat_member(user_id)
    if not kick or not kick['ok']:
        if from_warning:
            tg.send_message("{} has reached the maximum warning count but I was unable to kick them.".format(
                first_name))
        else:
            tg.send_message("It seems I'm not an admin or this person isn't here anymore :(")
        return

    if kicked_duration > 0:
        if from_warning:
            kicked_reason = "MAX WARNINGS"
            time_stamp = datetime.datetime.fromtimestamp(kicked_time + kicked_duration).strftime('%Y-%m-%d %H:%M')
            tg.send_message("{} has reached the maximum warning count. They will be unbanned on {}. "
                            "Sayonara \U0001F44B".format(first_name, time_stamp))
        else:
            if tg.message['matched_regex'] in arguments['text'][3:5]:
                kicked_duration = determine_duration(tg.message['match'][0], tg.message['match'][1])
                kicked_reason = tg.message['match'][2]
            elif tg.message['matched_regex'] == arguments['text'][5]:
                kicked_reason = tg.message['match']
            time_stamp = datetime.datetime.fromtimestamp(kicked_time + kicked_duration).strftime('%Y-%m-%d %H:%M')
            tg.send_message("Successfully kicked {}. You will recieve a reminder to add them on {} (UTC)".format(
                first_name, time_stamp))

        kick_id = tg.flag_time(kicked_time + kicked_duration)
        values = (kick_id, user_id, kicked_by_id, kicked_message_id, chat_id, kicked_time, kicked_duration,
                  kicked_reason, active_kick)
        tg.cursor.execute("INSERT INTO kicks VALUES(%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s, %s, %s)", values)
        tg.cursor.execute("UPDATE warnings SET active_warning=0")
    elif kicked_duration == 0:
        tg.send_message("{} has been kicked".format(first_name))
        tg.unban_chat_member(user_id)
    elif kicked_duration == -1:
        tg.send_message("{} has been permanently banned.".format(first_name))


def unban_member(tg):
    """
    Unbans a member and alerts the chat
    """
    first_name = tg.message['reply_to_message']['from']['first_name']
    user_id = tg.message['reply_to_message']['from']['id']
    username = None
    tg.unban_chat_member(user_id)

    user_object = tg.get_chat_member(user_id)
    if user_object and user_object['ok']:
        if 'user_name' in user_object['result']['user']:
            username = user_object['result']['user']['username']
    elif 'username' in tg.message['reply_to_message']['from']:
        username = tg.message['reply_to_message']['from']['username']

    if username:
        message = "{}'s ({}) ban duration has ended. Please add them back.".format(first_name, username)
    else:
        message = "{}'s ban duration has ended. Please add them back.".format(first_name)
    tg.send_message(message, reply_to_message_id=None)


def check_message(tg):
    """
    Checks message and if user has permissions to kick
    """
    admins = tg.get_chat_administrators()
    user_id = tg.message['from']['id']
    if admins['ok']:
        admins = admins['result']
    else:
        return
    if any(user['user']['id'] == user_id for user in admins):
        if 'reply_to_message' in tg.message:
            user_id = tg.message['reply_to_message']['from']['id']
            if user_id == tg.get_me['result']['id']:
                tg.send_message("You can't kick/warn me :'(")
            elif not any(user['user']['id'] == user_id for user in admins):
                return True
            elif user_id == tg.message['from']['id']:
                tg.send_message("You can't kick/warn yourself :(")
            else:
                tg.send_message("You can't kick/warn another admin")
        else:
            tg.send_message("This command only works by reply :(")


def determine_duration(duration, unit):
    """
    Determines how much time a user should be kicked
    """
    if 'm' in unit:
        scale = 60
    elif 'h' in unit:
        scale = 3600
    elif 'd' in unit:
        scale = 86400
    elif 'w' in unit:
        scale = 604800
    return int(float(duration) * scale)


def init_db(database):
    """
    Create warning and kick tables
    """
    cursor = database.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS warnings(warn_id VARCHAR(80) NOT NULL UNIQUE, user_id BIGINT NOT NULL, "
                   "warned_by_id BIGINT NOT NULL, warned_message_id BIGINT NOT NULL, chat_id BIGINT NOT NULL, "
                   "warning_time DATETIME NOT NULL, warning_reason TEXT, active_warning TINYINT NOT NULL)")
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS kicks(kick_id VARCHAR(80), user_id BIGINT NOT NULL, "
        "kicked_by_id BIGINT NOT NULL, kicked_message_id BIGINT, chat_id BIGINT NOT NULL, kicked_time DATETIME NOT "
        "NULL, kicked_duration BIGINT NOT NULL,kicked_reason TEXT, "
        "active_kick TINYINT NOT NULL);")
    cursor.close()


parameters = {'name': "Admin", 'short_description': "Kick and warn chat members in your group", 'permissions': 10}

arguments = {
    'text': [
        "^/warn$", "^/warn (.*)", "^/kick$", r"/kick (\d+\.\d|\d+) ?(minutes?|mins?|hours?|days?|weeks?) ?((.*)|$)",
        r"/kick (\d+\.\d|\d+) ?([mhdw]) ?((.*)|$)", "^/kick (.*)"
    ]
}
