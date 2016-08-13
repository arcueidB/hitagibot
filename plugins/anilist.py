# -*- coding: utf-8 -*-

import concurrent.futures
import html
import json
import time

import urllib.parse
import _mysql_exceptions

base_url = "http://anilist.co/api/"
client_id = None
client_secret = None
token = None
youtube = "https://www.youtube.com/watch?v={}"

try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError


def main(tg):
    global client_id, client_secret, token
    try:
        client_id = tg.config['ANILIST']['client_id']
        client_secret = tg.config['ANILIST']['client_secret']
    except KeyError:
        return
    if client_id and client_secret:
        token = client_credentials(tg)
        if token:
            if tg.message:
                handle_message(tg)
            elif tg.inline_query:
                handle_inline_query(tg)
        elif tg.message:
            tg.send_message("It seems that Anilist is down right now :(")
        elif tg.inline_query:
            tg.answer_inline_query([], cache_time=0)


def handle_message(tg):
    tg.send_chat_action('typing')
    if tg.message['flagged_message']:
        match = tg.plugin_data
    else:
        match = tg.message['matched_regex']
    if match in arguments['text'][0:2]:
        return_anime_result(tg)
    elif match in arguments['text'][2:4]:
        return_character_result(tg)
    elif match in arguments['text'][4:6]:
        return_manga_result(tg)


def handle_inline_query(tg):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    if tg.inline_query['offset']:
        query_start, query_end = [int(x) for x in tg.inline_query['offset'].split(',')]
    else:
        query_start, query_end = 0, 8
    if tg.inline_query['matched_regex'] is None:
        futures = default_query(tg, query_start, query_end)
    elif tg.inline_query['matched_regex'] in inline_arguments[0:2]:
        if tg.inline_query['matched_regex'] == inline_arguments[0]:
            search_results = return_anime_query(tg, query_start, query_end, True)
        elif tg.inline_query['matched_regex'] == inline_arguments[1]:
            search_results = return_anime_query(tg, query_start, query_end)
        futures = [executor.submit(create_anime_box, tg, anime) for anime in search_results]
    elif tg.inline_query['matched_regex'] in inline_arguments[2:4]:
        if tg.inline_query['matched_regex'] == inline_arguments[2]:
            search_results = return_character_query(tg, query_start, query_end, True)
        elif tg.inline_query['matched_regex'] == inline_arguments[3]:
            search_results = return_character_query(tg, query_start, query_end)
        futures = [executor.submit(create_character_box, tg, character) for character in search_results]
    elif tg.inline_query['matched_regex'] in inline_arguments[4:6]:
        if tg.inline_query['matched_regex'] == inline_arguments[4]:
            search_results = return_manga_query(tg, query_start, query_end, True)
        elif tg.inline_query['matched_regex'] == inline_arguments[5]:
            search_results = return_manga_query(tg, query_start, query_end)
        futures = [executor.submit(create_manga_box, tg, manga) for manga in search_results]
    concurrent.futures.wait(futures)
    offset = '{},{}'.format(query_end, query_end + 8) if len(futures) >= (query_end - query_start) else None
    tg.answer_inline_query([box.result() for box in futures], cache_time=10800, next_offset=offset)


def default_query(tg, query_start, query_end):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=16)
    futures = []
    if not tg.inline_query['match']:
        default = True
    else:
        default = False
    character_results = return_character_query(tg, query_start, query_end, default)
    manga_results = return_manga_query(tg, query_start, query_end, default)
    anime_results = return_anime_query(tg, query_start, query_end, default)
    while character_results or manga_results or anime_results:
        for i in range(0, 3):
            if anime_results:
                futures.append(executor.submit(create_anime_box, tg, anime_results[0]))
                del anime_results[0]
        for i in range(0, 2):
            if manga_results:
                futures.append(executor.submit(create_manga_box, tg, manga_results[0]))
                del manga_results[0]
        if character_results:
            futures.append(executor.submit(create_character_box, tg, character_results[0]))
            del character_results[0]
    return futures


def return_anime_query(tg, query_start, query_end, default=False):
    if default:
        url = base_url + 'browse/anime'
        fields = {'year': 2016,
                  'access_token': token,
                  'status': "Currently Airing",
                  'type': "TV",
                  'sort': "popularity-desc"}
        post = tg.http.request('GET', url, fields=fields)
        search_results = json.loads(post.data.decode('UTF-8'))
    else:
        search_results = search('anime/search/{}', tg.http, tg.inline_query['match'])
    return search_results[query_start:query_end] if search_results and 'error' not in search_results else list()


def return_manga_query(tg, query_start, query_end, default=False):
    if default:
        url = base_url + 'browse/manga'
        fields = {'access_token': token, 'sort': "score-desc"}
        post = tg.http.request('GET', url, fields=fields)
        search_results = json.loads(post.data.decode('UTF-8'))
    else:
        search_results = search('manga/search/{}', tg.http, tg.inline_query['match'])
    return search_results[query_start:query_end] if search_results and 'error' not in search_results else list()


def return_character_query(tg, query_start, query_end, default=False):
    if default:
        search_results = None
    else:
        search_results = search('character/search/{}', tg.http, tg.inline_query['match'])
    return search_results[query_start:query_end] if search_results and 'error' not in search_results else list()


def return_anime_result(tg):
    if tg.message['matched_regex'] == arguments['text'][0]:
        tg.send_message("Which anime should I look for?", flag_message={'plugin_data': arguments['text'][0]})
        return
    elif tg.message['flagged_message']:
        if 'text' in tg.message:
            query = tg.message['text']
        else:
            tg.send_message("I can only search for anime using text :(")
            return
    else:
        query = tg.message['match']
    search_results = search('anime/search/{}', tg.http, query)
    if search_results == int:
        tg.send_message("Anilist seems to be down right now :(")
    elif search_results:
        anime_id = search_results[0]['id']
        tg.send_message(**anime_model(tg, anime_id))
    else:
        tg.send_message("I couldn't find any results :(")


def return_manga_result(tg):
    if tg.message['matched_regex'] == arguments['text'][4]:
        tg.send_message("Which manga should I look for?", flag_message={'plugin_data': arguments['text'][4]})
        return
    elif tg.message['flagged_message']:
        if 'text' in tg.message:
            query = tg.message['text']
        else:
            tg.send_message("I can only search for manga using text :(")
            return
    else:
        query = tg.message['match']
    search_results = search('manga/search/{}', tg.http, query)
    if search_results == int:
        tg.send_message("Anilist seems to be down right now :(")
    elif search_results:
        manga_id = search_results[0]['id']
        tg.send_message(**manga_model(tg, manga_id))
    else:
        tg.send_message("I couldn't find any results :(")


def return_character_result(tg):
    if tg.message['matched_regex'] == arguments['text'][2]:
        tg.send_message("Which character should I look for?", flag_message={'plugin_data': arguments['text'][2]})
        return
    elif tg.message['flagged_message']:
        if 'text' in tg.message:
            query = tg.message['text']
        else:
            tg.send_message("I can only search for characters using text :(")
            return
    else:
        query = tg.message['match']
    search_results = search('character/search/{}', tg.http, query)
    if search_results == int:
        tg.send_message("Anilist seems to be down right now :(")
    elif search_results:
        character_id = search_results[0]['id']
        tg.send_message(**character_model(tg, character_id))
    else:
        tg.send_message("I couldn't find any results :(")


def create_anime_box(tg, anime):
    message = anime_model(tg, anime['id'])
    message_content = tg.input_text_message_content(message['text'], parse_mode="markdown")
    if 'image_url_lge' in anime and anime['image_url_lge']:
        thumb_url = anime['image_url_lge']
    else:
        thumb_url = "http://anilist.co/img/dir/anime/reg/noimg.jpg"
    if 'airing_status' in anime:
        description = anime['airing_status'].title()
    if 'type' in anime:
        description += " " + anime['type']
    box = tg.inline_query_result_article(
        anime['title_romaji'],
        message_content,
        reply_markup=message['reply_markup'],
        thumb_url=thumb_url,
        description=description)
    return box


def create_character_box(tg, character):
    message, big_model = character_model(tg, character['id'], True)
    message_content = tg.input_text_message_content(message['text'], parse_mode="markdown")
    title = "{} {}".format(character['name_first'], character['name_last'])
    if 'name_japanese' in character:
        description = "Character - {}".format(character['name_japanese'])
    else:
        description = "Character"
    box = tg.inline_query_result_article(
        title,
        message_content,
        reply_markup=message['reply_markup'],
        thumb_url=character['image_url_lge'],
        description=description)
    return box


def create_manga_box(tg, manga):
    message = manga_model(tg, manga['id'])
    message_content = tg.input_text_message_content(message['text'], parse_mode="markdown")
    if 'publishing_status' in manga and 'type' in manga:
        description = "{} {}".format(manga['publishing_status'].title(), manga['type'].title())
    else:
        description = "Manga"
    box = tg.inline_query_result_article(
        manga['title_romaji'],
        message_content,
        reply_markup=message['reply_markup'],
        thumb_url=manga['image_url_lge'],
        description=description)
    return box


def anime_model(tg, anime_id):
    anime = get_model('anime/{}/page', tg.http, anime_id)
    if anime:
        message = "*{}*".format(anime['title_romaji'])
        if 'title_english' in anime:
            if anime['title_english'].lower() != anime['title_romaji'].lower():
                message += " ({})".format(anime['title_english'])
        if anime['airing_status'] == "currently airing":
            message += '\n*Airs in {}*'

        if 'image_url_banner' in anime and anime['image_url_banner']:
            message += u'[\u200B]({})'.format(anime['image_url_banner'])
        elif 'image_url_lge' in anime and anime['image_url_lge']:
            message += u'[\u200B]({})'.format(anime['image_url_lge'])
        else:
            message += u'[\u200B]({})'.format("http://anilist.co/img/dir/anime/reg/noimg.jpg")

        message += "\n\n*Type:* {}".format(anime['type'])
        if 'studio' in anime:
            message += "\n*Studio:* "
            message += ", ".join([studio['studio_name'] for studio in anime['studio']])
        message += "\n*Status:* {}".format(anime['airing_status'].title())
        if 'airing_status' in anime:
            if anime['airing_status'] == "currently airing":
                episodes, hours = parse_date(anime)
                message = message.format(hours)
                if episodes > 1:
                    message += "\n*Episode Count:* {}".format(episodes - 1)
                    if anime['total_episodes']:
                        message += "/{}".format(anime['total_episodes'])
        elif 'total_episodes' in anime and anime['total_episodes']:
            message += "\n*Episode Count:* {}".format(anime['total_episodes'])

        if 'start_date' in anime and anime['start_date']:
            air_season = determine_air_season(anime['start_date'])
            if air_season:
                message += "\n*Aired:* {}".format(air_season)
        if 'average_score' in anime and float(anime['average_score']):
            message += "\n*Score:* {}".format(anime['average_score'])
        if 'genres' in anime and anime['genres']:
            message += "\n*Genres:* {}".format(', '.join(anime['genres']))
        if 'description' in anime and anime['description']:
            message += "\n\n{}".format(clean_description(anime['description']))

        anime_url = "https://www.anilist.co/anime/{}".format(anime['id'])
        keyboard = [[{'text': 'Full Anime Page', 'url': anime_url}]]
        if anime['youtube_id']:
            youtube_url = "https://www.youtube.com/watch?v={}".format(anime['youtube_id'])
            keyboard[0].append({'text': "Youtube Trailer", 'url': youtube_url})

        return {'text': message, 'reply_markup': tg.inline_keyboard_markup(keyboard), 'parse_mode': "markdown"}
    return {'text': "Anilist seems to be down :("}


def character_model(tg, character_id, inline=False):
    character = get_model('character/{}', tg.http, character_id)
    if character:
        message = "*{} {}*".format(character['name_first'], character['name_last'])

        if character['name_alt']:
            message += "\n*Aliases:* {}".format(character['name_alt'])

        if 'image_url_banner' in character and character['image_url_banner']:
            message += '[​]({})'.format(character['image_url_banner'])
        elif 'image_url_lge' in character and character['image_url_lge']:
            message += '[​]({})'.format(character['image_url_lge'])

        if character['info']:
            message += "\n\n{}".format(clean_description(character['info']))

        character_page = "http://anilist.co/character/{}".format(character['id'])
        keyboard = [[{'text': "Full Character Page", 'url': character_page}]]

        msg_contents = {'text': message, 'reply_markup': tg.inline_keyboard_markup(keyboard), 'parse_mode': "markdown"}
        if inline:
            return msg_contents, character
        else:
            return msg_contents
    return {'text': "Anilist seems to be down :("}


def manga_model(tg, manga_id):
    manga = get_model('manga/{}', tg.http, manga_id)
    if manga:
        message = "*{}* - {}".format(manga['title_romaji'], manga['title_japanese'])

        if 'image_url_banner' in manga and manga['image_url_banner']:
            message += '[​]({})'.format(manga['image_url_banner'])
        elif 'image_url_lge' in manga and manga['image_url_lge']:
            message += '[​]({})'.format(manga['image_url_lge'])

        if 'type' in manga and manga['type']:
            message += "\n*Type:* {}".format(manga['type'])
        if 'publishing_status' in manga and manga['publishing_status']:
            message += "\n*Status:* {}".format(manga['publishing_status'].title())
        if 'total_chapters' in manga and manga['total_chapters']:
            message += "\n*Chapter Count:* {}".format(manga['total_chapters'])
        if 'total_volumes' in manga and manga['total_volumes']:
            message += "\n*Volume Count:* {}".format(manga['total_volumes'])
        if 'average_score' in manga and manga['average_score']:
            message += "\n*Score:* {}".format(manga['average_score'])
        if 'genres' in manga and manga['genres']:
            message += "\n*Genres: {}*".format(', '.join(manga['genres']))
        if 'description' in manga and manga['description']:
            message += "\n\n{}".format(clean_description(manga['description']))

        manga_page = "http://anilist.co/manga/{}".format(manga['id'])
        keyboard = [[{'text': "Full Manga Page", 'url': manga_page}]]
        return {'text': message, 'reply_markup': tg.inline_keyboard_markup(keyboard), 'parse_mode': "markdown"}
    return {'text': "Anilist seems to be down :("}


def search(method, http, query):
    query = urllib.parse.quote(query)
    url = base_url + method.format(query)
    post = http.request('GET', url, fields={'access_token': token})
    if post.status == 200:
        try:
            search_results = json.loads(post.data.decode('UTF-8'))
        except JSONDecodeError:
            return
        if 'error' not in search_results:
            return search_results
    return


def get_model(method, http, query_id):
    url = base_url + method.format(query_id)
    post = http.request('GET', url, fields={'access_token': token})
    if post.status == 200:
        try:
            return json.loads(post.data.decode('UTF-8'))
        except JSONDecodeError:
            return
    return


def client_credentials(tg):
    tg.database.query('SELECT access_token FROM anilist_tokens WHERE grant_type="client_credentials" '
                      'AND expires > FROM_UNIXTIME({})'.format(int(time.time() - 60, )))
    query = tg.database.store_result()
    rows = query.fetch_row()
    if rows:
        return rows[0][0]
    url = base_url + "auth/access_token"
    headers = {'grant_type': "client_credentials", 'client_id': client_id, 'client_secret': client_secret}
    post = tg.http.request_encode_body('POST', url, fields=headers)
    try:
        result = json.loads(post.data.decode('UTF-8'))
    except JSONDecodeError:
        return post.status
    expires = result['expires_in'] + int(time.time())
    tg.cursor.execute('DELETE FROM anilist_tokens WHERE grant_type="client_credentials"')
    tg.cursor.execute("INSERT INTO anilist_tokens(access_token, token_type, expires, grant_type) VALUES(%s, %s, "
                      "FROM_UNIXTIME(%s), %s);", (result['access_token'], result['token_type'], expires - 10,
                                                  "client_credentials"))
    return result['access_token']


def clean_description(description):
    if description:
        description = description[:description.rfind('\n')].replace('<br>', '')
        if len(description) > 300:
            description = description[:250] + "...."
        return html.unescape(description).replace('`', '\'')


def parse_date(anime):
    try:
        next_episode = anime['airing']['next_episode']
    except TypeError:
        return 0, "Unknown"
    time_left = int(anime['airing']['countdown'])
    if time_left < 240:
        time_statement = "A few minutes"
    elif time_left < 3600:
        time_left = int(time_left / 60)
        time_statement = "{} minute".format(time_left)
    elif 86399 > time_left > 3600:
        time_left = int(time_left / 3600)
        time_statement = "{} hour".format(time_left)
    else:
        time_left = int(time_left / 86400)
        time_statement = "{} day".format(time_left)
    if time_left > 1:
        time_statement += 's'
    return next_episode, time_statement


def determine_air_season(date):
    date = date.split('-')
    try:
        year = int(date[0])
        month = int(date[1])
    except IndexError:
        return None
    if month <= 3:
        season = "Winter"
    elif month <= 6:
        season = "Spring"
    elif month <= 9:
        season = "Summer"
    elif month <= 12:
        season = "Fall"
    else:
        season = "Unknown"
    return "{} {}".format(season, year)


def init_db(database):
    cursor = database.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS anilist_tokens(access_token VARCHAR(64) NOT NULL, token_type VARCHAR(64)"
                   ", expires DATETIME, refresh_token VARCHAR(64), grant_type VARCHAR(64), user_id BIGINT)")
    cursor.close()


parameters = {
    'name': "Anilist",
    'short_description': "Search for anime, characters, and manga.",
    'long_description':
    "Search anilist using /anime, /character, and /manga for information like rating, summary, and "
    "episode count. You can also use this command inline from within any chat.",
    'permissions': True
}

arguments = {
    'text': [
        "^/anime$",
        "^/anime (.*)",
        "^/character$",
        "^/character (.*)",
        "^/manga$",
        "^/manga (.*)",
    ]
}

inline_arguments = [
    "^/?anime$",
    "^/?anime (.*)",
    "^/?character$",
    "^/?character (.*)",
    "^/?manga$",
    "^/?manga (.*)",
]
