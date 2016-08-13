# !/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Retrieves updates and routes them to appropriate classes/methods utilizing a system
of workers.
"""

import json
import time
import queue
import signal
from multiprocessing import Process, Value, Queue
from multiprocessing.dummy import Process as ThreadProcess

import MySQLdb
import certifi
import urllib3

import bot_init
from route_updates import RouteMessage, route_callback_query, route_inline_query
from tgapi import TelegramApi

BASE_URL = 'https://api.telegram.org/'
CONFIG, PLUGINS, EXTENSIONS = bot_init.master_mind()
SLEEP_TIME = float(CONFIG['BOT_CONFIG']['sleep'])
RUNNING = Value('i', True)  # If this is False workers shutdown safely

HTTP = urllib3.connection_from_url(BASE_URL, cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
HTTP.timeout = urllib3.Timeout(connect=1.0)
HTTP.retries = 3

API_TOKEN = CONFIG['BOT_CONFIG']['token']
MESSAGE_QUEUE = Queue()
# Stores all updates for workers to grab

GET_ME = HTTP.request('GET', "https://api.telegram.org/bot{}/getMe".format(API_TOKEN)).data
GET_ME = json.loads(GET_ME.decode('UTF-8'))
GET_ME.update({'date': int(time.time())})
# https://core.telegram.org/bots/api#getme

try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError
# Python 3.4 compatibility


def get_updates():
    """
    Grabs updates from the telegram server and places each update in MESSAGE_QUEUE.
    https://core.telegram.org/bots/api#getupdates
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    offset = 0
    url = "{}bot{}/getUpdates".format(BASE_URL, API_TOKEN)
    while RUNNING.value:
        fields = {'offset': offset, 'limit': 100, 'timeout': 10}
        try:
            update = HTTP.request('GET', url, fields)
        except urllib3.exceptions.HTTPError:
            time.sleep(SLEEP_TIME)
            continue

        if update.status == 200:
            try:
                update = json.loads(update.data.decode('UTF-8'))
            except JSONDecodeError:
                time.sleep(SLEEP_TIME)
                continue
            if update['ok'] and update['result']:
                offset = update['result'][-1]['update_id'] + 1
                for update in update['result']:
                    MESSAGE_QUEUE.put(update)


def process_updates():
    """
    Decides which type the update is and routes it to the appropriate route_updates
    method and launches a thread for the run_extensions method.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    plugin_http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
    plugin_http.timeout = urllib3.Timeout(connect=1.0)
    plugin_http.retries = 3
    update_router = RouteMessage(PLUGINS, plugin_http, GET_ME, CONFIG)
    while RUNNING.value:
        try:
            update = MESSAGE_QUEUE.get_nowait()
        except queue.Empty:
            continue
        extension_thread = ThreadProcess(target=run_extensions, args=(update, ))
        extension_thread.start()
        if 'message' in update:
            update_router.route_update(update['message'])
        elif 'edited_message' in update:
            update_router.route_update(update['edited_message'])
        elif 'callback_query' in update:
            route_callback_query(PLUGINS, GET_ME, CONFIG, plugin_http, update['callback_query'])
        elif 'inline_query' in update:
            route_inline_query(PLUGINS, GET_ME, CONFIG, plugin_http, update['inline_query'])
        extension_thread.join()
        time.sleep(SLEEP_TIME)


def run_extensions(update):
    """Runs all extensions with the given update"""
    extension_database = MySQLdb.connect(**CONFIG['DATABASE'])
    for module in EXTENSIONS:
        module.main(update, extension_database)
        extension_database.commit()
    extension_database.close()


def check_time_args():
    """
    Continuously checks the MySQL database for time arguments and runs the relevant
    plugin. Creates a different api_object depending on whether it was initialized
    with a standard message or callback query.
    """
    database = MySQLdb.connect(**CONFIG['DATABASE'])
    cursor = database.cursor()
    flagged_time_http = urllib3.PoolManager(cert_reqs='CERT_REQUIRED', ca_certs=certifi.where())
    flagged_time_http.timeout = urllib3.Timeout(connect=1.0)
    flagged_time_http.retries = 3

    while RUNNING.value:
        database.query("SELECT time_id, plugin_name,plugin_data,previous_message FROM flagged_time WHERE "
                       "argument_time <= from_unixtime({})".format(int(time.time())))

        query = database.store_result()
        rows = query.fetch_row(how=1, maxrows=0)
        for result in rows:
            time_id = result['time_id']
            plugin_name = result['plugin_name']
            if result['plugin_data']:
                plugin_data = json.loads(result['plugin_data'])
            else:
                plugin_data = None
            previous_message = json.loads(result['previous_message'])
            previous_message['time_id'] = time_id
            if 'message_id' in previous_message:
                api_object = TelegramApi(
                    database,
                    GET_ME,
                    plugin_name,
                    CONFIG,
                    flagged_time_http,
                    message=previous_message,
                    plugin_data=plugin_data)
            else:
                api_object = TelegramApi(
                    database,
                    GET_ME,
                    plugin_name,
                    CONFIG,
                    flagged_time_http,
                    callback_query=previous_message,
                    plugin_data=plugin_data)
            cursor.execute('DELETE FROM `flagged_time` WHERE time_id=%s;', (time_id, ))
            try:
                PLUGINS[plugin_name].main(api_object)
            except KeyError:
                continue
        database.commit()
        time.sleep(SLEEP_TIME)
    database.close()


def main():
    """
    Creates instances of the above methods and occassionally checks for crashed
    worker processes & relaunches.
    """
    worker_process = list()
    get_update_process = Process(target=get_updates)
    get_update_process.start()
    for i in range(0, int(CONFIG['BOT_CONFIG']['workers'])):
        worker_process.append(Process(target=process_updates))
        worker_process[i].start()
    time_worker = ThreadProcess(target=check_time_args)
    time_worker.start()
    while RUNNING.value:
        for index, worker in enumerate(worker_process):
            if not worker.is_alive():
                del worker_process[index]
                worker_process.append(Process(target=process_updates))
                worker_process[-1].start()
        if not time_worker.is_alive():
            time_worker = ThreadProcess(target=check_time_args)
            time_worker.start()
        if not get_update_process.is_alive():
            get_update_process = Process(target=get_updates)
            get_update_process.start()
    get_update_process.join()
    time_worker.join()
    for worker in worker_process:
        worker.join()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nShutting Down.....")
        RUNNING.value = 0
