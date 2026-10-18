import ssl
from typing import Any

from config import Config

_DEFAULT_CIPHERS = (
    'ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:'
    'DH+HIGH:RSA+AESGCM:RSA+AES:RSA+HIGH:!aNULL:!eNULL:!MD5:!3DES'
)


def get_context(config: dict[str, Any] | None = None) -> ssl.SSLContext:
    """Returns a secure SSLContext using recommended TLS defaults or user config."""
    if config is None:
        try:
            c = Config()
            if c.config is None:
                c.init()
            ssl_cfg = c.config.get('ssl', {}) if c.config else {}
        except Exception:
            ssl_cfg = {}
    else:
        ssl_cfg = config.get('ssl', {}) if isinstance(config, dict) else {}

    context_type = ssl_cfg.get('context', 'default') if isinstance(ssl_cfg, dict) else 'default'

    if context_type == 'unverified':
        context = ssl._create_unverified_context()
    else:
        context = ssl.create_default_context()

    context.set_ciphers(_DEFAULT_CIPHERS)
    return context
