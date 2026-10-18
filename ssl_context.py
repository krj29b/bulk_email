import ssl

_DEFAULT_CIPHERS = (
    'ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:'
    'DH+HIGH:RSA+AESGCM:RSA+AES:RSA+HIGH:!3DES:!aNULL:'
    '!eNULL:!MD5'
)


def get_context() -> ssl.SSLContext:
    """Returns a secure SSLContext using recommended TLS defaults."""
    context = ssl.create_default_context()
    context.set_ciphers(_DEFAULT_CIPHERS)
    return context
