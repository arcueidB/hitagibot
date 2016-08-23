# -*- coding: utf-8 -*-
"""
The LastFM plugin allows you to share currently/recently played,
top artists, and top tracks
"""

import concurrent.futures
import json
import os
import time

base_url = "https://ws.audioscrobbler.com/2.0/?method={}&api_key={}&format=json"
try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError


def main(tg):
    """
    Determines if theres an api key in the config then routes the message
    """
    api_key = tg.config['LASTFM']['api_key']
    if not api_key:
        return
    if tg.message:
        tg.send_chat_action('typing')
        handle_message(tg, api_key)
    elif tg.inline_query:
        handle_inline_query(tg, api_key)


def handle_message(tg, api_key):
    """
    Sends song or asks to link/links a users lastfm account
    """
    if tg.message['flagged_message']:
        link_profile(tg, api_key)
    else:
        try:
            first_name, lastfm_name, determiner = determine_names(tg)
        except TypeError:
            tg.send_message("I can't find this user :(")
            return
        if lastfm_name:
            if tg.message['matched_regex'] in arguments['text'][:2]:
                response = last_played(tg.http, api_key, first_name, lastfm_name)
                if response:
                    message = response['text']
                    keyboard = tg.inline_keyboard_markup(response['keyboard'])
                    tg.send_message(message, reply_markup=keyboard)
                else:
                    tg.send_message("No recently played tracks :(")
            elif tg.message['matched_regex'] in arguments['text'][:5]:
                top_tracks(tg, api_key, first_name, lastfm_name)
            else:
                top_artists(tg, api_key, first_name, lastfm_name)
        else:
            tg.send_message(
                "It seems {} LastFM hasn't been linked\n"
                "Reply with your LastFM to link it!".format(determiner),
                flag_message=True)


def handle_inline_query(tg, api_key):
    """
    Sends a users lastfm songs or nothing if the account isn't linked
    """
    try:
        first_name, lastfm_name, determiner = determine_names(tg)
    except TypeError:
        tg.answer_inline_query([])
        return
    if lastfm_name:
        page = int(tg.inline_query['offset']) if tg.inline_query['offset'] else 1
        track_list = get_recently_played(tg.http, api_key, lastfm_name, 14, page=page)
        if track_list:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
            futures = [executor.submit(create_track_result, tg, track, lastfm_name, first_name) for track in track_list]
            concurrent.futures.wait(futures)
            offset = page + 1 if len(track_list) == 14 else ''
            is_personal = False if '(.*)' in tg.inline_query['matched_regex'] else True
            tg.answer_inline_query(
                [box.result() for box in futures], is_personal=is_personal, cache_time=15, next_offset=offset)
            return
    tg.answer_inline_query([])


def create_track_result(tg, track, lastfm_name, first_name):
    """
    Creates a track result for inline mode
    """
    if track['now_playing']:
        time_played = "Currently Playing!"
        message = "{} is currently listening to:\n".format(first_name)
    else:
        time_played = how_long(track['date'])
        message = "{} recently listened to:\n".format(first_name)
    message += "{}\t-\t{}".format(track['name'], track['artist'])
    keyboard = create_keyboard(lastfm_name, track['song_url'])
    message_contents = tg.input_text_message_content(message)
    description = "{}\n{}".format(track['artist'], time_played)
    return tg.inline_query_result_article(
        track['name'],
        message_contents,
        description=description,
        reply_markup=tg.inline_keyboard_markup(keyboard),
        thumb_url=track['image'],
        parse_mode="None")


def last_played(http, api_key, first_name, lastfm_name):
    """
    Creates a last played message and keyboard
    """
    track_list = get_recently_played(http, api_key, lastfm_name, 1)
    if track_list:
        for track in track_list:
            if track['now_playing']:
                message = "{} is currently listening to:\n".format(first_name)
            else:
                message = "{} last listened to:\n".format(first_name)
            message += "{}\t-\t{}".format(track['name'], track['artist'])
            keyboard = create_keyboard(lastfm_name, track['song_url'])
            return {'text': message, 'keyboard': keyboard}


def top_tracks(tg, api_key, first_name, lastfm_name):
    """
    Sends a users top tracks
    """
    limit = int(tg.message['match'][1]) if tg.message['matched_regex'] in arguments['text'][3] else 8
    limit = 25 if limit > 25 else limit
    track_list = get_top_tracks(tg.http, api_key, lastfm_name, limit)
    if track_list:
        message = "<b>{}'s Top Tracks</b>\n".format(first_name)
        for track in track_list:
            message += '\n<a href="{}">{}</a>  -  <code>{} plays</code>'.format(track['song_url'], track['name'],
                                                                                track['play_count'])
        tg.send_message(message, disable_web_page_preview=True)


def top_artists(tg, api_key, first_name, lastfm_name):
    """
    Sends a users top artists
    """
    limit = int(tg.message['match'][1]) if tg.message['matched_regex'] in arguments['text'][6] else 8
    limit = 25 if limit > 25 else limit
    artists = get_top_artists(tg.http, api_key, lastfm_name, limit)
    if artists:
        message = "<b>{}'s Top Artists</b>\n".format(first_name)
        for artist in artists:
            message += '\n<a href="{}">{}</a>  -  <code>{} plays</code>'.format(artist['url'], artist['name'],
                                                                                artist['play_count'])
        tg.send_message(message, disable_web_page_preview=True)


def get_top_artists(local_http, api_key, user_name, limit, period='1month', page=1):
    """
    getTopArtists method. Returns a list of top artists.
    """
    artist_list = list()
    method = 'user.getTopArtists'
    url = (base_url + '&user={}&limit={}&period={}&page={}').format(method, api_key, user_name, limit, period, page)
    result = local_http.request('GET', url).data
    response = json.loads(result.decode('UTF-8'))
    try:
        artists = response['topartists']['artist']
    except KeyError:
        return
    for artist in artists:
        info = {
            'name': clean_up(artist['name']),
            'play_count': artist['playcount'],
            'url': artist['url'],
        }
        artist_list.append(info)
    return artist_list


def get_top_tracks(local_http, api_key, user_name, limit, period='1month', page=1):
    """
    getTopTracks method. Returns a list of top tracks.
    """
    track_list = list()
    method = 'user.getTopTracks'
    url = (base_url + '&user={}&limit={}&period={}&page={}').format(method, api_key, user_name, limit, period, page)
    result = local_http.request('GET', url).data
    response = json.loads(result.decode('UTF-8'))
    tracks = response['toptracks']['track']
    for track in tracks:
        song = {
            'name': clean_up(track['name']),
            'play_count': track['playcount'],
            'artist': clean_up(track['artist']['name']),
            'song_url': track['url'],
            'artist_url': track['artist']['url']
        }
        track_list.append(song)
    return track_list


def get_recently_played(local_http, api_key, user_name, limit, page=1):
    """
    getRecentTracks method. Returns a users recently played tracks.
    """
    method = 'user.getRecentTracks'
    url = (base_url + '&user={}&limit={}&page={}').format(method, api_key, user_name, limit, page)
    result = local_http.request('GET', url).data
    response = json.loads(result.decode('UTF-8'))
    if 'error' in response:
        return
    tracks = response['recenttracks']['track']
    track_list = list()
    for track in tracks:
        now_playing = bool('@attr' in track)
        song = {
            'name': clean_up(track['name']),
            'artist': clean_up(track['artist']['#text']),
            'song_url': track['url'],
            'album': clean_up(track['album']['#text']),
            'now_playing': now_playing,
            'image': track['image'][-1]['#text']
        }
        try:
            song['date'] = track['date']['uts']
        except KeyError:
            song['date'] = None
        track_list.append(song)
    return track_list


def get_lastfm_username(user_id):
    """
    Tries to grab a users lastfm username from their profile
    """
    try:
        with open('data/profile/{}.json'.format(int(user_id))) as json_file:
            profile = json.load(json_file)
    except (ValueError, FileNotFoundError):
        return
    if 'lastfm' in profile:
        return profile['lastfm']


def determine_names(tg):
    """
    Determines a users first_name, last_name, and a determiner
    """
    if tg.message:
        matched_regex = tg.message['matched_regex']
    else:
        matched_regex = tg.inline_query['matched_regex']
    if '(.*)' in matched_regex:
        determiner = None
        name = tg.message['match'] if tg.message else tg.inline_query['match']
        if name[0] == '@':
            tg.database.query('SELECT user_id FROM users_list WHERE user_name="{}"'.format(name.replace('@', '')))
            query = tg.database.store_result()
            result = query.fetch_row(how=1, maxrows=0)
            if result:
                return name, get_lastfm_username(result[0]['user_id']), "this"
            else:
                return False
        lastfm_name = first_name = tg.message['match'] if tg.message else tg.inline_query['match']
    elif tg.message and 'reply_to_message' in tg.message:
        user_id = tg.message['reply_to_message']['from']['id']
        determiner = "this"
        lastfm_name = get_lastfm_username(user_id)
        first_name = tg.message['reply_to_message']['from']['first_name']
    else:
        user_id = tg.message['from']['id'] if tg.message else tg.inline_query['from']['id']
        determiner = "your"
        lastfm_name = get_lastfm_username(user_id)
        first_name = tg.message['from']['first_name'] if tg.message else tg.inline_query['from']['first_name']
    return first_name, lastfm_name, determiner


def link_profile(tg, api_key):
    """
    Links a profile and sends the last played
    """
    if not os.path.exists('data/profile'):
        os.makedirs('data/profile')
    user_id = tg.message['from']['id']
    try:
        with open('data/profile/{}.json'.format(user_id)) as file:
            profile = json.load(file)
    except (JSONDecodeError, FileNotFoundError):
        open('data/profile/{}.json'.format(user_id), 'w')
        profile = dict()
    if 'text' in tg.message:
        if 'lastfm' in profile:
            message = "Updated your LastFM!"
        else:
            message = "Successfully set your LastFM!"
        profile['lastfm'] = tg.message['text'].replace('\n', '')
        track_list = get_recently_played(tg.http, api_key, profile['lastfm'], 1)
        keyboard = [[]]
        if track_list:
            track_list = track_list.pop()
            if track_list['now_playing']:
                message += "\n\nYou are currently listening to:"
            else:
                message += "\n\nYou have last listened to:"
            message += "\n{} - {}".format(track_list['name'], track_list['artist'])
            keyboard = create_keyboard(profile['lastfm'], track_list['song_url'])
        keyboard = tg.inline_keyboard_markup(keyboard)
        tg.send_message(message, reply_markup=keyboard)
    else:
        tg.send_message("Invalid username")
    with open('data/profile/{}.json'.format(user_id), 'w') as file:
        json.dump(profile, file, sort_keys=True, indent=4)


def create_keyboard(lastfm_name, song_url):
    """
    Creates a keyboard for the song
    """
    profile_url = "http://www.lastfm.com/user/{}".format(lastfm_name)
    keyboard = [[{'text': "Profile", 'url': profile_url}, {'text': "Song", 'url': song_url}]]
    return keyboard


def how_long(epoch_time):
    """
    Determine how long ago the user listened to the song
    """
    if epoch_time:
        diff = int(time.time() - int(epoch_time))
        if diff < 240:
            return "Just now"
        elif diff < 3600:
            return "{} minutes ago".format(int(diff / 60))
        elif 86399 > diff > 3600:
            return "{} hours ago".format(int(diff / 3600))
        elif diff > 86400:
            return "{} days ago".format(int(diff / 86400))
    else:
        return "Unknown time ago"


def clean_up(text):
    """
    Remove "tags" from text
    """
    text = text.replace('<', '&lt;')
    return text.replace('>', '&gt;')


parameters = {
    'name': "LastFM",
    'short_description': "View your recently played LastFM tracks!",
    'long_description':
    "The LastFM function of this bot allows you to share your currently and recently listened to "
    "tracks. You can use the command /lastfm both in a chat and inline to do so.",
    'permissions': True
}

arguments = {
    'text': [
        "^/lastfm (.*)", "^/lastfm$", "^/toptracks$", r"^/toptracks (--|\u2014)(\d+)$", "^/toptracks (.*)",
        "^/topartists$", r"^/topartists (--|\u2014)(\d+)$", "^/topartists (.*)"
    ]
}

inline_arguments = [
    '^lastfm$',
    "^lastfm (.*)",
    "^lastfm (.*)",
    "^/lastfm$",
]
