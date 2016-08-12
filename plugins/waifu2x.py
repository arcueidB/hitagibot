# -*- coding: utf-8 -*-

from PIL import Image
import io
from urllib3.exceptions import MaxRetryError

post_url = "http://waifu2x.udp.jp/api"


def main(tg):
    caption = ''
    document = None
    if 'reply_to_message' in tg.message and not tg.message['flagged_message']:
        if 'document' in tg.message['reply_to_message']:
            document = tg.message['reply_to_message']['document']
        elif 'photo' in tg.message['reply_to_message']:
            caption = "Tip: Upload an uncompressed image for higher quality"
            photo_id = tg.message['reply_to_message']['photo'][-1]['file_id']
        else:
            tg.send_message("I can only upscale photos :(")
            return
    elif 'document' in tg.message:
        document = tg.message['document']
    elif 'photo' in tg.message:
        caption = "Tip: Upload an uncompressed image for higher quality"
        photo_id = tg.message['photo'][-1]['file_id']
    elif tg.message['flagged_message']:
        tg.send_message("I can only upscale photos :(")
        return
    else:
        tg.send_message(
            "Send me the image you would like to upscale or reply to an image with /waifu2x", flag_message=True)
        return
    if document:
        mime_type = document['mime_type']
        if 'image' not in mime_type:
            tg.send_message("I can only upscale images :(")
        elif 'gif' in mime_type:
            tg.send_message("I can't upscale gifs :(")
        photo_id = document['file_id']
    tg.send_chat_action("upload_photo")
    document_obj = tg.get_file(photo_id)
    try:
        file_path = tg.download_file(document_obj)
    except OSError:
        tg.send_message("I can't upscale this kind of file :(")
        return
    file = Image.open(file_path)
    file = check_size(file)
    if file:
        file = create_image_obj(file)
        name = "{}.PNG".format(photo_id)
        fields = {'file': (name, file.read()), 'noise': 2, 'scale': 2}
        try:
            x = tg.http.request('POST', post_url, fields=fields)
        except MaxRetryError:
            tg.send_message("It seems waifu2x.udp.jp is down :(")
            return
        tg.send_chat_action("upload_photo")
        tg.send_document((name, x.data), caption=caption)
    else:
        tg.send_message("This image is too big for me to waifu2x :(")


def check_size(image):
    if image.size[0] < 1280 and image.size[1] < 1280:
        return image
    if image.size[0] > 2560 or image.size[1] > 2560:
        return None
    else:
        largest = image.size[0] if image.size[0] > image.size[1] else image.size[1]
        scale = 1280 / largest
        new_dimensions = (int(image.size[0] * scale), int(image.size[1] * scale))
        return image.resize(new_dimensions, Image.LANCZOS)


def create_image_obj(image):
    compressed_image = io.BytesIO()
    image.save(compressed_image, format="PNG")
    compressed_image.seek(0)
    return compressed_image


parameters = {'name': "Waifu2x", 'short_description': "Upscale images!", 'permissions': '11'}

arguments = {'text': ["^/waifu2x"], 'caption': ["^/waifu2x"]}
