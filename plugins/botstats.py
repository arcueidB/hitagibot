# -*- coding: utf-8 -*-

import math
import time
import _mysql_exceptions


def main(tg):
    if str(tg.chat_data['from']['id']) in tg.config['BOT_CONFIG']['admins']:
        tg.send_chat_action('typing')
        tg.database.query("SELECT chat_id FROM chat_opt_status WHERE status=1;")
        query = tg.database.store_result()
        chat_list = query.fetch_row(maxrows=0)
        total_messages = 0
        opted_in_count = len(chat_list)
        for chat in chat_list:
            try:
                tg.database.query("SELECT COUNT(*) FROM `{}stats`;".format(chat[0]))
            except _mysql_exceptions.ProgrammingError:
                continue
            query = tg.database.store_result()
            message_count = query.fetch_row(maxrows=0)
            total_messages += message_count[0][0]

        tg.database.query("SELECT COUNT(*) FROM chats_list;")
        query = tg.database.store_result()
        result = query.fetch_row(maxrows=0)
        chat_total = result[0][0]

        tg.database.query("SELECT COUNT(*) FROM users_list;")
        query = tg.database.store_result()
        result = query.fetch_row(maxrows=0)
        user_total = result[0][0]

        message = "<code>Total Chats: {:,}".format(chat_total)
        message += "\nTotal Users: {:,}".format(user_total)
        message += "\nTracked Chats: {:,}".format(opted_in_count)
        message += "\nMessage Count: {:,}".format(total_messages)
        message += "\nUp for: {}</code>".format(parse_date(tg.get_me['date']))

        tg.send_message(message)


def parse_date(start_time):
    time_up = int(time.time()) - start_time
    hours = minutes = 0
    if time_up > 3600:
        hours = math.floor(time_up / 3600)
    if time_up > 60:
        minutes = (time_up % 3600) / 60
    return "{0:02.0f}:{1:02.0f}".format(hours, minutes)


parameters = {'name': "Bot Statistics", 'short_description': "View bot statistics", 'permissions': "11", 'hidden': True}

arguments = {'text': ["^/botstats$"]}
