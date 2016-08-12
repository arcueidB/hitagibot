# -*- coding: utf-8 -*-

normal = list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')


def main(tg):
    if tg.message:
        tg.send_chat_action('typing')
        if tg.message['flagged_message']:
            if 'text' in tg.message:
                tg.send_message(tg.message['text'])
            else:
                tg.send_message("I only echo text :(")
        elif 'reply_to_message' in tg.message:
            tg.send_message(tg.message['reply_to_message']['text'])
        elif tg.message['matched_regex'] == arguments['text'][0]:
            tg.send_message("What should I echo?", flag_message=True)
        elif tg.message['matched_regex'] == arguments['text'][1]:
            tg.send_message(tg.message['match'])
    elif tg.inline_query:
        bold_message = "<b>{}</b>".format(tg.inline_query['match'])
        bold_contents = tg.input_text_message_content(bold_message)
        bold = tg.inline_query_result_article(
            "Bold", bold_contents, description=bold_message, thumb_url="https://botnets.me/hitagi/bold.png")

        italic_message = "<i>{}</i>".format(tg.inline_query['match'])
        italic_contents = tg.input_text_message_content(italic_message)
        italic = tg.inline_query_result_article(
            "Italic", italic_contents, description=italic_message, thumb_url="https://botnets.me/hitagi/italic.png")

        code_message = "<code>{}</code>".format(tg.inline_query['match'])
        code_contents = tg.input_text_message_content(code_message)
        code = tg.inline_query_result_article(
            "Code", code_contents, description=code_message, thumb_url="https://botnets.me/hitagi/code.png")

        leet_message = leet_text(tg.inline_query['match'])
        leet_contents = tg.input_text_message_content(leet_message)
        leet = tg.inline_query_result_article(
            "1337", leet_contents, description=leet_message, thumb_url="https://botnets.me/hitagi/1337.png")

        tg.answer_inline_query([bold, italic, code, leet], cache_time=0)


def leet_text(text):
    l33t = list('48CD3F9H1jqLmn0Pkr57UvwxyZ48CD3F9H1jqLmn0Pkr57UvwxyZ')
    for letter in range(len(normal)):
        text = text.replace(normal[letter], l33t[letter])
    return text


parameters = {
    'name': "Echo",
    'short_description': "The echo command repeats your message text.",
    'long_description':
    "The /echo command repeats your message text. You can also use it inline by initiating an "
    "inline chat and typing in <code>echo <your_text></code>.",
    'permissions': "01"
}

arguments = {'text': ["^/echo$", "^/echo (.*)"]}

inline_arguments = ['^/?echo (.*)']
