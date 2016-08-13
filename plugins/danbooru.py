# -*- coding: utf-8 -*-
"""
Returns inline results from danbooru
"""

import concurrent.futures
import json
import io
import os
from PIL import Image

base_url = "https://danbooru.donmai.us"

try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError


def main(tg):
    """
    Sends results from danbooru if inline or sends a redirection message
    """
    if tg.inline_query:
        api_key = tg.config['DANBOORU']['api_key']
        page = int(tg.inline_query['offset']) if tg.inline_query['offset'] else 1
        query = "rating:s" if tg.inline_query['matched_regex'] == inline_arguments[0] else tg.inline_query['match'][1]
        query = query.split(',')
        result = get_post(tg.http, query, page, api_key)
        if result:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
            futures = [executor.submit(create_box, tg, pic) for pic in result]
            concurrent.futures.wait(futures)
            offset = page + 1 if len(result) == 40 else ''
            response = [box.result() for box in futures]
            tg.answer_inline_query([box for box in response if box], cache_time=86400, next_offset=offset)
        else:
            tg.answer_inline_query([], cache_time=0)
    elif tg.message['pm_parameter']:
        tg.send_chat_action("upload_photo")
        photo_id = tg.message['pm_parameter'].replace('danbooru', '')
        photo = return_photo(tg.http, photo_id)
        if photo:
            photo_name = "{}.png".format(photo_id)
            file_obj = io.BytesIO()
            photo.save(file_obj, format='PNG')
            file_obj.seek(0)
            tg.send_document((photo_name, file_obj.read()))
        else:
            tg.send_message("Sorry I was unable to retrieve this photo :(")
    elif tg.message:
        keyboard = [[{'text': "Go Inline", 'switch_inline_query': "pic "}]]
        message_text = "Searching for anime pictures is an inline only feature."
        tg.send_message(message_text, reply_markup=tg.inline_keyboard_markup(keyboard))


def create_box(tg, pic):
    """
    Creates an inline result photo
    """
    try:
        image_url = base_url + pic['file_url']
    except KeyError:
        return
    thumb_url = base_url + pic['preview_file_url']
    keyboard = [[]]
    if 'source' in pic and pic['source']:
        keyboard[0].append({'text': "Source", 'url': pic['source']})
    pm_parameter = tg.pm_parameter("danbooru" + str(pic['id']))
    keyboard[0].append({'text': "Download", 'url': pm_parameter})
    width = pic['image_width']
    height = pic['image_height']
    return tg.inline_query_result_photo(
        image_url, thumb_url, photo_width=width, photo_height=height, reply_markup=tg.inline_keyboard_markup(keyboard))


def get_post(http, tags, page, api_key):
    """
    Fetches results from the given tags
    """
    tags[-1] = get_tags(http, tags[-1])
    tags = ','.join(tags)
    fields = {'api_key': api_key, 'limit': 40, 'tags': tags.replace(' ', '_') + ' rating:safe', 'page': page}
    try:
        request = http.request('GET', base_url + '/posts.json', fields=fields)
    except UnicodeEncodeError:
        return
    if request.status == 200:
        try:
            return json.loads(request.data.decode('UTF-8'))
        except JSONDecodeError:
            return


def get_tags(http, query):
    """
    Returns the top search result for the inputted tag
    """
    url = base_url + "/tags/autocomplete.json?search[name_matches]={}*".format(query)
    try:
        request = http.request('GET', url)
    except UnicodeEncodeError:
        return query
    if request.status == 200:
        try:
            result = json.loads(request.data.decode('UTF-8'))
            if result:
                return result[0]['name']
            return query
        except JSONDecodeError:
            return query
    else:
        return query


def return_photo(http, photo_id):
    """
    Returns a photo object from danbooru
    """
    file_path = "data/files/danbooru/{}.png".format(photo_id)
    try:
        return Image.open(file_path)
    except FileNotFoundError:
        pass
    url = base_url + "/posts/{}.json"
    request = http.request('GET', url.format(photo_id))
    if request.status == 200:
        try:
            result = json.loads(request.data.decode('UTF-8'))
        except JSONDecodeError:
            return
        return download_photo(http, result['file_url'], file_path)


def download_photo(http, url, file_path):
    """
    Downloads a photo and returns the file object
    """
    request = http.request('GET', base_url + url)
    if request.status == 200:
        image_obj = io.BytesIO(request.data)
        image = Image.open(image_obj)
        try:
            image.save(file_path)
        except FileNotFoundError:
            os.makedirs('data/files/danbooru')
            image.save(file_path)
        return Image.open(file_path)


parameters = {
    'name': "Danbooru",
    'short_description':
    "Search for anime art inline using animepic <search_term>",
    'long_description':
    "This is an inline only function which allows you to search Danbooru for anime art. Simply "
    "initiate an inline query from any chat and type in <code>pic &lt;search_term&gt;</code>.",
    'inline_only': True
}

arguments = {'text': ["^/pic$"]}

inline_arguments = ['^/?(danbooru|animepic|pic)$', '^/?(danbooru|animepic|pic) (.*)']
