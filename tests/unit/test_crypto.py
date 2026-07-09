#  Project:   scalo
#  File:      tests/unit/test_crypto.py
#  Purpose:   CryptoProfile posture: object + primitives, consumed AS-IS by httpx
#  Language:  Python
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED

"""The crypto posture, exercised with a REAL TLS handshake (no mocks): a P-384
self-signed HTTPS server, and httpx consuming both the scalo-minted
ssl.SSLContext (object form) and the CA-path primitive - same posture."""

from __future__ import annotations

import datetime
import http.server
import ssl
import threading

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from scalo.crypto import (
    CryptoProfile,
    PqcMode,
    openssl_supports_pqc,
    ssl_context,
    tls_parts,
)


@pytest.fixture(scope="module")
def https_server(tmp_path_factory):
    """A P-384 self-signed HTTPS server; yields (base_url, ca_file_path)."""
    key = ec.generate_private_key(ec.SECP384R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA384())
    )
    d = tmp_path_factory.mktemp("certs")
    cf, kf = d / "srv.crt", d / "srv.key"
    cf.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    kf.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(str(cf), str(kf))
    srv.socket = sctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"https://localhost:{srv.server_address[1]}/", str(cf)
    srv.shutdown()


def test_default_profile_is_prod_commercial_floor():
    p = CryptoProfile.PROD
    assert p.tls_floor is ssl.TLSVersion.TLSv1_2
    assert p.pqc is PqcMode.PREFER
    assert p.warn_on_downgrade is True


def test_highsec_is_strict():
    assert CryptoProfile.HIGHSEC.tls_floor is ssl.TLSVersion.TLSv1_3
    assert CryptoProfile.HIGHSEC.pqc is PqcMode.REQUIRE


def test_ssl_context_applies_floor_and_aes256(https_server):
    _, ca = https_server
    ctx = ssl_context(CryptoProfile.PROD, cafile=ca)
    assert ctx.minimum_version is ssl.TLSVersion.TLSv1_2
    # highsec floors at 1.3
    assert ssl_context(CryptoProfile.HIGHSEC, cafile=ca).minimum_version is ssl.TLSVersion.TLSv1_3


def test_httpx_consumes_ssl_context_object(https_server):
    url, ca = https_server
    ctx = ssl_context(CryptoProfile.PROD, cafile=ca)
    r = httpx.get(url, verify=ctx)  # object form, AS-IS
    assert r.status_code == 200
    assert r.text == "ok"


def test_httpx_consumes_ca_path_primitive(https_server):
    url, ca = https_server
    parts = tls_parts(CryptoProfile.PROD, ca_paths=[ca])
    r = httpx.get(url, verify=parts.ca_paths[0])  # primitive form, AS-IS
    assert r.status_code == 200


def test_real_handshake_is_tls13_aes256(https_server):
    import socket

    url, ca = https_server
    port = int(url.rsplit(":", 1)[1].rstrip("/"))
    ctx = ssl_context(CryptoProfile.PROD, cafile=ca)
    with socket.create_connection(("localhost", port)) as s, ctx.wrap_socket(s, server_hostname="localhost") as ss:
        assert ss.version() == "TLSv1.3"
        assert ss.cipher()[0] == "TLS_AES_256_GCM_SHA384"


def test_tls_parts_reflect_profile():
    prod = tls_parts(CryptoProfile.PROD, ca_paths=["/tmp/ca.pem"])
    assert prod.min_version == "1.2"
    assert prod.curves[0] == "X25519MLKEM768"
    assert prod.ca_paths == ["/tmp/ca.pem"]
    hs = tls_parts(CryptoProfile.HIGHSEC)
    assert hs.min_version == "1.3"
    assert hs.curves == ["X25519MLKEM768"]


def test_openssl_pqc_capability_is_boolean():
    # This runtime is OpenSSL 3.5+, so PQC is available at the library level.
    assert openssl_supports_pqc() is True


def test_emit_envoy_config():
    from scalo.crypto import emit_envoy_client_traffic_policy

    y = emit_envoy_client_traffic_policy(CryptoProfile.PROD)
    assert 'minVersion: "1.2"' in y
    assert "X25519MLKEM768" in y
    assert "ECDHE-ECDSA-AES256-GCM-SHA384" in y


def test_emit_terraform_and_aws_with_deltas():
    from scalo.crypto import emit_aws_lb_ssl_policy, emit_terraform_tfvars

    assert 'tls_min_version = "1.3"' in emit_terraform_tfvars(CryptoProfile.HIGHSEC)
    name, deltas = emit_aws_lb_ssl_policy(CryptoProfile.PROD)
    assert name == "ELBSecurityPolicy-TLS13-1-2-2021-06"
    assert deltas  # the bundle's shortfalls are recorded, not hidden
