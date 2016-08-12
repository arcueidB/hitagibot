# -*- coding: utf-8 -*-
"""
Helps a user learn about the bots functions.
Arguments:
    /help
    /help plugin-name
"""


def main(tg):
    """
    Returns a message with plugin pretty names as buttons or routes the message to grab_plugin.
    """
    if tg.message and tg.message['matched_regex'] == arguments['text'][0]:
        tg.send_chat_action('typing')
        tg.database.query("SELECT pretty_name FROM `plugins` p LEFT JOIN `{}blacklist` b ON p.plugin_name=b.plugin_name"
                          " WHERE hidden=0 AND b.plugin_status=1 OR p.inline_only=1;".format(tg.message['chat']['id']))
        query = tg.database.store_result()
        rows = query.fetch_row(how=1, maxrows=0)
        keyboard = []
        remaining = len(rows)
        for plugin in rows:
            pretty_name = plugin['pretty_name']
            row_length = 3 if remaining >= 3 or remaining == 1 else 2
            button = {'text': pretty_name, 'callback_data': '%%help%%{}'.format(pretty_name)}
            if keyboard and len(keyboard[-1]) < row_length:
                keyboard[-1].append(button)
            else:
                keyboard.append([button])
            remaining -= 1
        tg.send_message(
            "Here are a list of my functions.\nFor more detail you can use <code>/help plugin-name</code>",
            reply_markup=tg.inline_keyboard_markup(keyboard))
    else:
        grab_plugin(tg)


def grab_plugin(tg):
    """
    Returns a plugins description.
    """
    if tg.callback_query:
        plugin = tg.callback_query['data'].replace('%%help%%', '').lower()
    else:
        plugin = tg.message['match'].lower()
    tg.database.query('SELECT pretty_name, short_description, long_description FROM plugins '
                      'WHERE lower(pretty_name)="{0}" OR lower(plugin_name) ="{0}"'.format(plugin))
    query = tg.database.store_result()
    row = query.fetch_row(how=1)
    if row:
        row = row[0]
        if tg.callback_query:
            response = "{} - {}".format(row['pretty_name'], row['short_description'])
            tg.answer_callback_query(response)
        else:
            tg.send_message(row['long_description'])
    else:
        if tg.callback_query:
            tg.answer_callback_query("Unknown error occurred")
        else:
            tg.send_message("I can't seem to find this plugin")


parameters = {
    'name': "Help",
    'short_description': "Learn about this bots various functions!",
    'long_description':
    "The /help command allows you to learn about the bots various functions. For more detail on a "
    "command you can also type in <code>/help plugin_name</code>.",
    'permissions': True
}

arguments = {'text': ["^/help$", "^/help (.*)"]}
