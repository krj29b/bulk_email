import ssl
from unittest.mock import MagicMock, patch

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


def test_get_context_config_default():
    mock_config = MagicMock()
    mock_config.config = {'ssl': {'context': 'default'}}
    with patch('ssl_context.Config', return_value=mock_config):
        ctx = ssl_context.get_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_get_context_config_unverified():
    mock_config = MagicMock()
    mock_config.config = {'ssl': {'context': 'unverified'}}
    with patch('ssl_context.Config', return_value=mock_config):
        ctx = ssl_context.get_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE


def test_get_context_config_passed_explicitly():
    ctx_unverified = ssl_context.get_context(config={'ssl': {'context': 'unverified'}})
    assert isinstance(ctx_unverified, ssl.SSLContext)
    assert ctx_unverified.verify_mode == ssl.CERT_NONE

    ctx_default = ssl_context.get_context(config={'ssl': {'context': 'default'}})
    assert isinstance(ctx_default, ssl.SSLContext)
    assert ctx_default.verify_mode == ssl.CERT_REQUIRED


def test_get_context_config_exception_or_missing_ssl():
    mock_config = MagicMock()
    mock_config.config = None
    mock_config.init.side_effect = Exception("Config error")
    with patch('ssl_context.Config', return_value=mock_config):
        ctx = ssl_context.get_context()
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_REQUIRED
