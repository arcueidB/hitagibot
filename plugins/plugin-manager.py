# -*- coding: utf-8 -*-

on = u"\U0001F535"
off = u"\U0001F534"
admin = u"\U0001F536"
chat_id = int
tg = None


def main(tg_api):
    global chat_id, tg
    tg = tg_api
    chat_id = tg.chat_data['chat']['id']
    if tg.callback_query:
        answer_callback()
    else:
        tg.send_chat_action('typing')
        if tg.message['chat']['type'] != 'private':
            keyboard = create_plugin_keyboard()
            if check_if_mod() or check_if_admin():
                tg.send_message(
                    "Here are a list of plugins and their status. Only admins can "
                    "toggle these",
                    reply_markup=tg.inline_keyboard_markup(keyboard))
            else:
                tg.send_message("Only admins can manage plugins!")
        else:
            tg.send_message("You can only manage plugins in groups!")


def answer_callback():
    plugin = tg.callback_query['data'].replace('%%toggle%%', '')
    if plugin == tg.plugin_name:
        tg.answer_callback_query("You can't disable this plugin!")
        return
    updated = update_plugin_status(plugin)
    if updated:
        tg.answer_callback_query("Toggled the plugin status!")
        keyboard = create_plugin_keyboard()
        tg.edit_message_reply_markup(
            message_id=tg.callback_query['message']['message_id'], reply_markup=tg.inline_keyboard_markup(keyboard))
    elif updated is False:
        tg.answer_callback_query("Only the bot admin can toggle this plugin!")
    else:
        tg.answer_callback_query("Only chat admins can toggle plugins!")


def update_plugin_status(plugin_name):
    tg.database.query('SELECT plugin_status FROM `{}blacklist` WHERE plugin_name="{}"'.format(chat_id, plugin_name))
    query = tg.database.store_result()
    row = query.fetch_row(how=1, maxrows=0)
    if row[0]['plugin_status'] != 2:
        has_permission = check_if_admin() or check_if_mod()
        if not has_permission:
            return
    else:
        has_permission = check_if_admin()
        if not has_permission:
            return False
    tg.cursor.execute('UPDATE `{}blacklist` SET plugin_status = NOT `plugin_status` WHERE '
                      'plugin_name=lower("{}");'.format(chat_id, plugin_name))
    tg.database.commit()
    return True


def create_plugin_keyboard():
    keyboard = list()
    tg.database.query("SELECT b.plugin_name, pretty_name, plugin_status FROM `plugins` p "
                      "LEFT JOIN `{}blacklist` b ON p.plugin_name=b.plugin_name WHERE "
                      "b.plugin_name != \"{}\" AND hidden=0 AND inline_only=0;".format(chat_id, tg.plugin_name))
    query = tg.database.store_result()
    rows = query.fetch_row(how=1, maxrows=0)
    remaining = len(rows)

    for plugin in rows:
        button = {'callback_data': "%%toggle%%{}".format(plugin['plugin_name']), 'text': "{} - {}"}

        if plugin['plugin_status'] == 0:
            button['text'] = button['text'].format(off, plugin['pretty_name'])
        elif plugin['plugin_status'] == 1:
            button['text'] = button['text'].format(on, plugin['pretty_name'])
        elif plugin['plugin_status'] == 2:
            button['text'] = button['text'].format(admin, plugin['pretty_name'])

        row_length = 4 if remaining >= 4 or remaining == 1 else 3
        remaining -= 1
        if keyboard and len(keyboard[-1]) < row_length:
            keyboard[-1].append(button)
        else:
            keyboard.append([button])
    return keyboard


def check_if_mod():
    admins = tg.get_chat_administrators()
    if tg.callback_query:
        user_id = tg.callback_query['from']['id']
    else:
        user_id = tg.chat_data['from']['id']
    if admins['ok']:
        admins = admins['result']
    else:
        return
    if any(user['user']['id'] == user_id for user in admins):
        return True


def check_if_admin():
    if tg.callback_query:
        user_id = tg.callback_query['from']['id']
    else:
        user_id = tg.chat_data['from']['id']
    if str(user_id) in tg.config['BOT_CONFIG']['admins']:
        return True
    return


parameters = {
    'name': "Plugin Manager",
    'short_description': "Enable and disable plugins in your group!",
    'long_description':
    "The plugin manager allows you to enable and disable plugins in your group. Simply use the "
    "/admin command for an interactive plugin control panel. Only chat administrators are allowed "
    "to toggle plugins.",
    'permissions': True
}

arguments = {'text': ["^/admin$", "^/plugins$"]}
