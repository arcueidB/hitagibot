# -*- coding: utf-8 -*-

import json
import os

import _mysql_exceptions

user_id = None
entries = None
try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError


def main(tg):
    global user_id, entries
    if not os.path.exists('data/profile'):
        os.makedirs('data/profile')
    if tg.message:
        tg.send_chat_action('typing')
        if 'reply_to_message' in tg.message:
            user_id = tg.message['reply_to_message']['from']['id']
        else:
            user_id = tg.message['from']['id']
    else:
        user_id = tg.inline_query['from']['id']
    with open('data/entries.json', 'r') as json_file:
        entries = json.load(json_file)
    if tg.message:
        if tg.message['matched_regex'] == arguments['text'][0]:
            message, keyboard = return_profile(tg)
            tg.send_message(message, reply_markup=tg.inline_keyboard_markup(keyboard))
        elif tg.message['matched_regex'] == arguments['text'][1]:
            if "delete" in tg.message['match'] or "del" in tg.message['match']:
                delete_entry(tg)
            else:
                add_entry(tg)
    else:
        message, keyboard = return_profile(tg)
        message_contents = tg.input_text_message_content(message)
        box = tg.inline_query_result_article(
            "Share your profile!", message_contents, reply_markup=tg.inline_keyboard_markup(keyboard))
        tg.answer_inline_query([box], is_personal=True, cache_time=60)


def return_profile(tg):
    global user_id
    if tg.message:
        if 'reply_to_message' in tg.message:
            first_name = tg.message['reply_to_message']['from']['first_name']
        else:
            first_name = tg.message['from']['first_name']
    else:
        first_name = tg.inline_query['from']['first_name']
    try:
        with open('data/profile/{}.json'.format(user_id)) as json_file:
            profile = json.load(json_file)
    except (JSONDecodeError, FileNotFoundError):
        profile = dict()
    message = "<b>{}'s Profile</b>".format(first_name.title())
    misc_details = profile.pop('misc', None)
    keyboard = make_keyboard(profile)
    stats = get_stats(tg) if tg.message else None
    if misc_details:
        for field, value in misc_details.items():
            if field == 'bio':
                continue
            message += "\n<b>{}:</b> {}".format(field.title(), value)
        if "bio" in misc_details:
            message += "\n<b>Bio:</b> {}".format(misc_details['bio'])
    if stats:
        message += "\n<b>Total Messages:</b> {:,} ({})".format(stats['user_total'], stats['percentage'])
    try:
        playing = last_fm(tg.http, profile, tg.config['LASTFM']['api_key'])
    except KeyError:
        playing = None
    if playing:
        message += u"\n\U0001F3B6 {} - {}".format(playing['name'], playing['artist'])
    if len(message.split('\n')) == 1 and not keyboard:
        message = "\nYour profile seems empty. You can add entries using:\n<code>/profile website username</code>"
    return message, keyboard


def make_keyboard(profile):
    remaining = len(profile)
    keyboard = []
    for name, username in profile.items():
        row_length = 3 if remaining >= 3 or remaining == 1 else 2
        pretty_name = entries[name]['pretty_name']
        url = entries[name]['url'].format(username)
        button = {'text': pretty_name, 'url': url}
        if keyboard and len(keyboard[-1]) < row_length:
            keyboard[-1].append(button)
        else:
            keyboard.append([button])
        remaining -= 1
    return keyboard


def last_fm(http, profile, api_key):
    if 'lastfm' in profile:
        from plugins import lastfm
        last_track = lastfm.get_recently_played(http, api_key, profile['lastfm'], 1)
        if last_track and last_track[0]['now_playing']:
            last_track = last_track[0]
            return last_track


def get_stats(tg):
    try:
        from plugins import chat_stats
    except AttributeError:
        return
    chat_id = tg.message['chat']['id']
    try:
        tg.database.query("SELECT COUNT(*) FROM `{}stats`;".format(chat_id))
    except _mysql_exceptions.ProgrammingError:
        return
    query = tg.database.store_result()
    chat_total = query.fetch_row()
    if chat_total[0][0] < 100:
        return
    tg.database.query("SELECT COUNT(*) FROM `{}stats` WHERE user_id={}".format(chat_id, user_id))
    query = tg.database.store_result()
    user_total = query.fetch_row()
    percentage = "{:.2%}".format(user_total[0][0] / chat_total[0][0])
    return {'user_total': user_total[0][0], 'percentage': percentage}


def add_entry(tg):
    try:
        with open('data/profile/{}.json'.format(user_id)) as file:
            profile = json.load(file)
    except (JSONDecodeError, FileNotFoundError):
        open('data/profile/{}.json'.format(user_id), 'w')
        profile = dict()
    message = "This entry doesn't seem to be an option"
    field = tg.message['match'][1].lower()
    entry = tg.message['match'][2]
    if field in entries['misc']:
        max_length = entries['misc'][field]
        if len(entry) <= max_length:
            message = "Successfully updated your {}".format(field)
            try:
                profile['misc'][field] = entry
            except KeyError:
                profile.update({'misc': {field: entry}})
        else:
            message = "Your {} can only be {} characters at most :(".format(field, max_length)
    else:
        del entries['misc']
        for key, value in entries.items():
            if field.lower() == key or field.lower() in value['aliases']:
                if key in profile:
                    message = "Updated your {}!".format(value['pretty_name'])
                else:
                    message = "Successfully set your {}!".format(value['pretty_name'])
                profile.update({key: entry})
    with open('data/profile/{}.json'.format(user_id), 'w') as file:
        json.dump(profile, file, sort_keys=True, indent=4)
    tg.send_message(message)


def delete_entry(tg):
    message = "Invalid field"
    try:
        with open('data/profile/{}.json'.format(user_id)) as file:
            profile = json.load(file)
    except (JSONDecodeError, FileNotFoundError):
        tg.send_message(
            "You don't seem to have anything to delete :(\nAdd entries using <code>/profile website username</code>")
        return
    if tg.message['match'][1] == "del" or tg.message['match'][1] == "delete":
        field = tg.message['match'][2].lower()
    else:
        field = tg.message['match'][1].lower()
    if field.lower() in entries['misc']:
        message = "Successfully removed your {}".format(field)
        try:
            del profile['misc'][field]
        except KeyError:
            message = "It seems you haven't added a {}".format(field)
    else:
        del entries['misc']
        for key, value in entries.items():
            if field.lower() == key or field.lower() in value['aliases']:
                message = "Successfully removed {}".format(value['pretty_name'])
                try:
                    del profile[key]
                except KeyError:
                    message = "You haven't linked a {}".format(value['pretty_name'])
    with open('data/profile/{}.json'.format(user_id), 'w') as file:
        json.dump(profile, file, sort_keys=True, indent=4)
    tg.send_message(message)


def list_of_options():
    fields = list()
    with open('data/entries.json', 'r') as json_file:
        sites = json.load(json_file)
    for site in sites.values():
        try:
            fields.append(site['pretty_name'])
        except KeyError:
            continue
    return ", ".join(fields)


parameters = {
    'name': "Profile",
    'short_description': "Display information about yourself",
    'long_description':
    "The /profile command allows you to share your other online accounts from within a chat or "
    "inline mode. Type in <code>/profile &lt;website&gt; &lt;your_user_name&gt;</code> within a "
    "chat to add entry. To remove an entry replace <code>&lt;your_user_name&gt;</code> with delete."
    "\n\nSupported Sites: {}".format(list_of_options()),
    'permissions': True
}

arguments = {'text': ["^/(profile|me)$", "^/(profile|me) ([^\s]+) (.*)$"]}

inline_arguments = ["^/?(profile|me)$"]
