"""
Uploads a compressed version of uncompressed images.
"""

import io
import subprocess
import re
from PIL import Image


def main(tg):
    """
    Ignores gifs. Downloads an image, downscales, then uploads as a jpeg.
    """
    if tg.message:
        upload_photo(tg)
    else:
        send_exif(tg)


def send_exif(tg):
    file_id = tg.callback_query['data'].replace("exif", '')
    document_obj = tg.get_file(file_id)
    file_path = tg.download_file(document_obj)
    message = "<code>{}</code>".format(get_exif(file_path))
    if tg.callback_query['from']['id'] == tg.callback_query['message']['chat']['id']:
        response_text = None
        reply_to_id = tg.callback_query['message']['message_id']
    else:
        response_text = "I've sent you the exif data in a private message"
        reply_to_id = None
    response = tg.send_message(message, chat_id=tg.callback_query['from']['id'], reply_to_message_id=reply_to_id)
    if response and response['ok']:
        tg.answer_callback_query(response_text)
    else:
        tg.answer_callback_query(
            "I was unable to send you the exif data. Try unblocking or messaging me", show_alert=True)


def upload_photo(tg):
    if 'gif' in tg.message['document']['mime_type']:
        return
    file_id = tg.message['document']['file_id']
    document_obj = tg.get_file(file_id)
    tg.send_chat_action('upload_photo')
    file_path = tg.download_file(document_obj)
    photo = Image.open(file_path)
    if get_exif(file_path):
        keyboard = tg.inline_keyboard_markup([[{'text': "View exif data", 'callback_data': "exif{}".format(file_id)}]])
    else:
        keyboard = None
    photo = resize_image(photo)
    photo = compress_image(photo)
    name = document_obj['result']['file_id'] + ".jpg"
    tg.send_photo(
        (name, photo.read()),
        disable_notification=True,
        reply_to_message_id=tg.message['message_id'],
        reply_markup=keyboard)
    photo.close()


def resize_image(image):
    """
    Resizes an image if its height or width > 1600. Uses lanczos downscaling.
    """
    if image.size[0] > 1600 or image.size[1] > 1600:
        larger = image.size[0] if image.size[0] > image.size[1] else image.size[1]
        scale = 1600 / larger
        new_dimensions = (int(image.size[0] * scale), int(image.size[1] * scale))
        resized_image = image.resize(new_dimensions, Image.LANCZOS)
        image.close()
        return resized_image
    return image


def compress_image(image):
    """
    Saves a jpeg copy of the image in a BytesIO object with quality set to 100.
    """
    compressed_image = io.BytesIO()
    try:
        image.save(compressed_image, format='JPEG', quality=90)
    except OSError:  # For "cannot write mode P as JPEG"
        to_rgb = image.convert('RGB')
        to_rgb.save(compressed_image, format='JPEG', quality=90)
        to_rgb.close()
    image.close()
    compressed_image.seek(0)
    return compressed_image


def get_exif(file_path):
    try:
        output = subprocess.check_output(["exiv2", file_path])
        return format_exif(output)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return


def format_exif(exif_data):
    exif = exif_data.decode("utf8", "ignore")
    split_exif = exif.split('\n')
    formatted_exif = ""
    for line in split_exif[1:]:
        if re.match(".*:.+", line.replace(' ', '')):
            formatted_exif += line + "\n"
    return formatted_exif


parameters = {
    'name': "Auto upload",
    'short_description':
    "Automatically uploads your uncompressed images for you",
    'permissions': "11"
}

arguments = {'document': {'mime_type': ['image']}}
