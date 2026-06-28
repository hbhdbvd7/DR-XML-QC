# XML-QC

DaVinci Resolve XML conform QC tool with a Tkinter GUI.

## Install Into Resolve Scripts

Copy the whole `XML-QC` folder to your Resolve script directory, for example:

`C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Comp\XML-QC`

Then restart DaVinci Resolve. Run it from:

`Workspace > Scripts > Comp > XML-QC > XML-QC`

If your Resolve installation uses a different script folder, keep this folder structure intact:

```text
XML-QC/
  XML-QC.py
  local_conform_qc/
```

## Environment Requirements

- Windows with DaVinci Resolve installed
- Resolve scripting access available to the running Resolve instance
- No extra Python packages are required
- `ffprobe` is recommended in `PATH` for media frame-rate statistics and codec-based proxy detection

The tool tries to import `DaVinciResolveScript` directly from the Resolve script runtime first. If that path is unavailable, it falls back to:

- `RESOLVE_SCRIPT_API`
- `RESOLVE_SCRIPT_LIB`
- `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`

In a normal Resolve installation, manual environment-variable setup is usually not required.

If `ffprobe` is missing, the main flow still works, but media frame-rate statistics may become `unknown`, and ProRes Proxy files cannot be excluded by codec inspection.

## Basic Use

1. Select the project root.
2. Optional: add one or more XML files. If empty, XML-QC uses `project_root\edit\*.xml`.
3. Optional: choose the shot media path. If empty, XML-QC uses `project_root\footage`.
4. Confirm the Resolve project name.
5. Run `XML-QC`.

Reports are written to:

`project_root\QC`

## Folder Rules

- `edit`: XML auto-discovery folder.
- `footage`: shot media auto-discovery folder.
- `ref`: files here are imported into the Resolve `ref` Media Pool folder.
- matched media is imported into `footage/<xml file name>`.
- proxy media is excluded by file name containing `proxy` or ProRes Proxy codec detection.

## Resolve API Boundary

If a requested Resolve internal operation is not exposed by the Resolve scripting API, XML-QC does not attempt unsupported internal modifications.
