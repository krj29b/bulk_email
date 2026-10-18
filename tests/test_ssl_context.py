import ssl

import ssl_context


def test_ssl_context_ciphers():
    assert "ECDH+3DES" not in ssl_context._DEFAULT_CIPHERS
    assert "DH+3DES" not in ssl_context._DEFAULT_CIPHERS
    assert "RSA+3DES" not in ssl_context._DEFAULT_CIPHERS
    assert "!3DES" in ssl_context._DEFAULT_CIPHERS


def test_get_context():
    ctx = ssl_context.get_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    # Verify enabled ciphers do not include 3DES / Triple DES
    cipher_names = [c["name"] for c in ctx.get_ciphers()]
    for cipher_name in cipher_names:
        assert "3DES" not in cipher_name
        assert "DES-CBC3" not in cipher_name
