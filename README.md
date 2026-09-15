# YKW 3DS to Switch Save Converter

An experimental converter for moving a **Yo-kai Watch 1** Nintendo 3DS `.yw`
save into the Nintendo Switch save layout.

The project includes:

- A command-line converter
- A native desktop interface using Tkinter
- A static, client-side GitHub Pages interface
- A bundled fresh Switch save template
- Structural, checksum, and migration validation

> Keep backups. Save conversion is inherently experimental. The
> **Requests Completed** record is a known pending mapping issue.

## What is transferred

- Player name, location transform, map, playtime, and watch rank
- Inventory, equipment, and key items
- Owned Yo-kai and nicknames
- Party/formation data
- Story and active-objective state
- Persistent world/event and interactable flags
- Records/settings and opaque game state where the layouts are compatible

Switch-only metadata and capacity with no 3DS equivalent are retained from the
bundled template. Handheld-only sections are not injected into the Switch save.

## Command line

Python 3.10 or newer is recommended. No third-party package is required for
conversion.

```bash
python ykw_3ds_to_switch.py "game1.yw" "game1-switch.yw"
```

To replace an existing output:

```bash
python ykw_3ds_to_switch.py --force "game1.yw" "game1-switch.yw"
```

An advanced user can supply another fresh Switch template:

```bash
python ykw_3ds_to_switch.py --template "fresh-switch.yw" "game1.yw" "game1-switch.yw"
```

## Desktop UI

```bash
python desktop_ui.py
```

Tkinter is included with standard Windows and macOS Python distributions. On
some Linux distributions it is packaged separately as `python3-tk`.

## GitHub Pages web UI

The web converter is completely static. It uses Pyodide to run the same Python
converter locally inside the browser; selected saves are never uploaded.


The public repository does not need to include personal 3DS saves. The bundled
Switch template is sufficient for the template-validation tests; development
sample tests skip automatically when no sample exists.

## Compatibility and safety

- Supported input: Yo-kai Watch 1 3DS save, exactly `0x96e0` bytes
- Produced output: Switch-layout save, exactly `0xb9cc` bytes
- Existing input files are never modified
- CLI output is not overwritten unless `--force` is supplied
- CRC, container layout, section layout, and migrated fields are validated
  before output is written

This project is not affiliated with Nintendo or LEVEL-5. Use it only with save
data you own and have backed up.

## License

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
