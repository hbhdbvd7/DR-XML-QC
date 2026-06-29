"""XML parsing and precheck utilities."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlparse
import re
import xml.etree.ElementTree as ET

from .models import Issue, XmlClip, XmlPrecheckResult


OLD_PATH_MARKERS = ("old", "offline", "missing", "temp", "bak", "backup")
SPECIAL_PATH_CHARS = set("#?&[]{}'\"")


def parse_xml(path: Path) -> XmlPrecheckResult:
    xml_path = Path(path)
    tree = ET.parse(xml_path)
    root = tree.getroot()
    issues: list[Issue] = []
    if root.tag != "xmeml":
        issues.append(Issue(code="xml_not_xmeml", severity="ERROR", message="XML root is not xmeml.", context={"root_tag": root.tag, "xml_path": str(xml_path)}))
    sequence = root.find("sequence")
    sequence_name = _text(sequence, "name") if sequence is not None else ""
    sequence_timebase = _int_text(sequence, "rate/timebase") if sequence is not None else None
    if not sequence_name:
        issues.append(Issue(code="xml_missing_sequence_name", severity="WARNING", message="Sequence name is empty or missing.", context={"xml_path": str(xml_path)}))
    clips = _extract_clips(root, issues)
    if not clips:
        issues.append(Issue(code="xml_no_clipitems", severity="ERROR", message="No xmeml clipitem entries were found.", context={"xml_path": str(xml_path)}))
    issues.extend(_detect_global_issues(root, xml_path))
    return XmlPrecheckResult(xml_path=xml_path, sequence_name=sequence_name, sequence_timebase=sequence_timebase, clips=clips, issues=issues)


def _extract_clips(root: ET.Element, issues: list[Issue]) -> list[XmlClip]:
    clips: list[XmlClip] = []
    for track_index, track in enumerate(root.findall(".//media/video/track"), start=1):
        for clip_el in track.findall("clipitem"):
            clip_index = len(clips) + 1
            file_el = clip_el.find("file")
            pathurl = _text(file_el, "pathurl") if file_el is not None else ""
            decoded_path = decode_pathurl(pathurl)
            clip = XmlClip(
                index=clip_index,
                clip_id=clip_el.get("id", ""),
                name=_text(clip_el, "name"),
                start=_int_text(clip_el, "start"),
                end=_int_text(clip_el, "end"),
                duration=_int_text(clip_el, "duration"),
                source_in=_int_text(clip_el, "in"),
                source_out=_int_text(clip_el, "out"),
                pathurl=pathurl,
                decoded_path=decoded_path,
                timebase=_int_text(clip_el, "rate/timebase"),
                file_timebase=_int_text(file_el, "rate/timebase") if file_el is not None else None,
                track_index=track_index,
            )
            clips.append(clip)
            issues.extend(_detect_clip_issues(clip, clip_el))
    return clips


def decode_pathurl(pathurl: str) -> str:
    """Decode an xmeml file path URL to a filesystem-like path string."""
    if not pathurl:
        return ""
    decoded = unquote(pathurl)
    parsed = urlparse(decoded)
    if parsed.scheme != "file":
        return decoded

    path = parsed.path or ""
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if parsed.fragment:
        path = f"{path}#{parsed.fragment}"
    if re.match(r"^/[A-Za-z]:/", path):
        return str(PureWindowsPath(path[1:]))
    return path


def _detect_clip_issues(clip: XmlClip, clip_el: ET.Element) -> list[Issue]:
    issues: list[Issue] = []
    context = {"clip_index": clip.index, "clip_name": clip.name, "clip_id": clip.clip_id}
    if not clip.pathurl.strip():
        issues.append(Issue(code="xml_empty_path", severity="ERROR", message="Clip has an empty file/pathurl.", context=context))
    decoded_lower = clip.decoded_path.lower()
    if any(marker in decoded_lower for marker in OLD_PATH_MARKERS):
        issues.append(Issue(code="xml_old_path_marker", severity="WARNING", message="Clip path contains a marker that often indicates an old or temporary path.", context={**context, "decoded_path": clip.decoded_path}))
    if _looks_like_mac_path(clip.pathurl, clip.decoded_path):
        issues.append(Issue(code="xml_mac_path", severity="WARNING", message="Clip path appears to be a Mac-style path.", context={**context, "decoded_path": clip.decoded_path}))
    if _has_cjk(clip.decoded_path):
        issues.append(Issue(code="xml_chinese_path", severity="WARNING", message="Clip path contains Chinese characters.", context={**context, "decoded_path": clip.decoded_path}))
    special_chars = sorted({char for char in f"{clip.pathurl}{clip.decoded_path}" if char in SPECIAL_PATH_CHARS})
    if special_chars:
        issues.append(Issue(code="xml_special_chars_path", severity="WARNING", message="Clip path contains special characters that may affect relinking.", context={**context, "decoded_path": clip.decoded_path, "characters": special_chars}))
    if _has_speed_effect(clip_el):
        issues.append(Issue(code="xml_speed_effect", severity="WARNING", message="Clip has speed-related XML metadata.", context=context))
    if clip_el.find(".//sequence") is not None:
        issues.append(Issue(code="xml_nested_sequence", severity="WARNING", message="Clip contains a nested sequence.", context=context))
    return issues


def _detect_global_issues(root: ET.Element, xml_path: Path) -> list[Issue]:
    issues: list[Issue] = []
    transition_count = len(root.findall(".//transitionitem"))
    if transition_count:
        issues.append(Issue(code="xml_transition", severity="WARNING", message="XML contains transition items.", context={"xml_path": str(xml_path), "count": transition_count}))
    nested_sequences = max(0, len(root.findall(".//sequence")) - 1)
    if nested_sequences:
        issues.append(Issue(code="xml_nested_sequence", severity="WARNING", message="XML contains nested sequence entries.", context={"xml_path": str(xml_path), "count": nested_sequences}))
    return issues


def _has_speed_effect(element: ET.Element) -> bool:
    for child in element.iter():
        tag = _strip_namespace(child.tag).lower()
        text = (child.text or "").lower()
        if "speed" in tag or "timewarp" in text or "timeremap" in text:
            return True
    return False


def _looks_like_mac_path(pathurl: str, decoded_path: str) -> bool:
    text = f"{pathurl} {decoded_path}"
    return any(marker in text for marker in ("file://localhost/Volumes/", "/Users/", "/Volumes/"))


def _has_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _text(element: ET.Element | None, path: str) -> str:
    if element is None:
        return ""
    found = element.find(path)
    return (found.text or "").strip() if found is not None else ""


def _int_text(element: ET.Element | None, path: str) -> int | None:
    text = _text(element, path)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
