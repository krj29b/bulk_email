from email.message import EmailMessage


def build_message(subject, sender, email, message_text):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = email
    msg.set_content(message_text)
    return msg

SUBJECT = "SAMPLE SUBJECT"

MESSAGE_TEXT = """Hello,

Leverage agile frameworks to provide a robust synopsis for high level overviews.
Iterative approaches to corporate strategy foster collaborative thinking to further the overall value proposition.
Organically grow the holistic world view of disruptive innovation via workplace diversity and empowerment.

Best regards
ABCD"""

