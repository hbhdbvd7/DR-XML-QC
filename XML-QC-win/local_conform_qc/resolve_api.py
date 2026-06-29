"""DaVinci Resolve API integration helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Iterable

from .models import Issue, ResolveImportAttempt, ResolveImportResult, TimelineItemRecord, TimelineReadbackResult


MEDIA_POOL_FOLDERS = {
    "footage": "footage",
    "ref": "ref",
    "edit": "edit",
    "tc": "TC",
    "look": "定调",
}
IMPORTABLE_REF_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".m4v",
    ".mov",
    ".mp3",
    ".mp4",
    ".mxf",
    ".png",
    ".tif",
    ".tiff",
    ".wav",
}


def safe_call(label: str, func: object, *args: object, **kwargs: object) -> tuple[bool, Any]:
    """Call a Resolve API function without letting one failure stop the run."""
    if not callable(func):
        return False, f"{label} is not callable"
    try:
        return True, func(*args, **kwargs)
    except Exception as exc:  # Resolve can raise opaque bridge exceptions.
        return False, f"{label} failed: {exc}"


def connect_resolve() -> object:
    """Connect to the running DaVinci Resolve instance."""
    try:
        import DaVinciResolveScript as dvr_script

        resolve = dvr_script.scriptapp("Resolve")
        if resolve is not None:
            return resolve
    except ImportError:
        pass

    api_dir = os.environ.get("RESOLVE_SCRIPT_API", "").strip()
    lib_path = os.environ.get("RESOLVE_SCRIPT_LIB", "").strip()
    if not api_dir:
        common_modules_dir = Path(
            r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"
        )
        if common_modules_dir.is_dir():
            sys.path.insert(0, str(common_modules_dir))
        else:
            raise RuntimeError("RESOLVE_SCRIPT_API is not set and Resolve scripting modules were not found.")
    else:
        modules_dir = Path(api_dir) / "Modules"
        if not modules_dir.is_dir():
            raise RuntimeError(f"Resolve Modules directory was not found: {modules_dir}")

        modules_dir_text = str(modules_dir)
        if modules_dir_text not in sys.path:
            sys.path.insert(0, modules_dir_text)

    if lib_path:
        lib_parent = str(Path(lib_path).expanduser().resolve().parent)
        os.environ["PATH"] = lib_parent + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(lib_parent)

    import DaVinciResolveScript as dvr_script

    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        raise RuntimeError("Could not connect to a running DaVinci Resolve instance.")
    return resolve


def open_or_create_project(resolve: object, project_name: str):
    """Open an existing project, or create it when missing."""
    project_manager = resolve.GetProjectManager()
    if project_manager is None:
        raise RuntimeError("Could not get Resolve ProjectManager.")

    project = project_manager.LoadProject(project_name)
    if project is not None:
        return project

    project = project_manager.CreateProject(project_name)
    if project is None:
        raise RuntimeError(f"Could not open or create Resolve project: {project_name}")
    return project


def get_current_project(resolve: object):
    """Return the current Resolve project."""
    project_manager = resolve.GetProjectManager()
    if project_manager is None:
        raise RuntimeError("Could not get Resolve ProjectManager.")
    project = project_manager.GetCurrentProject()
    if project is None:
        raise RuntimeError("No current Resolve project is open.")
    return project


def ensure_media_pool_folders(project: object) -> dict[str, object]:
    """Ensure the standard Media Pool folders exist and return them by role."""
    media_pool = project.GetMediaPool()
    if media_pool is None:
        raise RuntimeError("Could not get Resolve MediaPool.")
    root_folder = media_pool.GetRootFolder()
    if root_folder is None:
        raise RuntimeError("Could not get Resolve Media Pool root folder.")

    folders: dict[str, object] = {}
    for role, folder_name in MEDIA_POOL_FOLDERS.items():
        folder = find_subfolder(root_folder, folder_name)
        if folder is None:
            folder = media_pool.AddSubFolder(root_folder, folder_name)
        if folder is None:
            raise RuntimeError(f"Could not create Media Pool folder: {folder_name}")
        folders[role] = folder
    return folders


def find_subfolder(parent_folder: object, folder_name: str):
    """Find a direct Media Pool subfolder by exact name."""
    for folder in normalize_folder_list(parent_folder.GetSubFolderList()):
        ok, name = safe_call("Folder.GetName", getattr(folder, "GetName", None))
        if ok and name == folder_name:
            return folder
    return None


def ensure_media_pool_subfolder(media_pool: object, parent_folder: object, folder_name: str):
    """Ensure one direct Media Pool subfolder exists under a parent folder."""
    folder = find_subfolder(parent_folder, folder_name)
    if folder is None:
        folder = media_pool.AddSubFolder(parent_folder, folder_name)
    if folder is None:
        raise RuntimeError(f"Could not create Media Pool subfolder: {folder_name}")
    return folder


def normalize_folder_list(raw_value: object) -> list[object]:
    """Normalize Resolve folder list return shapes."""
    if raw_value is None:
        return []
    if isinstance(raw_value, dict):
        return list(raw_value.values())
    if isinstance(raw_value, (list, tuple)):
        return list(raw_value)
    return []


def import_project_assets(
    project: object,
    media_paths: Iterable[Path],
    xml_path: Path,
    offline_reference_paths: Iterable[Path] | None = None,
    look_reference_paths: Iterable[Path] | None = None,
    source_clips_path: Path | None = None,
    project_root: Path | None = None,
    ref_media_paths: Iterable[Path] | None = None,
    xml_frame_rate: int | float | str | None = None,
    media_folder_name: str | None = None,
) -> ResolveImportResult:
    """Import media, references, and one XML timeline into Resolve."""
    project_name = project.GetName()
    media_pool = project.GetMediaPool()
    if media_pool is None:
        raise RuntimeError("Could not get Resolve MediaPool.")

    folders = ensure_media_pool_folders(project)
    result = ResolveImportResult(
        project_name=project_name,
        folders={role: folder.GetName() for role, folder in folders.items()},
    )
    footage_import_folder = folders["footage"]
    if media_folder_name:
        footage_import_folder = ensure_media_pool_subfolder(media_pool, folders["footage"], media_folder_name)
        result.folders["footage_xml"] = f'{folders["footage"].GetName()}/{footage_import_folder.GetName()}'

    if xml_frame_rate is not None:
        _set_project_timeline_frame_rate(project, xml_frame_rate, result.issues)

    result.imported_media = import_media_paths(media_pool, footage_import_folder, media_paths, result.issues)
    ref_paths = list(ref_media_paths or [])
    if not ref_paths and project_root is not None:
        ref_paths = find_project_ref_media(project_root)
    result.imported_ref_media = import_media_paths(media_pool, folders["ref"], ref_paths, result.issues)
    result.imported_offline_references = import_media_paths(
        media_pool,
        folders["tc"],
        offline_reference_paths or [],
        result.issues,
    )
    result.imported_look_references = import_media_paths(
        media_pool,
        folders["look"],
        look_reference_paths or [],
        result.issues,
    )

    result.xml_import_attempts = import_xml_timeline_with_attempts(
        project=project,
        media_pool=media_pool,
        edit_folder=folders["edit"],
        footage_folder=footage_import_folder,
        xml_path=xml_path,
        source_clips_path=source_clips_path,
    )
    for attempt in result.xml_import_attempts:
        if attempt.success and attempt.current_timeline_name:
            result.timeline_name = attempt.current_timeline_name
            break
    if result.timeline_name is None:
        result.issues.append(
            Issue(
                code="resolve_xml_import_failed",
                severity="ERROR",
                message="Resolve did not create a current timeline from the XML.",
                context={"xml_path": str(xml_path)},
            )
        )
    return result


def import_media_paths(
    media_pool: object,
    target_folder: object,
    paths: Iterable[Path],
    issues: list[Issue],
) -> list[str]:
    """Import paths into a target Media Pool folder and return imported item names."""
    path_list = [Path(path) for path in paths]
    if not path_list:
        return []

    ok, switched = safe_call("MediaPool.SetCurrentFolder", media_pool.SetCurrentFolder, target_folder)
    if not ok or not switched:
        issues.append(
            Issue(
                code="resolve_set_current_folder_failed",
                severity="ERROR",
                message="Could not switch Resolve Media Pool folder before import.",
                context={"folder": _safe_folder_name(target_folder), "detail": switched},
            )
        )
        return []

    ok, imported = safe_call("MediaPool.ImportMedia", media_pool.ImportMedia, [str(path) for path in path_list])
    if not ok:
        issues.append(
            Issue(
                code="resolve_media_import_failed",
                severity="ERROR",
                message="Resolve media import call failed.",
                context={"detail": imported, "paths": [str(path) for path in path_list]},
            )
        )
        return []

    imported_items = normalize_import_result(imported)
    if len(imported_items) != len(path_list):
        issues.append(
            Issue(
                code="resolve_media_import_count_mismatch",
                severity="WARNING",
                message="Resolve imported item count differs from requested media path count.",
                context={"requested": len(path_list), "imported": len(imported_items)},
            )
        )
    return [_safe_item_name(item) for item in imported_items]


def import_xml_timeline_with_attempts(
    project: object,
    media_pool: object,
    edit_folder: object,
    footage_folder: object,
    xml_path: Path,
    source_clips_path: Path | None = None,
) -> list[ResolveImportAttempt]:
    """Import XML with several Resolve option sets and record each attempt."""
    attempts: list[ResolveImportAttempt] = []
    safe_call("MediaPool.SetCurrentFolder", media_pool.SetCurrentFolder, edit_folder)

    option_sets: list[dict[str, Any]] = [
        {"importSourceClips": False, "sourceClipsFolders": [footage_folder]},
    ]
    if source_clips_path is not None:
        option_sets.append({"importSourceClips": True, "sourceClipsPath": str(source_clips_path)})
    option_sets.append({})

    for index, options in enumerate(option_sets, start=1):
        ok, imported = _import_timeline(media_pool, xml_path, options)
        timeline = project.GetCurrentTimeline()
        timeline_name = timeline.GetName() if timeline else None
        attempt = ResolveImportAttempt(
            attempt=index,
            options=summarize_import_options(options),
            success=bool(ok and imported and timeline_name),
            result_type=type(imported).__name__,
            result_repr=_short_repr(imported),
            current_timeline_name=timeline_name,
            error=None if ok else str(imported),
        )
        attempts.append(attempt)
        if attempt.success:
            break
    return attempts


def _import_timeline(media_pool: object, xml_path: Path, options: dict[str, Any]) -> tuple[bool, Any]:
    if options:
        return safe_call(
            "MediaPool.ImportTimelineFromFile",
            media_pool.ImportTimelineFromFile,
            str(xml_path),
            options,
        )
    return safe_call("MediaPool.ImportTimelineFromFile", media_pool.ImportTimelineFromFile, str(xml_path))


def summarize_import_options(options: dict[str, Any]) -> dict[str, Any]:
    """Make Resolve import options reportable without remote objects."""
    summary: dict[str, Any] = {}
    for key, value in options.items():
        if key == "sourceClipsFolders":
            summary[key] = [_safe_folder_name(folder) for folder in value]
        else:
            summary[key] = value
    return summary


def normalize_import_result(raw_value: object) -> list[object]:
    """Normalize Resolve ImportMedia return shapes."""
    if raw_value is None or raw_value is False:
        return []
    if isinstance(raw_value, dict):
        return list(raw_value.values())
    if isinstance(raw_value, (list, tuple)):
        return list(raw_value)
    return [raw_value]


def read_current_timeline_items(project: object) -> TimelineReadbackResult:
    """Read all video timeline items from the current Resolve timeline."""
    ok, timeline = safe_call("Project.GetCurrentTimeline", getattr(project, "GetCurrentTimeline", None))
    if not ok or timeline is None:
        raise RuntimeError("No current Resolve timeline is available for readback.")
    return read_timeline_items(timeline)


def read_timeline_items(timeline: object) -> TimelineReadbackResult:
    """Read video tracks and item fields from a Resolve timeline."""
    timeline_name = _safe_timeline_name(timeline)
    result = TimelineReadbackResult(timeline_name=timeline_name)
    ok, video_track_count = safe_call("Timeline.GetTrackCount(video)", timeline.GetTrackCount, "video")
    if not ok:
        result.issues.append(
            Issue(
                code="timeline_track_count_failed",
                severity="ERROR",
                message="Could not read Resolve video track count.",
                context={"detail": video_track_count},
            )
        )
        return result

    track_count = _safe_int(video_track_count) or 0
    result.track_counts["video"] = track_count
    for track_index in range(1, track_count + 1):
        ok, raw_items = safe_call(
            f"Timeline.GetItemListInTrack(video,{track_index})",
            timeline.GetItemListInTrack,
            "video",
            track_index,
        )
        items = normalize_item_list(raw_items) if ok else []
        result.track_counts[f"video_{track_index}"] = len(items)
        if not ok:
            result.issues.append(
                Issue(
                    code="timeline_track_items_failed",
                    severity="ERROR",
                    message="Could not read Resolve timeline items for a video track.",
                    context={"track_type": "video", "track_index": track_index, "detail": raw_items},
                )
            )
            continue
        for item_index, item in enumerate(items, start=1):
            record = read_timeline_item(item, "video", track_index, item_index)
            result.video_items.append(record)
            result.issues.extend(record.issues)
    return result


def find_project_ref_media(project_root: Path) -> list[Path]:
    """Return media files under a project-level ref folder when it exists.

    Some validation runs pass the project root, while older ad-hoc runs pass
    the footage folder directly. Check both shapes so a sibling project `ref`
    folder is still imported.
    """
    root = Path(project_root)
    ref_dirs = []
    for candidate in (root / "ref", root.parent / "ref"):
        if candidate.is_dir() and candidate not in ref_dirs:
            ref_dirs.append(candidate)
    if not ref_dirs:
        return []
    return sorted(
        (
            path
            for ref_dir in ref_dirs
            for path in ref_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMPORTABLE_REF_EXTENSIONS
        ),
        key=lambda path: str(path).casefold(),
    )


def read_timeline_item(
    item: object,
    track_type: str,
    track_index: int,
    item_index: int,
) -> TimelineItemRecord:
    """Read one Resolve timeline item with best-effort field safety."""
    issues: list[Issue] = []
    name = _safe_item_field(item, "GetName", issues, track_type, track_index, item_index)
    media_pool_item = _safe_media_pool_item(item, issues, track_type, track_index, item_index)
    properties = _safe_clip_properties(item, issues, track_type, track_index, item_index)
    media_properties = _safe_media_pool_properties(
        media_pool_item,
        issues,
        track_type,
        track_index,
        item_index,
    )
    media_pool_name = _safe_media_pool_item_name(media_pool_item)
    media_file_path = _first_property(media_properties, ("File Path", "FilePath", "Filename", "File Name"))

    return TimelineItemRecord(
        track_type=track_type,
        track_index=track_index,
        item_index=item_index,
        name=str(name) if name is not None else "",
        start=_safe_item_int_field(item, "GetStart", issues, track_type, track_index, item_index),
        end=_safe_item_int_field(item, "GetEnd", issues, track_type, track_index, item_index),
        duration=_safe_item_int_field(item, "GetDuration", issues, track_type, track_index, item_index),
        source_start=_safe_item_int_field(item, "GetSourceStartFrame", issues, track_type, track_index, item_index),
        source_end=_safe_item_int_field(item, "GetSourceEndFrame", issues, track_type, track_index, item_index),
        left_offset=_safe_item_int_field(item, "GetLeftOffset", issues, track_type, track_index, item_index),
        right_offset=_safe_item_int_field(item, "GetRightOffset", issues, track_type, track_index, item_index),
        media_pool_name=media_pool_name,
        media_file_path=str(media_file_path) if media_file_path else None,
        is_offline=media_pool_item is None,
        properties=properties,
        issues=issues,
    )


def normalize_item_list(raw_value: object) -> list[object]:
    """Normalize Resolve timeline item list return shapes."""
    if raw_value is None:
        return []
    if isinstance(raw_value, dict):
        return list(raw_value.values())
    if isinstance(raw_value, (list, tuple)):
        return list(raw_value)
    return []


def _safe_item_name(item: object) -> str:
    ok, name = safe_call("MediaPoolItem.GetName", getattr(item, "GetName", None))
    return str(name) if ok and name else type(item).__name__


def _safe_folder_name(folder: object) -> str:
    ok, name = safe_call("Folder.GetName", getattr(folder, "GetName", None))
    return str(name) if ok and name else type(folder).__name__


def _set_project_timeline_frame_rate(
    project: object,
    frame_rate: int | float | str,
    issues: list[Issue],
) -> None:
    """Set Resolve project timeline frame rate before XML import."""
    frame_rate_text = str(frame_rate)
    method = getattr(project, "SetSetting", None)
    if not callable(method):
        issues.append(
            Issue(
                code="resolve_timeline_framerate_unavailable",
                severity="WARNING",
                message="Resolve Project.SetSetting is not available; timeline frame rate was not set before XML import.",
                context={"frame_rate": frame_rate_text},
            )
        )
        return
    attempted: dict[str, object] = {}
    success = False
    for key in ("timelineFrameRate", "timelinePlaybackFrameRate"):
        ok, value = safe_call(f"Project.SetSetting({key})", method, key, frame_rate_text)
        attempted[key] = value
        success = success or bool(ok and value)
    if not success:
        issues.append(
            Issue(
                code="resolve_timeline_framerate_failed",
                severity="WARNING",
                message="Resolve did not confirm timeline frame-rate settings before XML import.",
                context={"frame_rate": frame_rate_text, "attempts": attempted},
            )
        )


def _short_repr(value: object, limit: int = 240) -> str:
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit]}..."


def _safe_timeline_name(timeline: object) -> str:
    ok, name = safe_call("Timeline.GetName", getattr(timeline, "GetName", None))
    return str(name) if ok and name else type(timeline).__name__


def _safe_media_pool_item(
    item: object,
    issues: list[Issue],
    track_type: str,
    track_index: int,
    item_index: int,
) -> object | None:
    ok, media_pool_item = safe_call("TimelineItem.GetMediaPoolItem", getattr(item, "GetMediaPoolItem", None))
    if ok:
        return media_pool_item
    issues.append(_timeline_item_issue("timeline_item_media_pool_item_failed", media_pool_item, track_type, track_index, item_index))
    return None


def _safe_clip_properties(
    item: object,
    issues: list[Issue],
    track_type: str,
    track_index: int,
    item_index: int,
) -> dict[str, Any]:
    ok, properties = safe_call("TimelineItem.GetProperty", getattr(item, "GetProperty", None))
    if ok and isinstance(properties, dict):
        return {str(key): value for key, value in properties.items()}
    if not ok:
        issues.append(_timeline_item_issue("timeline_item_properties_failed", properties, track_type, track_index, item_index))
    return {}


def _safe_media_pool_properties(
    media_pool_item: object | None,
    issues: list[Issue],
    track_type: str,
    track_index: int,
    item_index: int,
) -> dict[str, Any]:
    if media_pool_item is None:
        return {}
    ok, properties = safe_call("MediaPoolItem.GetClipProperty", getattr(media_pool_item, "GetClipProperty", None))
    if ok and isinstance(properties, dict):
        return {str(key): value for key, value in properties.items()}
    if not ok:
        issues.append(_timeline_item_issue("timeline_item_media_properties_failed", properties, track_type, track_index, item_index))
    return {}


def _safe_media_pool_item_name(media_pool_item: object | None) -> str | None:
    if media_pool_item is None:
        return None
    ok, name = safe_call("MediaPoolItem.GetName", getattr(media_pool_item, "GetName", None))
    return str(name) if ok and name else None


def _safe_item_field(
    item: object,
    method_name: str,
    issues: list[Issue],
    track_type: str,
    track_index: int,
    item_index: int,
) -> object | None:
    method = getattr(item, method_name, None)
    ok, value = safe_call(f"TimelineItem.{method_name}", method)
    if ok:
        return value
    issues.append(_timeline_item_issue(f"timeline_item_{method_name.lower()}_failed", value, track_type, track_index, item_index))
    return None


def _safe_item_int_field(
    item: object,
    method_name: str,
    issues: list[Issue],
    track_type: str,
    track_index: int,
    item_index: int,
) -> int | None:
    value = _safe_item_field(item, method_name, issues, track_type, track_index, item_index)
    return _safe_int(value)


def _safe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_property(properties: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = properties.get(name)
        if value not in (None, ""):
            return value
    return None


def _timeline_item_issue(
    code: str,
    detail: object,
    track_type: str,
    track_index: int,
    item_index: int,
) -> Issue:
    return Issue(
        code=code,
        severity="WARNING",
        message="Could not read one Resolve timeline item field.",
        context={
            "track_type": track_type,
            "track_index": track_index,
            "item_index": item_index,
            "detail": detail,
        },
    )
