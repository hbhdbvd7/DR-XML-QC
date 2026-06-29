"""Project media scanning and XML clip matching."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable

from .models import Issue, MediaFile, MediaMatch, XmlClip


MEDIA_EXTENSIONS = {
    ".3gp", ".aac", ".aif", ".aiff", ".ari", ".braw", ".cin", ".dng", ".dpx", ".exr",
    ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".mxf", ".r3d", ".tif", ".tiff", ".wav",
}
EXCLUDED_DIR_NAMES = {"reports", "logs", "cache", "ref", "__pycache__", ".git", ".idea", ".venv"}
PROXY_CODEC_EXTENSIONS = {".m4v", ".mov", ".mp4", ".mxf"}
FRAME_RATE_PROBE_EXTENSIONS = {".3gp", ".ari", ".braw", ".cin", ".m4v", ".mkv", ".mov", ".mp4", ".mxf", ".r3d"}
FFPROBE_CANDIDATES = (
    "ffprobe",
    "/opt/homebrew/bin/ffprobe",
    "/usr/local/bin/ffprobe",
    "/usr/bin/ffprobe",
)


@dataclass(slots=True)
class MediaScanResult:
    media_files: list[MediaFile]
    total_candidates: int
    proxy_excluded: int
    frame_rate_rows: list[dict[str, object]]


def scan_project_media(project_root: Path, reference_paths: Iterable[Path] | None = None) -> list[MediaFile]:
    return scan_project_media_with_stats(project_root, reference_paths).media_files


def scan_project_media_with_stats(project_root: Path, reference_paths: Iterable[Path] | None = None) -> MediaScanResult:
    root = Path(project_root).expanduser()
    references = {_normalize_path(path) for path in reference_paths or []}
    media_files: list[MediaFile] = []
    frame_rate_counts: dict[str, int] = defaultdict(int)
    total_candidates = 0
    proxy_excluded = 0

    for path in root.rglob("*"):
        if _is_under_excluded_dir(path, root) or not path.is_file() or path.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        normalized = _normalize_path(path)
        if normalized in references:
            continue

        total_candidates += 1
        if "proxy" in path.name.casefold():
            proxy_excluded += 1
            continue

        probe = _probe_media_info(path)
        if _is_proxy_media_from_probe(path, probe):
            proxy_excluded += 1
            continue

        if _should_count_frame_rate(probe["frame_rate"]):
            frame_rate_counts[probe["frame_rate"]] += 1
        media_files.append(MediaFile(path=path, name_key=_normalize_name(path.name), stem_key=_normalize_name(path.stem)))

    return MediaScanResult(
        media_files=sorted(media_files, key=lambda item: str(item.path).casefold()),
        total_candidates=total_candidates,
        proxy_excluded=proxy_excluded,
        frame_rate_rows=_frame_rate_rows(frame_rate_counts),
    )


def build_media_index(media_files: Iterable[MediaFile]) -> dict[str, dict[str, list[MediaFile]]]:
    by_name: dict[str, list[MediaFile]] = defaultdict(list)
    for media_file in media_files:
        by_name[media_file.name_key].append(media_file)
    return {"name": dict(by_name)}


def match_xml_clips_to_media(clips: Iterable[XmlClip], media_files: Iterable[MediaFile]) -> list[MediaMatch]:
    index = build_media_index(media_files)
    return [_match_clip(clip, index) for clip in clips]


def get_import_media_paths(
    matches: Iterable[MediaMatch],
    media_files: Iterable[MediaFile] | None = None,
    import_all_media: bool = False,
) -> list[Path]:
    if import_all_media:
        return _unique_paths(media_file.path for media_file in media_files or [])
    return _unique_paths(match.selected_path for match in matches if match.selected_path is not None)


def _is_proxy_media_from_probe(path: Path, probe: dict[str, str]) -> bool:
    if "proxy" in path.name.casefold():
        return True
    return probe["is_prores_proxy"] == "1"


def _match_clip(clip: XmlClip, index: dict[str, dict[str, list[MediaFile]]]) -> MediaMatch:
    clip_name_key = _clip_file_name_key(clip)
    if clip_name_key:
        name_candidates = index["name"].get(clip_name_key, [])
        if name_candidates:
            return _candidate_match(clip, "matched_by_file_name", name_candidates)

    return MediaMatch(
        clip=clip,
        status="missing",
        issues=[
            Issue(
                code="media_missing",
                severity="ERROR",
                message="No local media file name matched the XML clip; it will be left offline.",
                context={"clip_index": clip.index, "clip_name": clip.name, "source_path": clip.decoded_path},
            )
        ],
    )


def _candidate_match(clip: XmlClip, status: str, candidates: list[MediaFile]) -> MediaMatch:
    candidate_paths = [candidate.path for candidate in candidates]
    if len(candidates) == 1:
        return MediaMatch(clip=clip, status=status, candidates=candidate_paths, selected_path=candidate_paths[0])
    return MediaMatch(
        clip=clip,
        status="multiple_candidates",
        candidates=candidate_paths,
        issues=[
            Issue(
                code="media_multiple_candidates",
                severity="WARNING",
                message="Multiple local media candidates matched the XML clip.",
                context={
                    "clip_index": clip.index,
                    "clip_name": clip.name,
                    "match_basis": status,
                    "candidate_count": len(candidates),
                },
            )
        ],
    )


def _is_under_excluded_dir(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        relative_parts = path.parts
    return any(part.casefold() in EXCLUDED_DIR_NAMES for part in relative_parts[:-1])


def _normalize_path(path: Path) -> str:
    try:
        return str(path.expanduser().resolve()).casefold()
    except OSError:
        return str(path.expanduser()).casefold()


def _clip_file_name_key(clip: XmlClip) -> str:
    if clip.decoded_path:
        decoded_text = clip.decoded_path.replace("\\", "/")
        file_name = Path(decoded_text).name
        if file_name:
            return _normalize_name(file_name)
    if clip.name:
        return _normalize_name(clip.name)
    return ""


def _normalize_name(value: str) -> str:
    return value.strip().casefold()


def _unique_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = _normalize_path(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


@lru_cache(maxsize=8192)
def _probe_media_info(path: Path) -> dict[str, str]:
    media_path = Path(path)
    if media_path.suffix.lower() not in FRAME_RATE_PROBE_EXTENSIONS | PROXY_CODEC_EXTENSIONS:
        return {"frame_rate": "未知", "is_prores_proxy": "0"}
    ffprobe_bin = _resolve_ffprobe_bin()
    if ffprobe_bin is None:
        return {"frame_rate": "未知", "is_prores_proxy": "0"}
    try:
        completed = _run_probe([
            ffprobe_bin, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate,r_frame_rate,codec_name,codec_long_name,codec_tag_string,profile",
            "-of", "json", str(media_path),
        ])
    except (OSError, subprocess.SubprocessError):
        return {"frame_rate": "未知", "is_prores_proxy": "0"}
    if completed.returncode != 0:
        return {"frame_rate": "未知", "is_prores_proxy": "0"}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"frame_rate": "未知", "is_prores_proxy": "0"}
    streams = payload.get("streams") or []
    if not streams:
        return {"frame_rate": "未知", "is_prores_proxy": "0"}
    stream = streams[0]
    frame_rate = _format_frame_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    codec_name = str(stream.get("codec_name") or "").casefold()
    codec_text = " ".join(str(stream.get(key) or "") for key in ("profile", "codec_long_name", "codec_tag_string")).casefold()
    is_prores_proxy = codec_name == "prores" and ("proxy" in codec_text or "apco" in codec_text)
    return {"frame_rate": frame_rate, "is_prores_proxy": "1" if is_prores_proxy else "0"}


def _frame_rate_rows(counts: dict[str, int]) -> list[dict[str, object]]:
    return [{"帧率": frame_rate, "数量": count} for frame_rate, count in sorted(counts.items(), key=lambda item: _frame_rate_sort_key(item[0]))]


def _should_count_frame_rate(value: str) -> bool:
    normalized = str(value or "").strip()
    return bool(normalized) and normalized != "未知"


def _run_probe(args: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, object] = {
        "args": args,
        "check": False,
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "timeout": 20,
    }
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.run(**kwargs)


@lru_cache(maxsize=1)
def _resolve_ffprobe_bin() -> str | None:
    env_raw = os.environ.get("FFPROBE_BIN", "").strip()
    env_value = str(Path(env_raw).expanduser()) if env_raw else ""
    if env_value and Path(env_value).is_file():
        return env_value
    for candidate in FFPROBE_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file():
            return str(candidate_path)
    return None


def _format_frame_rate(value: object) -> str:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return "未知"
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return text
    number = float(rate)
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _frame_rate_sort_key(value: str) -> tuple[int, float | str]:
    if value == "未知":
        return (1, 0.0)
    try:
        return (0, float(value))
    except ValueError:
        return (2, value)
