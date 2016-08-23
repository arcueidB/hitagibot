# -*- coding: utf-8 -*-
"""
Reminds users at a time they specify.
"""

import random

responses = ["Ok, I will remind you in", "I'll be sure to remind you in", "Expect to hear from me in",
             "I'll be sure to ping you in", "You will hear from me in", "You'll receive a notification in"]
prefixes = ['to', 'that']


def main(tg):
    """
    Routes api_object to appropriate method.
    """
    if tg.message:
        tg.send_chat_action('typing')
        if tg.plugin_data:
            answer_reminder(tg)
        else:
            reminder_time = added_time(tg.message['match'][0], tg.message['match'][1])
            if reminder_time and reminder_time <= 2147483647:
                set_reminder(tg, reminder_time + tg.message['date'])
            else:
                tg.send_message("Invalid Time :(")
    else:
        time_id = tg.callback_query['data'].replace('add', '')
        chat_id = tg.callback_query['message']['chat']['id']
        user_id = tg.callback_query['from']['id']
        if 'add' in tg.callback_query['data']:
            time_id = tg.callback_query['data'].replace('add', '')
            if check_user(time_id, chat_id, user_id, tg.database):
                return add_time_keyboard(tg, time_id)
        elif 'cancel' in tg.callback_query['data']:
            time_id = tg.callback_query['data'].replace('cancel', '')
            if check_user(time_id, chat_id, user_id, tg.database):
                return cancel_reminder(tg, time_id)
        elif '+' in tg.callback_query['data']:
            time_id = tg.callback_query['data'][3:]
            if check_user(time_id, chat_id, user_id, tg.database):
                return add_time(tg, time_id)
        tg.answer_callback_query("You are not the one who set the reminder")


def answer_reminder(tg):
    """
    Removes markup from reminder confirmation message and answers the reminder.
    Tries to send a message in both the chat and in pm.
    """
    user_id = tg.message['from']['id']
    statement = 'SELECT message_id FROM remind_plugin WHERE time_id="{}"'.format(tg.message['time_id'])
    tg.database.query(statement)
    query = tg.database.store_result()
    result = query.fetch_row(maxrows=0)
    message_id = result[0][0]
    tg.edit_message_reply_markup(message_id=message_id, chat_id=tg.message['chat']['id'])
    response = tg.send_message("Reminder:\n{}".format(tg.plugin_data))
    if response and not response['ok']:
        tg.send_message("Reminder:\n{}".format(tg.plugin_data), reply_to_message_id=None)
    if tg.message['from']['id'] != tg.message['chat']['id']:
        tg.send_message("Reminder:\n{}".format(tg.plugin_data), chat_id=user_id)


def set_reminder(tg, reminder_time):
    """
    Flags the reminder time and sends a confirmation
    """
    reminder_message = remove_prefix(tg.message['match'][2])
    time_id = tg.flag_time(reminder_time, reminder_message)

    message = create_message(tg.message)
    keyboard = [[{'text': "Cancel",
                  'callback_data': 'cancel{}'.format(time_id)}, {'text': "Add Time",
                                                                 'callback_data': 'add{}'.format(time_id)}]]
    keyboard = tg.inline_keyboard_markup(keyboard)
    message = tg.send_message(message, reply_markup=keyboard)
    if message['ok']:
        message_id = message['result']['message_id']
        user_id = tg.message['from']['id']
        chat_id = tg.message['chat']['id']
        tg.cursor.execute("INSERT INTO remind_plugin VALUES(%s, %s, %s, %s)", (time_id, user_id, chat_id, message_id))


def add_time_keyboard(tg, time_id):
    """
    Switches the keyboard for the user to add time
    """
    if 'add' in tg.callback_query['data']:
        tg.answer_callback_query()
        keyboard = [[{'text': "+5",
                      'callback_data': '+05{}'.format(time_id)}, {'text': "+15",
                                                                  'callback_data': '+15{}'.format(time_id)},
                     {'text': "+30",
                      'callback_data': '+30{}'.format(time_id)}, {'text': "+60",
                                                                  'callback_data': '+60{}'.format(time_id)}]]
        keyboard = tg.inline_keyboard_markup(keyboard)
        tg.edit_message_reply_markup(keyboard)


def cancel_reminder(tg, time_id):
    """
    Cancels a previous reminder
    """
    tg.answer_callback_query("Successfully Cancelled")
    tg.edit_message_text("Cancelled Reminder")
    tg.cursor.execute("DELETE FROM `flagged_time` WHERE time_id=%s", (time_id, ))


def check_user(time_id, chat_id, user_id, database):
    """
    Checks if the user who made the callback query is the one who set the reminder
    """
    statement = 'SELECT user_id FROM `remind_plugin` WHERE time_id="{}" AND chat_id={}'.format(time_id, chat_id)
    database.query(statement)
    query = database.store_result()
    result = query.fetch_row(maxrows=0)
    if result and result[0][0]:
        return True if result[0][0] == user_id else False
    else:
        return False


def add_time(tg, time_id):
    """
    Sets the keyboard back to default and adds time
    """
    time_id = tg.callback_query['data'][3:]
    time = int(tg.callback_query['data'][1:3])
    tg.answer_callback_query("Delayed the reminder by {} minutes!".format(time))
    keyboard = [[{'text': "Cancel",
                  'callback_data': 'cancel{}'.format(time_id)}, {'text': "Add Time",
                                                                 'callback_data': 'add{}'.format(time_id)}]]
    message = modify_message(tg.callback_query['message']['text'], time)
    tg.edit_message_text(message, reply_markup=tg.inline_keyboard_markup(keyboard))
    tg.cursor.execute("UPDATE `flagged_time` SET argument_time=DATE_ADD(argument_time, INTERVAL %s MINUTE) WHERE "
                      "time_id=%s", (int(time), time_id))


def added_time(time, unit):
    """
    Returns time to be added in seconds
    """
    time = float(time)
    if "m" in unit:
        multiplier = 60
    elif "h" in unit:
        multiplier = 3600
    elif "d" in unit:
        multiplier = 86400
    elif "w" in unit:
        multiplier = 604800
    if time:
        return int(time * multiplier)


def remove_prefix(message):
    """
    Removes prepositions from reminders
    """
    for prefix in prefixes:
        if message[:len(prefix) + 1] == prefix + ' ':
            return message[len(prefix) + 1:]
    return message


def create_message(message):
    """
    Creates a message which confirm a reminder has been set
    """
    time = float(message['match'][0])
    time = int(time) if time.is_integer() else time
    unit = None
    if message['match'][1] == 'm' or "min" in message['match'][1]:
        unit = "minute"
    elif message['match'][1] == 'h' or "hour" in message['match'][1]:
        unit = "hour"
    elif message['match'][1] == 'd' or "day" in message['match'][1]:
        unit = "day"
    elif message['match'][1] == 'w' or "week" in message['match'][1]:
        unit = "week"
    unit = unit if time == 1 else (unit + 's')
    return "{} {} {}".format(random.choice(responses), time, unit)


def modify_message(message, time):
    """
    Returns edited version of previous message with latest added time.
    """
    if '\n' not in message:
        message += '\n'
    else:
        message += ', '
    return message + "+{}".format(time)


def init_db(database):
    cursor = database.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS remind_plugin(time_id VARCHAR(128), user_id BIGINT NOT NULL, "
                   "chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL) CHARACTER SET utf8mb4;")
    cursor.close()


parameters = {
    'name': "Remind",
    'short_description':
    "The remind plugin gives you a notification at the time you specify",
    'long_description':
    "The remind plugins pings you at a time you specify. To set a reminder simply ask the bot. \n"
    "ie: Remind me in 30 minutes to take out the trash.",
    'permissions': True
}

arguments = {
    'text': [
        r"(?i)remind .* (\d+\.\d|\d+) ?(minutes?|mins?|hours?|days?|weeks?) (.*)",
        r"(?i)remind .* (\d+\.\d|\d+) ?([mhdw]) (.*)"
    ]
}
