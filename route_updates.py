# -*- coding: utf-8 -*-
"""
Contains various methods which route messages to plugins.
"""

from concurrent.futures import ThreadPoolExecutor
import json
import re
import time
import traceback

import copy
import MySQLdb
import _mysql_exceptions

from inline import InlineCallbackQuery
from inline import TelegramInlineAPI
from tgapi import TelegramApi


class RouteMessage(object):
    """
    Routes standard telegram messages.
    https://core.telegram.org/bots/api#message
    """

    def __init__(self, plugins, http, get_me, config):
        self.plugins = plugins
        self.http = http
        self.get_me = get_me
        self.config = config
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.futures = list()
        self.message = None
        self.database = None
        self.cursor = None

    def route_update(self, message):
        """
        Removes bot username from messages and runs through appropriate methods.
        """
        self.message = message
        self.init_message()  # Sets some default parameters
        self.database = MySQLdb.connect(**self.config['DATABASE'])
        self.cursor = self.database.cursor()

        if 'text' in self.message and 'entities' in self.message:
            message = self.message['text']
            bot_name = '@' + self.get_me['result']['username']
            name_match = re.search('(?i)^(/[^ ]*){}'.format(bot_name), message)
            if name_match:
                self.message['text'] = message.replace(message[:name_match.end(0)],
                                                       message[:name_match.end(0) - len(bot_name)])
                self.message['cleaned_message'] = True

        if 'reply_to_message' in self.message:
            self.check_db_reply()
        elif not self.handle_plugins() and self.message['chat']['type'] == 'private':
            self.check_db_pm()
        self.executor.shutdown(wait=True)
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.futures = list()
        self.database.commit()
        self.database.close()

    def check_db_reply(self):
        """
        Checks if the recieved message is a reply to a message flagged by a
        plugin. If not it then runs the standard handle_plugins check.
        """
        chat_id = self.message['chat']['id']
        message_id = self.message['reply_to_message']['message_id']
        self.database.query("SELECT plugin_name, user_id, single_use, currently_active, plugin_data "
                            "FROM flagged_messages WHERE message_id={} AND chat_id={};".format(message_id, chat_id))
        query = self.database.store_result()
        rows = query.fetch_row(how=1, maxrows=0)
        for result in rows:
            if result['user_id'] and result['user_id'] != self.message['from']['id']:
                return False
            if result['single_use']:
                self.cursor.execute("DELETE FROM flagged_messages WHERE message_id=%s", (message_id, chat_id))
            self.message['flagged_message'] = True
            plugin_data = json.loads(result['plugin_data']) if result['plugin_data'] else None
            api_object = TelegramApi(self.database, self.get_me, result['plugin_name'], self.config, self.http,
                                     self.message, plugin_data)
            self.plugins[result['plugin_name']].main(api_object)
            self.database.commit()
        if not rows:
            self.handle_plugins()

    def check_db_pm(self):
        """
        Checks if there is a currently active flagged_message in the chat where
        the message was sent. In a private chat it is not necessary to reply to the
        flagged message for it to trigger.
        """
        chat_id = self.message['chat']['id']
        self.database.query("SELECT plugin_name, single_use, message_id, plugin_data FROM flagged_messages WHERE "
                            "chat_id={} AND currently_active=1".format(chat_id))
        query = self.database.store_result()
        rows = query.fetch_row(how=1, maxrows=0) if query else list()
        for result in rows:
            message_id = result["message_id"]
            if result['single_use']:
                self.cursor.execute("DELETE FROM flagged_messages WHERE message_id=%s AND chat_id=%s",
                                    (chat_id, message_id))
            plugin_data = json.loads(result['plugin_data']) if result['plugin_data'] else None
            self.message['flagged_message'] = True
            self.cursor.execute("UPDATE flagged_messages SET currently_active=FALSE WHERE chat_id=%s", (chat_id, ))
            self.database.commit()
            self.plugins[result['plugin_name']].main(
                TelegramApi(self.database, self.get_me, result['plugin_name'], self.config, self.http, self.message,
                            plugin_data))

    def handle_plugins(self):
        """
        Loops through the plugin arguments looking for a match
        and checks for pm_parameters. If a plugin is activated True is returned.
        """
        plugin_triggered = False
        if time.time() - self.message['date'] >= 180:
            return False
        for plugin_name, plugin_module in self.plugins.items():
            if self.plugin_check(plugin_name, plugin_module):
                plugin_triggered = True
            self.init_message()
        if self.check_pm_parameters():
            plugin_triggered = True
        return plugin_triggered

    def plugin_check(self, plugin_name, plugin_module):
        """
        Checks if the plugin has an arguments dictionary. If so match is checked
        for by the check_argument method. If a match is found it checks if the plugin
        is enabled in the chat then runs it and returns True.
        """
        if hasattr(plugin_module, 'arguments'):
            for key, value in plugin_module.arguments.items():
                if self.check_argument(key, value, self.message):
                    chat_id = self.message['chat']['id']
                    statement = 'SELECT plugin_status FROM `{}blacklist` WHERE plugin_name="{}";'
                    try:
                        self.database.query(statement.format(chat_id, plugin_name))
                    except _mysql_exceptions.ProgrammingError:
                        self.create_default_table()
                        self.database.query(statement.format(chat_id, plugin_name))
                    query = self.database.store_result()
                    result = query.fetch_row(how=1)
                    if result:
                        enabled = result[0]['plugin_status']
                    else:
                        enabled = self.add_plugin(plugin_name)
                    if enabled == 1:
                        message = copy.copy(self.message)
                        self.futures.append(self.executor.submit(self.run_plugin, plugin_name, plugin_module, message))
                        return True

    def check_argument(self, key, value, incremented_message):
        """
        Recursively loops through the argument and message until it reaches the
        end value or the key is not found in the message. Once the end value is reached
        it loops through each argument and return True is a match is found.
        """
        if key in incremented_message:
            if isinstance(value, list):
                incremented_message = incremented_message[key]
                return self.check_match(key, value, incremented_message)
            elif isinstance(value, dict):
                incremented_message = incremented_message[key]
                for key1, value1 in value.items():
                    if self.check_argument(key1, value1, incremented_message):
                        return True

    def check_match(self, key, values, incremented_message):
        """
        Simply returns True is a match is made or the argument contains a *
        """
        self.message['matched_argument'] = key
        if '*' in values:
            self.message['matched_regex'] = '*'
            return True
        for regex in values:
            match = re.findall(str(regex), str(incremented_message))
            if match:
                self.message['matched_regex'] = regex
                self.message['match'] = match[0]
                return True

    def check_pm_parameters(self):
        """
        Retrieves payload from pm_parameters and sends to relevant plugin
        https://core.telegram.org/bots/#deep-linking
        """
        if 'text' not in self.message:
            return
        match = re.findall("^/start (.*)", self.message['text'])
        if match:
            self.message['pm_parameter'] = match[0]
            self.database.query('SELECT plugin_name FROM pm_parameters WHERE parameter="{}"'.format(match[0]))
            query = self.database.store_result()
            result = query.fetch_row()
            for plugin in result:
                api_object = TelegramApi(self.database, self.get_me, plugin[0], self.config, self.http, self.message)
                self.plugins[plugin[0]].main(api_object)
            return True if result else False

    def add_plugin(self, plugin_name):
        """
        If a plugin has no entry in the chat blacklist this method will add the
        default value.
        """
        chat_name = "{}blacklist".format(self.message['chat']['id'])
        perms = self.plugins[plugin_name].parameters['permissions']
        if self.message['chat']['type'] == 'private':
            enabled = int(perms[1])
        else:
            enabled = int(perms[0])
        try:
            self.cursor.execute("INSERT INTO `{}` VALUES(%s, %s, 0000)".format(chat_name), (plugin_name, enabled))
        except _mysql_exceptions.IntegrityError:
            pass
        self.database.commit()
        return enabled

    def create_default_table(self):
        """
        When a chat has no blacklist this method will create a default table for
        it. Usually when the bot is first added to a group.
        """
        values = list()
        chat_name = "{}blacklist".format(self.message['chat']['id'])
        self.cursor.execute("CREATE TABLE `{}`(plugin_name VARCHAR(16) NOT NULL UNIQUE, "
                            "plugin_status BOOLEAN, set_by BIGINT) CHARACTER SET utf8mb4;".format(chat_name))
        for plugin_name, module in self.plugins.items():
            perms = module.parameters['permissions']
            if self.message['chat']['type'] == 'private':
                enabled = int(perms[1])
            else:
                enabled = int(perms[0])
            values.append((plugin_name, enabled))
        self.cursor.executemany("INSERT INTO `{}` VALUES(%s, %s, 0)".format(chat_name), values)
        self.database.commit()

    def run_plugin(self, plugin_name, plugin_module, message):
        """
        Inits a plugin with its own DB and commits/closes it after.
        Wrapped for concurrent.futures
        """
        database = MySQLdb.connect(**self.config['DATABASE'])
        api_object = TelegramApi(database, self.get_me, plugin_name, self.config, self.http, message)
        try:
            plugin_module.main(api_object)
        except Exception:
            admin_list = self.config['BOT_CONFIG']['admins'].split(',')
            for admin_id in admin_list:
                message = "<code>{}</code>".format(traceback.format_exc())
                api_object.forward_message(admin_id)
                api_object.send_message(message, chat_id=admin_id)
        database.commit()
        database.close()

    def init_message(self):
        """Sets some default values on a message"""
        self.message['flagged_message'] = None
        self.message['matched_regex'] = None
        self.message['matched_argument'] = None
        self.message['cleaned_message'] = False
        self.message['pm_parameter'] = False
        self.message['time_id'] = None


def route_callback_query(plugins, get_me, config, http, callback_query):
    """
    Routes a callback query to the appropriate plugin. Callback data is stored in mysql.
    https://core.telegram.org/bots/api#callbackquery
    """
    database = MySQLdb.connect(**config['DATABASE'])
    data = callback_query['data']
    query = 'SELECT plugin_name, plugin_data FROM callback_queries WHERE callback_data="{}"'
    database.query(query.format(data))
    query = database.store_result()
    rows = query.fetch_row(how=1, maxrows=0)
    for db_result in rows:
        plugin_name = db_result['plugin_name']
        plugin_data = json.loads(db_result['plugin_data']) if db_result['plugin_data'] else None
        if 'message' in callback_query:
            api_object = TelegramApi(
                database, get_me, plugin_name, config, http, plugin_data=plugin_data, callback_query=callback_query)
        else:
            api_object = InlineCallbackQuery(database, config, http, callback_query)
        try:
            plugins[plugin_name].main(api_object)
        except Exception:
            api_object = TelegramApi(database, get_me, plugin_name, config, http)
            send_error_report(data, traceback.format_exc(), api_object)
        database.commit()
        database.close()


def route_inline_query(plugins, get_me, config, http, inline_query):
    """
    Routes inline arguments to the appropriate plugin. Only the first match runs.
    https://core.telegram.org/bots/api#inlinequery
    """
    default_plugin = config['BOT_CONFIG']['default_inline_plugin']
    query = str(inline_query['query'])
    for plugin_name, plugin in plugins.items():
        if hasattr(plugin, 'inline_arguments'):
            for argument in plugin.inline_arguments:
                match = re.findall(str(argument), query)
                if match:
                    database = MySQLdb.connect(**config['DATABASE'])
                    inline_query['matched_regex'] = argument
                    inline_query['match'] = match[0]
                    try:
                        plugin.main(TelegramInlineAPI(database, get_me, plugin_name, config, http, inline_query))
                    except Exception:
                        api_object = TelegramApi(database, get_me, plugin_name, config, http)
                        send_error_report(query, traceback.format_exc(), api_object)
                    database.commit()
                    database.close()
                    return
    if default_plugin:
        database = MySQLdb.connect(**config['DATABASE'])
        inline_query['matched_regex'] = None
        inline_query['match'] = inline_query['query']
        try:
            plugins[default_plugin].main(TelegramInlineAPI(database, get_me, plugin_name, config, http, inline_query))
        except Exception:
            api_object = TelegramApi(database, get_me, plugin_name, config, http)
            send_error_report(query, traceback.format_exc(), api_object)
        database.commit()
        database.close()


def send_error_report(recieved, error, api_object):
    admin_list = api_object.config['BOT_CONFIG']['admins'].split(',')
    for admin_id in admin_list:
        message = "<b>Unhandled Exception</b>\n<b>Recieved:</b> {}\n\n<code>{}</code>".format(recieved, error)
        api_object.send_message(message, chat_id=admin_id)
