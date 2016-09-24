# -*- coding: utf-8 -*-

from datetime import datetime

import _mysql_exceptions

chat_id = int

types = ["audio", "document", "photo", "sticker", "video", "voice", "contact", "location", "venue", "text"]
pretty_types = ["Audio", "Documents", "Photos", "Stickers", "Videos", "Voice", "Contacts", "Locations", "Venues",
                "Text"]


def main(tg):
    global chat_id
    chat_id = tg.chat_data['chat']['id']
    if tg.message:
        tg.send_chat_action('typing')
        if tg.message['matched_regex'] == arguments['text'][1]:
            opt_out(tg)
        else:
            if check_status(tg.database):
                if tg.message['matched_regex'] == arguments['text'][0]:
                    chat_stats(tg)
                elif tg.message['matched_regex'] == arguments['text'][2]:
                    user_stats(tg)
                elif tg.message['matched_regex'] == arguments['text'][3]:
                    global_user_stats(tg)
            else:
                keyboard = [[{'text': 'Enable Stats', 'callback_data': '%%toggle_on%%'}]]
                message = "You are not opted into stat collection. A moderator can opt-in by clicking this button."
                tg.send_message(message, reply_markup=tg.inline_keyboard_markup(keyboard))
    elif tg.callback_query:
        if tg.callback_query['data'] == '%%toggle_on%%':
            opt_in(tg)
        elif tg.callback_query['data'] == '%%toggle_off%%':
            opt_out(tg)


def opt_in(tg):
    if check_status(tg.database):
        tg.answer_callback_query("Chat stats are already enabled!")
    elif check_if_mod(tg):
        user_id = tg.callback_query['from']['id']
        try:
            tg.cursor.execute("INSERT INTO chat_opt_status VALUES(%s, 1, %s, now())", (chat_id, user_id))
        except _mysql_exceptions.IntegrityError:
            tg.cursor.execute("UPDATE chat_opt_status SET status=1, toggle_user=%s, toggle_date=now()", (user_id, ))
        tg.answer_callback_query("You have opted in!")
        tg.edit_message_text(
            "You have successfully opted into stat collection."
            "You'll be able to see statistics shortly. Opt out at anytime using /chatstats opt-out",
            message_id=tg.callback_query['message']['message_id'])
    else:
        tg.answer_callback_query("Only moderators can enable chat stats!")


def opt_out(tg):
    if tg.callback_query:
        if check_if_mod(tg):
            tg.cursor.execute("DROP TABLE `{}stats`".format(chat_id))
            tg.cursor.execute("UPDATE chat_opt_status SET status=FALSE AND toggle_user=%s AND toggle_date=now() WHERE "
                              "chat_id=%s", (tg.callback_query['from']['id'], chat_id))
            tg.answer_callback_query()
            tg.edit_message_text(
                "You have successfully disabled statistics. All chat data has been deleted.",
                message_id=tg.callback_query['message']['message_id'])
        else:
            tg.answer_callback_query("Only mods can disable stats!")
    elif tg.message:
        tg.database.query("SELECT status FROM chat_opt_status WHERE chat_id={} AND status=TRUE".format(chat_id))
        try:
            query = tg.database.store_result()
        except _mysql_exceptions.OperationalError:
            tg.database.commit()
            opt_out(tg)
        rows = query.fetch_row()
        if rows:
            keyboard = [[{'text': 'Disable & Remove Stats', 'callback_data': '%%toggle_off%%'}]]
            tg.send_message(
                "Are you sure you want to opt-out? All chat data is deleted, this is irreversible.",
                reply_markup=tg.inline_keyboard_markup(keyboard))
        else:
            tg.send_message("You aren't currently opted in")
    return


def chat_stats(tg):
    total_messages, total_characters, average_chars, total_words = metrics(tg.database)
    message = "<b>Global Chat Statistics:</b>\n\n"
    message += "<b>Total Messages Sent:</b> {:,}".format(total_messages)
    if total_characters:
        message += "\n<b>Total Characters Sent:</b> {:,}".format(total_characters)
    message += "\n<b>Average Characters Per Message:</b> {0:.1f}".format(average_chars)

    message += "\n\n<b>Types of Messages Sent</b>"
    message_types = types_breakdown(tg.database)
    for msg_type, total in message_types.items():
        try:
            message += "\n<b>{}:</b> {:,}".format(pretty_types[types.index(msg_type)], total)
        except ValueError:
            continue
    message += hourly_time(total_messages, tg.database)
    tg.send_message(message)


def user_stats(tg):
    user_id = tg.message['reply_to_message']['from']['id'] if 'reply_to_message' in tg.message else \
        tg.message['from']['id']
    first_name = tg.message['reply_to_message']['from']['first_name'] if 'reply_to_message' in tg.message else \
        tg.message['from']['first_name']
    total_messages, total_characters, average_chars, total_words = metrics(tg.database, user_id)

    message = "<b>{}'s Chat Stats</b>\n\n".format(first_name)
    message += "<b>Total Messages Sent:</b> {:,}".format(total_messages)
    if total_characters:
        message += "\n<b>Total Characters Sent:</b> {:,}".format(total_characters)
    message += "\n<b>Average Characters Per Message:</b> {0:.1f}".format(average_chars)

    message += "\n\n<b>Types of Messages Sent</b>"
    message_types = types_breakdown(tg.database, user_id)
    for msg_type, total in message_types.items():
        try:
            message += "\n<b>{}:</b> {:,}".format(pretty_types[types.index(msg_type)], total)
        except ValueError:
            continue
    message += hourly_time(total_messages, tg.database, user_id)

    tg.send_message(message)


def global_user_stats(tg):
    tg.database.query("SELECT first_name, s.user_id, COUNT(*) as `message_count` FROM `{}stats` s "
                      "LEFT JOIN users_list u ON s.user_id = u.user_id GROUP BY user_id "
                      "ORDER BY message_count DESC;".format(chat_id))
    try:
        query = tg.database.store_result()
    except _mysql_exceptions.OperationalError:
        tg.database.commit()
        global_user_stats(tg)
    results = query.fetch_row(maxrows=0)
    text = "Global User Stats For Chat: {}\r\nGenerated On: {}\r\n".format(
        tg.message['chat']['title'], datetime.now().strftime("%A, %d. %B %Y %I:%M%p"))
    for rank, user in enumerate(results):
        first_name = user[0]
        if not first_name:
            chat_member = tg.get_chat_member(chat_id, user[1])
            chat_member = chat_member['result'] if chat_member and chat_member['ok'] else None
            if chat_member:
                first_name = None
                last_name = None
                user_name = None
                user_id = None
                if 'first_name' in chat_member:
                    first_name = chat_member['first_name']
                if 'last_name' in chat_member:
                    last_name = chat_member['last_name']
                if 'username' in chat_member:
                    user_name = chat_member['username']
                if 'id' in chat_member:
                    user_id = chat_member['id']
                try:
                    tg.cursor.execute("INSERT INTO users_list VALUES(%s, %s, %s, %s)",
                                      (user_id, first_name, last_name, user_name))
                except _mysql_exceptions.IntegrityError:
                    pass
            else:
                first_name = "Unknown"
                try:
                    tg.cursor.execute("INSERT INTO users_list(first_name, user_id) VALUES(%s, %s)",
                                      (first_name, user[1]))
                except _mysql_exceptions.IntegrityError:
                    pass
        if first_name != "Unknown":
            line = "\r\n{}. {} [{}] - {} messages".format(rank + 1, first_name, user[1], user[2])
            text += line.replace(u"\u200F", '')
    tg.send_document(('stats.txt', text))


def types_breakdown(database, user_id=None):
    """
    Returns totals of each message type
    """
    database.commit()
    message_types = dict()
    statement = "SELECT message_type, COUNT(*) FROM `{}stats`".format(chat_id)
    if user_id:
        statement += " WHERE user_id={}".format(user_id)
    statement += " GROUP BY message_type;"
    database.query(statement)
    try:
        query = database.store_result()
    except _mysql_exceptions.OperationalError:
        database.commit()
        return types_breakdown(database, user_id)
    rows = query.fetch_row(maxrows=0)
    for result in rows:
        message_types[result[0]] = result[1]
    return message_types


def metrics(database, user_id=None):
    """
    Returns total messages, total characters, average chat length, and average word count.
    """
    database.commit()
    statement = "SELECT COUNT(*), SUM(char_length), AVG(char_length), AVG(word_count) FROM `{}stats`".format(chat_id)
    if user_id:
        statement += " WHERE user_id={}".format(user_id)
    database.query(statement)
    try:
        query = database.store_result()
    except _mysql_exceptions.OperationalError:
        database.commit()
        return metrics(database, user_id)
    rows = query.fetch_row(maxrows=0)[0]
    return rows[0], rows[1], rows[2], rows[3]


def hourly_time(total, database, user_id=None):
    """
    Determines how many messages are sent within 4 6 hour time intervals
    """
    database.commit()
    if user_id:
        database.query("SELECT hour(time_sent), Count(*) FROM `{}stats` WHERE user_id={} "
                       "GROUP BY HOUR(time_sent);".format(chat_id, user_id))
    else:
        database.query("SELECT hour(time_sent), Count(*) FROM `{}stats` GROUP BY HOUR(time_sent);".format(chat_id))
    try:
        query = database.store_result()
    except _mysql_exceptions.OperationalError:
        database.commit()
        return hourly_time(database, user_id)
    rows = query.fetch_row(maxrows=0)
    times = {'0to6': 0, '6to12': 0, '12to18': 0, '18to0': 0}
    for result in rows:
        if result[0] < 6:
            times['0to6'] += result[1]
        elif result[0] < 12:
            times['6to12'] += result[1]
        elif result[0] < 18:
            times['12to18'] += result[1]
        else:
            times['18to0'] += result[1]
    return parse_times(total, times)


def parse_times(total, times):
    """
    Creates formatted message displaying times with percentage of activity
    """
    message = "<b>\n\nActivity By Time</b>"
    message += "\n<b>00:00 - 06:00:</b> {:.1f}%".format((times['0to6'] / total) * 100)
    message += "\n<b>06:00 - 12:00:</b> {:.1f}%".format((times['6to12'] / total) * 100)
    message += "\n<b>12:00 - 18:00:</b> {:.1f}%".format((times['12to18'] / total) * 100)
    message += "\n<b>18:00 - 00:00:</b> {:.1f}%".format((times['18to0'] / total) * 100)
    return message


def check_status(database):
    """
    Check is a chat is opted into stat collection
    """
    database.query("SELECT status FROM chat_opt_status WHERE status=True and chat_id={}".format(chat_id))
    try:
        query = database.store_result()
    except _mysql_exceptions.OperationalError:
        database.commit()
        return check_status(database)
    rows = query.fetch_row()
    return True if rows else False


def check_if_mod(tg):
    """
    Check if a user is a moderator of the current chat
    """
    admins = tg.get_chat_administrators()
    user_id = tg.callback_query['from']['id']
    if admins['ok']:
        admins = admins['result']
    else:
        return
    if any(user['user']['id'] == user_id for user in admins):
        return True


parameters = {
    'name': "Stats",
    'short_description': "Chat and user message statistics",
    'long_description':
    "View the most active users, activity breakdowns, and a variety of other metrics by opting into"
    " message collection. The actual contents of a message are not logged by the bot. You can opt-"
    "out and delete prior data using <code>/chatstats opt-out.</code>",
    'permissions': '10'
}

arguments = {'text': ["^/chatstats$", "^/chatstats opt-out$", "^/stats$", "^/userstats$"]}
