import ssl

import ssl_context


def test_get_context_returns_valid_context():
    context = ssl_context.get_context()
    assert isinstance(context, ssl.SSLContext)


def test_get_context_security_options():
    context = ssl_context.get_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert (context.options & ssl.OP_NO_SSLv2) == ssl.OP_NO_SSLv2
    assert (context.options & ssl.OP_NO_SSLv3) == ssl.OP_NO_SSLv3
