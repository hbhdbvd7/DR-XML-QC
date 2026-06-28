# DR-XML-QC

`DR-XML-QC` is a standalone DaVinci Resolve XML conform QC script package.

The release tool is kept under `XML-QC/` so the whole folder can be copied directly into Resolve's script menu path.

## Repository Layout

- `XML-QC/XML-QC.py`: Resolve script-menu entrypoint
- `XML-QC/local_conform_qc/`: bundled core package
- `XML-QC/local_conform_qc_cli.py`: local CLI entrypoint

## Main Capabilities

- import selected XML files or auto-discover XML files under `project_root/edit`
- import shot media from a selected path or auto-discover under `project_root/footage`
- import project-level `ref` media into Resolve's `ref` Media Pool folder
- exclude proxy media by file name and ProRes Proxy codec detection
- create per-XML subfolders under `footage` so multiple XML imports stay separated
- set the Resolve timeline frame rate from the XML when the Resolve API exposes that setting
- compare XML clips against Resolve timeline clips and generate Chinese QC reports
- write reports to `project_root/QC`

## Install

Copy the whole `XML-QC` folder to a Resolve script directory such as:

```text
C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Comp\XML-QC
```

Restart Resolve, then run:

```text
Workspace > Scripts > Comp > XML-QC > XML-QC
```

## Environment Requirements

- Windows with DaVinci Resolve installed
- Resolve scripting access available to the running Resolve instance
- No extra Python packages are required; the tool uses the bundled scripts and Python standard library
- `ffprobe` is recommended in `PATH` for media frame-rate statistics and codec-based proxy detection

The tool first tries to import `DaVinciResolveScript` directly from the Resolve script runtime. If that is not available, it falls back to:

- `RESOLVE_SCRIPT_API`
- `RESOLVE_SCRIPT_LIB`
- `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules`

In a normal Resolve installation, manual environment-variable setup is usually not required.

If `ffprobe` is missing, the main conform flow still runs, but:

- media frame-rate statistics may show `unknown`
- ProRes Proxy files cannot be excluded by codec inspection
- file names containing `proxy` are still excluded

## Resolve API Boundary

If a requested internal Resolve operation is not exposed by the Resolve scripting API, the tool does not attempt unsupported internal modifications.
