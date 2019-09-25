"""These tests rely on replies from public internet services

TODO: reimplement with local stubs
"""
import httplib2
import os
import pytest
import ssl
import sys
import tests


def test_get_301_via_https():
    # Google always redirects to http://google.com
    http = httplib2.Http()
    response, content = http.request("https://code.google.com/apis/", "GET")
    assert response.status == 200
    assert response.previous.status == 301


def test_get_via_https():
    # Test that we can handle HTTPS
    http = httplib2.Http()
    response, content = http.request("https://google.com/adsense/", "GET")
    assert response.status == 200


def test_get_via_https_spec_violation_on_location():
    # Test that we follow redirects through HTTPS
    # even if they violate the spec by including
    # a relative Location: header instead of an
    # absolute one.
    http = httplib2.Http()
    response, content = http.request("https://google.com/adsense", "GET")
    assert response.status == 200
    assert response.previous is not None


def test_get_via_https_key_cert():
    #  At this point I can only test
    #  that the key and cert files are passed in
    #  correctly to httplib. It would be nice to have
    #  a real https endpoint to test against.
    http = httplib2.Http(timeout=2)
    http.add_certificate("akeyfile", "acertfile", "bitworking.org")
    try:
        http.request("https://bitworking.org", "GET")
    except AttributeError:
        assert http.connections["https:bitworking.org"].key_file == "akeyfile"
        assert http.connections["https:bitworking.org"].cert_file == "acertfile"
    except IOError:
        # Skip on 3.2
        pass

    try:
        http.request("https://notthere.bitworking.org", "GET")
    except httplib2.ServerNotFoundError:
        assert http.connections["https:notthere.bitworking.org"].key_file is None
        assert http.connections["https:notthere.bitworking.org"].cert_file is None
    except IOError:
        # Skip on 3.2
        pass


def test_get_via_https_key_cert_password():
    #  At this point I can only test
    #  that the key and cert files are passed in
    #  correctly to httplib. It would be nice to have
    #  a real https endpoint to test against.
    http = httplib2.Http(timeout=2)
    http.add_certificate("akeyfile", "acertfile", "", "apassword")
    try:
        with tests.MockHttpServer(use_ssl=True) as server:
            http.request(server.url, "GET")
    except AttributeError:
        assert http.connections["https:localhost"].key_file == "akeyfile"
        assert http.connections["https:localhost"].cert_file == "acertfile"
        assert http.connections["https:localhost"].key_password == "apassword"
    except IOError:
        # Catch 'No such file or directory' since filenames are fake
        pass

    try:
        http.request("https://notthere", "GET")
    except httplib2.ServerNotFoundError:
        assert http.connections["https:notthere"].key_file is None
        assert http.connections["https:notthere"].cert_file is None
        assert http.connections["https:notthere"].key_password is None
    except IOError:
        # Catch 'No such file or directory' since filenames are fake
        pass


def test_get_via_https_key_cert_password_with_pem():
    with tests.MockHttpServer(use_ssl=True) as server:
        # load matching server cert to avoid verification failure
        http = httplib2.Http(ca_certs=server.certfile)
        # load client cert to be presented when server asks for it
        http.add_certificate(tests.CLIENT_CERTFILE, tests.CLIENT_CERTFILE,
                             '', tests.CLIENT_CERT_PASSWORD)
        response, content = http.request(server.url, "GET")
        assert response.status == 200
        # verify that client cert was presented with matching serial number
        assert server.server.last_client_cert["serialNumber"] == tests.CLIENT_CERT_SERIAL

        # try invalid password
        http = httplib2.Http(ca_certs=server.certfile)
        # load client cert to be presented when server asks for it
        http.add_certificate(tests.CLIENT_CERTFILE, tests.CLIENT_CERTFILE,
                             "", "invalid")
        with tests.assert_raises(ssl.SSLError):
            http.request(server.url, "GET")


def test_ssl_invalid_ca_certs_path():
    # Test that we get an ssl.SSLError when specifying a non-existent CA
    # certs file.
    http = httplib2.Http(ca_certs="/nosuchfile")
    with tests.assert_raises(IOError):
        http.request("https://www.google.com/", "GET")


@pytest.mark.xfail(
    sys.version_info <= (3,),
    reason=(
        "FIXME: for unknown reason Python 2.7.10 validates www.google.com "
        "against dummy CA www.example.com"
    ),
)
def test_ssl_wrong_ca():
    # Test that we get a SSLHandshakeError if we try to access
    # https://www.google.com, using a CA cert file that doesn't contain
    # the CA Google uses (i.e., simulating a cert that's not signed by a
    # trusted CA).
    other_ca_certs = os.path.join(
        os.path.dirname(os.path.abspath(httplib2.__file__)), "test", "other_cacerts.txt"
    )
    assert os.path.exists(other_ca_certs)
    http = httplib2.Http(ca_certs=other_ca_certs)
    http.follow_redirects = False
    with tests.assert_raises(ssl.SSLError):
        http.request("https://www.google.com/", "GET")


def test_sni_hostname_validation():
    # TODO: make explicit test server with SNI validation
    http = httplib2.Http()
    http.request("https://google.com/", method="GET")


@pytest.mark.skipif(
    os.environ.get("TRAVIS_PYTHON_VERSION") in ("2.7", "pypy"),
    reason="Python 2.7 doesn't support TLS min/max"
)
def test_min_tls_version():
    # skip on Python versions that don't support TLS min
    if not hasattr(ssl.SSLContext(), 'minimum_version'):
        return
    # BadSSL server that supports max TLS 1.1,
    # forcing 1.2 should always fail
    http = httplib2.Http(tls_minimum_version="TLSv1_2")
    with tests.assert_raises(ssl.SSLError):
        http.request("https://tls-v1-1.badssl.com:1011/")


@pytest.mark.skipif(
    os.environ.get("TRAVIS_PYTHON_VERSION") in ("2.7", "pypy"),
    reason="Python 2.7 doesn't support TLS min/max"
)
def test_max_tls_version():
    # skip on Python versions that don't support TLS max
    if not hasattr(ssl.SSLContext(), 'maximum_version'):
        return
    # Google supports TLS 1.2+, confirm we can force down to 1.0
    # this may break whenever Google disables TLSv1
    http = httplib2.Http(tls_maximum_version="TLSv1")
    http.request("https://google.com")
    _, tls_ver, _ = http.connections['https:google.com'].sock.cipher()
    assert tls_ver == "TLSv1.0"
