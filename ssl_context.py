import ssl

_DEFAULT_CIPHERS = (
    "ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:"
    "DH+HIGH:RSA+AESGCM:RSA+AES:RSA+HIGH:!aNULL:"
    "!eNULL:!MD5:!3DES"
)


def get_context() -> ssl.SSLContext:
    # only TLSv1 or higher
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3

    context.set_ciphers(_DEFAULT_CIPHERS)
    context.set_default_verify_paths()
    context.verify_mode = ssl.CERT_REQUIRED
    return context
