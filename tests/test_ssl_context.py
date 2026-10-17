import ssl
import warnings

import ssl_context


def test_get_context_returns_valid_ssl_context():
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        context = ssl_context.get_context()

        # Check no DeprecationWarning was emitted
        deprecation_warnings = [
            w for w in recorded_warnings if issubclass(w.category, DeprecationWarning)
        ]
        assert len(deprecation_warnings) == 0

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
