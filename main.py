import smtplib
import logging

from pprint import pprint as pp

import ssl_context
from messages import MESSAGE_TEXT as message_text, SUBJECT as subject
from messages import build_message
from config import Config

c = Config()
c.init()

logging.basicConfig(
    filename=c.config['logging']['log_file'],
    encoding='utf-8',
    level=getattr(logging, c.config['logging']['log_level'])
)
log = logging.getLogger()

sender = c.config['sender']

with open('data/email_list.txt', 'r') as f:
    recipient_list = f.readlines()

recipient_list = [email.strip('\n') for email in recipient_list]

#pp(recipient_list)

context = ssl_context.get_context()

with smtplib.SMTP(c.config['smtp_server'], c.config['port']) as server:
    server.starttls(context=context)
    server.login(c.config['login'], c.config['password'])

    for recipient_email in recipient_list:
        msg = build_message(subject, sender, recipient_email, message_text)
        server.send_message(msg)
        log.info(f'Sent to {recipient_email}')
