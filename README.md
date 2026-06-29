# DR-XML-QC

`DR-XML-QC` is a DaVinci Resolve XML conform QC toolset for local finishing workflows.

This workspace now maintains two standalone release packages:

- `XML-QC-win/`: Windows package for Resolve `Workspace > Scripts`
- `XML-QC-mac/`: macOS package for Resolve `Workspace > Scripts`

The development-source copy remains under `20260626_local conform qc/`.

## Repository Layout

- `XML-QC-win/`: current Windows standalone release package
- `XML-QC-mac/`: current macOS standalone release package
- `20260626_local conform qc/`: development-source copy used during implementation and verification

Generated QC reports, cache files, test scripts, sample assets, and internal planning files are not part of the release package.

## Main Capabilities

- import selected XML files or auto-discover XML files under `project_root/edit`
- import shot media from a selected path or auto-discover under `project_root/footage`
- import project-level `ref` media into Resolve's `ref` Media Pool folder
- exclude proxy media by file name and ProRes Proxy codec detection
- create per-XML subfolders under `footage` so multiple XML imports stay separated
- set the Resolve timeline frame rate from the XML when the Resolve API exposes that setting
- compare XML clips against Resolve timeline clips and generate Chinese QC reports
- write reports to `project_root/QC`

## Packages

### Windows

Use [XML-QC-win](XML-QC-win).

Install by copying the whole folder content into a Resolve script folder so the final structure is:

```text
C:\ProgramData\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Comp\XML-QC\
  XML-QC.py
  local_conform_qc\
```

### macOS

Use [XML-QC-mac](XML-QC-mac).

The actual script package is the inner `XML-QC` folder:

```text
XML-QC-mac/
  README.md
  XML-QC/
    XML-QC.py
    local_conform_qc/
```

Copy that inner `XML-QC` folder into one of Resolve's macOS script folders, for example:

```text
~/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/XML-QC
```

or:

```text
/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Comp/XML-QC
```

## Environment Requirements

- DaVinci Resolve installed
- Resolve scripting access available to the running Resolve instance
- No extra Python packages are required; the tool uses bundled scripts plus the Python standard library
- `ffprobe` is recommended in `PATH` for media frame-rate statistics and codec-based proxy detection

The tool first tries to import `DaVinciResolveScript` directly from the Resolve runtime. If that is unavailable, it falls back to common Resolve scripting locations and environment variables.

If `ffprobe` is missing, the main conform flow still runs, but:

- media frame-rate statistics may show `unknown`
- ProRes Proxy files cannot be excluded by codec inspection
- file names containing `proxy` are still excluded

## Resolve API Boundary

If a requested internal Resolve operation is not exposed by the Resolve scripting API, this project does not attempt an unsupported internal workaround.
