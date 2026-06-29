# XML-QC for macOS

DaVinci Resolve XML conform QC tool package for macOS.

This release folder contains the actual Resolve script package inside `XML-QC/`.

## Install Into Resolve Scripts

Copy the inner `XML-QC` folder into a Resolve script directory, for example:

```text
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/XML-QC
```

or:

```text
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/XML-QC
```

The final structure should be:

```text
XML-QC/
  XML-QC.py
  local_conform_qc/
```

Then restart DaVinci Resolve and run:

```text
Workspace > Scripts > Comp > XML-QC > XML-QC
```

## Included Files

- `XML-QC/`: Resolve script package
- `XML-QC/run_xml_qc.command`: optional macOS launcher wrapper included with this package

## Environment Requirements

- macOS with DaVinci Resolve installed
- Resolve scripting access available to the running Resolve instance
- No extra Python packages are required
- `ffprobe` is recommended in `PATH` for media frame-rate statistics and codec-based proxy detection

If `ffprobe` is missing, the main flow still works, but media frame-rate statistics may become `unknown`, and ProRes Proxy files cannot be excluded by codec inspection.

## Basic Use

1. Select the project root.
2. Optional: add one or more XML files. If empty, XML-QC uses `project_root/edit/*.xml`.
3. Optional: choose the shot media path. If empty, XML-QC uses `project_root/footage`.
4. Confirm the Resolve project name.
5. Run `XML-QC`.

Reports are written to:

```text
project_root/QC
```

## Resolve API Boundary

If a requested Resolve internal operation is not exposed by the Resolve scripting API, XML-QC does not attempt unsupported internal modifications.
