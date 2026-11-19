# vc_redist.x64.exe goes here — place it by hand

This step was blocked by the project's no-networking rule (CLAUDE.md
hard constraint 1): nothing in this repo or its build/installer tooling
downloads anything. `installer/derby.iss` already handles this file's
absence correctly (it checks `skipifsourcedoesntexist` at compile time
and shows a clear Arabic message directing the owner to install the
redistributable manually if it's both missing here and missing on the
target machine) — but the installer cannot silently install the
redistributable for people unless this file is actually present.

## What to add

Download the **x64** Visual C++ 2015-2019 Redistributable from Microsoft:

https://aka.ms/vs/17/release/vc_redist.x64.exe

Save it as:

```
installer/redist/vc_redist.x64.exe
```

## After adding the file

1. Delete this placeholder file.
2. Re-run `.venv\Scripts\python.exe tools\write_installer_version.py`
   and recompile the installer (`ISCC.exe installer\derby.iss`) — Inno
   Setup bundles the file into the installer automatically once it's
   present; no `.iss` changes are needed.
