import concurrent.futures
import json
import time

base_url = "https://ibsearch.xxx/api/v1/"
image_path = "https://{}.ibsearch.xxx/{}"
thumb_path = "https://{}.ibsearch.xxx/t{}"
api_key = None

try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError


def main(tg):
    global api_key
    api_key = tg.config['IBSEARCH']['api_key']
    if not api_key:
        return
    if tg.inline_query:
        page = int(tg.inline_query['offset']) if tg.inline_query['offset'] else 1
        if tg.inline_query['matched_regex'] == inline_arguments[0]:
            query = 'random: rating:s'
        else:
            query = tg.inline_query['match'].replace(' ', '_') + ' rating:s'
        images = get_images(tg.http, query, page=page)
        if images:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
            futures = [executor.submit(create_box, tg, pic) for pic in images]
            concurrent.futures.wait(futures)
            offset = page + 1 if len(images) == 50 else ''
            tg.answer_inline_query([box.result() for box in futures], cache_time=86400, next_offset=offset)
        else:
            tg.answer_inline_query([], cache_time=0)


def create_box(tg, pic):
    image_url = image_path.format(pic['server'], pic['path'])
    thumb_url = thumb_path.format(pic['server'], pic['path'])
    if pic['site_deleted'] != '0':
        sauce = image_url
    else:
        sauce = pic['site_file']
    keyboard = [[{'text': 'Source', 'url': sauce}]]
    width = int(pic['width'])
    height = int(pic['height'])
    return tg.inline_query_result_photo(
        image_url, thumb_url, photo_width=width, photo_height=height, reply_markup=tg.inline_keyboard_markup(keyboard))


def get_images(http, query, limit=50, page=1):
    fields = {'key': api_key, 'limit': limit, 'page': page, 'q': query, 'rating': 's', 'sources': 'one'}
    response = http.request('GET', base_url + 'images.json', fields=fields)
    if response.status == 200:
        try:
            return json.loads(response.data.decode('UTF-8'))
        except JSONDecodeError:
            return
    elif response.status == 429:
        time.sleep(0.1)
        return get_images(http, query)
    else:
        return


parameters = {
    'name': "Ibsearch",
    'short_description':
    "Search Ibsearch for anime art inline using ibsearch <search_term>",
    'long_description':
    "This is an inline only function which allows you to search Ibsearch for anime art. Simply "
    "initiate an inline query from any chat and type in <code>ibsearch &lt;search_term&gt;</code>.",
    'inline_only': True
}

inline_arguments = ['^/?ibsearch$', '^/?ibsearch (.*)']
