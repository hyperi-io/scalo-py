# License

AES-256-GCM-encrypted, Ed25519-signed license files. Direct port of
`hyperi-rustlib/src/license/` — encrypted bytes from one language load
cleanly in the other. Singleton lifecycle: `init()` once at startup,
`get()` / `has_feature()` everywhere else.

```
pip install hyperi-pylib[license]
```

Pulls in `cryptography` (for AES-GCM and Ed25519) and `httpx` (for URL
loading).

---

## Quick start

```python
from hyperi_pylib import license

license.init_default()                  # load from standard paths
settings = license.get()                # LicenseSettings
print(settings.tier, settings.expires_at)

if license.has_feature("advanced-analytics"):
    enable_advanced_module()
```

---

## Search cascade

`License.load(opts)` looks in this order, stopping at the first hit:

1. **Explicit path** — `LicenseOptions(license_path=Path("..."))`
2. **`HYPERI_LICENSE_PATH`** env var
3. **Standard paths** —
   - `./license.enc`, `./.license.enc`
   - `/etc/hyperi/license.enc`
   - `$XDG_CONFIG_HOME/hyperi/license.enc` (or `~/.config/hyperi/license.enc`)
   - `~/.hyperi/license.enc`
   - Plus pre-rebrand `hypersec` variants for backward compatibility
4. **`HYPERI_LICENSE_URL`** env var (or `LicenseOptions(license_url=...)`)
   — fetched via `httpx.get` with a 30 s timeout
5. **Compiled-in defaults** — the Community-tier fallback shipped in
   `hyperi_pylib.license.defaults`

A non-default license that fails to verify (signature, expiry,
decryption) raises immediately. Standard-path candidates that exist but
fail to decrypt are skipped — the cascade keeps walking.

---

## Encrypted format

Cross-language identical:

```
[12-byte nonce][ciphertext + 16-byte GCM tag]
```

- Encryption: AES-256-GCM (`cryptography.hazmat.primitives.ciphers.aead`).
- Key derivation: `SHA-256(secret || "hs-rustlib-license-v1")`. The
  domain separator is fixed — changing it breaks every existing
  license file.
- Nonce: 12 bytes from `os.urandom`, prepended to the ciphertext.

Files written by Rust's `hs-rustlib::license::crypto::encrypt` decrypt
in Python. Files written by Python's `license.crypto.encrypt` decrypt
in Rust. The Ed25519 signature on the inner JSON payload is verified
on load whenever `LicenseOptions.verify_signature=True` (the default
for non-default licenses).

---

## Singleton API

```python
from hyperi_pylib import license

license.init()                  # init with default options
license.init_default()          # equivalent shortcut
license.init(license.LicenseOptions(license_path=Path("/etc/myapp/license.enc")))

settings = license.get()        # raises LicenseNotInitializedError if not init'd
settings = license.try_get()    # returns None if not init'd

if license.has_feature("kafka-tier"):
    ...

if license.is_default():
    logger.warning("Running on Community tier — features X/Y disabled")

license.verify_integrity()      # re-check tampering and expiry
license.reset()                 # testing only
```

`init` is **single-shot** — calling it twice raises
`LicenseAlreadyInitializedError`. Wire it into application startup
(e.g., the `DfeApp.run_service` entry path).

The `License` instance — useful when you need source metadata — is
available via `license.get_license()`:

```python
mgr = license.get_license()
print(mgr.source)            # LicenseSource.FILE / URL / DEFAULT
print(mgr.source_info.path)  # which path / URL it came from
```

---

## Types

`LicenseSettings` (from `hyperi_pylib.license.types`) carries:

| Field | Meaning |
|-------|---------|
| `tier` | Subscription tier name |
| `customer` | Customer identifier |
| `expires_at` | ISO timestamp or `None` for perpetual |
| `features` | Set of enabled feature flags |
| `is_default` | True for the compiled Community fallback |
| `signature` | Ed25519 signature (verified at load) |

`LicenseSourceInfo`:

| Field | Meaning |
|-------|---------|
| `source` | `LicenseSource.FILE` / `URL` / `DEFAULT` |
| `path` | `Path` when `source=FILE` |
| `url` | `str` when `source=URL` |

`LicenseOptions`:

| Arg | Default | Meaning |
|-----|---------|---------|
| `license_path` | None | Skip the cascade, use this file. |
| `license_url` | None | Used at step 4 if env var also unset. |
| `verify_signature` | True | Ed25519 signature check (skipped for default). |
| `allow_expired` | False | Load expired licenses with a WARN instead of raising. |
| `custom_key` | None | Use this secret instead of the compiled-in key. |

---

## Feature gating

```python
def export_to_clickhouse(df):
    if not license.has_feature("clickhouse-export"):
        raise FeatureNotLicensedError("clickhouse-export")
    ...
```

`has_feature` returns `False` (not raises) when the license is
uninitialised — services that haven't called `init()` yet appear
feature-less, which is safer than crashing on a missing setup step.

---

## Tampering checks

```python
license.verify_integrity()
```

Recomputes the SHA-256 hash of `LicenseSettings` and compares against
the hash captured at load time. Raises `LicenseIntegrityError` on
mismatch and `LicenseExpiredError` if the license expired since load.
Cheap enough to run on every health probe.

---

## Building license files (operator tooling)

```python
from hyperi_pylib.license import LicenseSettings
from hyperi_pylib.license.manager import encrypt_license, decrypt_license

settings = LicenseSettings(
    tier="enterprise",
    customer="acme-corp",
    expires_at="2027-01-01T00:00:00Z",
    features={"kafka-tier", "clickhouse-export", "advanced-analytics"},
)

key = b"32-byte-secret-known-to-issuer.."
encrypted = encrypt_license(settings, key)
Path("/etc/hyperi/license.enc").write_bytes(encrypted)

# Verify it loads back
decrypted = decrypt_license(encrypted, key)
assert decrypted.tier == "enterprise"
```

`encrypt_license` / `decrypt_license` are for **issuer-side** tooling —
not for normal runtime use. Wrap them in a CLI behind operator
authentication.

---

## Errors

| Exception | When |
|-----------|------|
| `LicenseNotInitializedError` | `get()` / `verify_integrity()` before `init()` |
| `LicenseAlreadyInitializedError` | Second `init()` call |
| `LicenseLoadError` | File could not be read |
| `LicenseDecryptionError` | AES-GCM auth failure (wrong key or tampered data) |
| `LicenseParseError` | Decrypted JSON malformed |
| `LicenseSignatureError` | Ed25519 signature did not verify |
| `LicenseExpiredError` | Expired and `allow_expired=False` |
| `LicenseFetchError` | `httpx.get` failed when loading from URL |
| `LicenseIntegrityError` | `verify_integrity()` detected post-load mutation |

---

## Related

- [SECRETS.md](SECRETS.md)
- [VERSION-CHECK.md](VERSION-CHECK.md)
- [../core-pillars/CONFIG.md](../core-pillars/CONFIG.md)
- [../runtime/RUNTIME-CONTEXT.md](../runtime/RUNTIME-CONTEXT.md)
- [../EXTRAS-FLAGS.md](../EXTRAS-FLAGS.md)
- [../INTEGRATION.md](../INTEGRATION.md)
