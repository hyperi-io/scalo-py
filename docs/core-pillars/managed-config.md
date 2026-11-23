# Managed config

An app can take part of its config from Group Policy on Windows, or from an MDM profile on macOS (Jamf, Intune). It names its store, and scalo-py reads that store on every load and reload. Nothing is read until an app names one. Linux has no managed layer: manage it with the config files.

```python
from scalo.config import ManagedSource, get_config

source = ManagedSource(windows_key=r"Example\App", macos_domain="com.example.app")
config = get_config(managed=source)
```

A `ServiceApp` sets the class attribute `managed_source = source` instead.

## Precedence

CLI flag, then env vars and `.env`, then the managed store, then `settings.{env}.yaml`, `settings.yaml` and `defaults.yaml`. A policy beats a local file edit, and an administrator on the box can still override it with an env var or a flag.

A key absent from the store changes nothing. A list from the store replaces the one beneath it, so a local file can't add entries to it.

## Windows -- Group Policy

scalo-py reads `HKLM\SOFTWARE\Policies\<windows_key>`. Administrators and SYSTEM alone can write there.

- A subkey is a section: `Example\App\sink\tls` is `sink.tls`.
- `REG_DWORD` and `REG_QWORD` are integers. `REG_MULTI_SZ` is a list of strings.
- `REG_SZ` reads as the same text does in an env var: `true` is a bool, `8443` an int, `[{name="a"}]` a list of tables.
- A name holding `__` nests as an env var name does, so a value `sink__port` is `sink.port`.
- Any other type is skipped, with a warning naming the value.

In a GPO, add the values as registry preference items under Computer Configuration > Preferences > Windows Settings > Registry, with hive `HKEY_LOCAL_MACHINE` and key path `SOFTWARE\Policies\Example\App\sink`. Tick "Remove this item when it is no longer applied" so the value goes when the GPO does. The same values by hand:

```bat
reg add "HKLM\SOFTWARE\Policies\Example\App\sink" /v port /t REG_DWORD /d 8443 /f
reg add "HKLM\SOFTWARE\Policies\Example\App\sink" /v hosts /t REG_MULTI_SZ /d "a.example.com\0b.example.com" /f
```

## macOS -- Jamf or another MDM

scalo-py reads `/Library/Managed Preferences/<macos_domain>.plist`, the machine-level file a configuration profile writes. The per-user folders beside it are ignored. A file not owned by root, or writable by its group or anyone, is skipped with a warning.

A dict is a section and an array a list. Strings, integers, reals and booleans are their scalars, and a string is never parsed, so `true` in a `<string>` stays text. Any other type is skipped, with a warning naming the key.

In Jamf Pro, add an Application & Custom Settings payload to a computer configuration profile, with preference domain `com.example.app` and this property list:

```xml
<dict>
  <key>sink</key>
  <dict>
    <key>port</key><integer>8443</integer>
    <key>hosts</key><array><string>a.example.com</string></array>
  </dict>
</dict>
```

## Secrets

Every domain user can read a GPO's `Registry.pol` in SYSVOL, so a secret never comes from policy. The load fails with an error naming the key when a key's last name, in any case, is one of `password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `private_key`, `credential` or `credentials`, or ends in `_` and one of them. So `kafka.sasl_password` and `auth.token` fail, and `max_tokens` and `verify_cert` load. Set the key's file-path form, a name ending `_file` or `_path`, and put the secret in that file.

## Logs and provenance

The layer logs at info when it reads a store, with the source and the key count, and at debug for each key name, never a value. A skipped value or an untrusted plist logs a warning, and a refused secret an error.

`dynaconf.inspect_settings(settings, "sink.port")` lists the layer as loader `managed`, with the registry key or plist path as its identifier.

Up: [config.md](config.md).
