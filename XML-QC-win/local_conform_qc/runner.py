"""End-to-end local conform QC pipeline."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
import shutil

from .media_scanner import (
    get_import_media_paths,
    match_xml_clips_to_media,
    scan_project_media_with_stats,
)
from .models import ReportData, ToolConfig
from .qc_engine import (
    build_import_difference_sections,
    calculate_match_success_percentage,
    collect_problem_issues,
    compare_timeline,
)
from .report_writer import write_reports
from .resolve_api import (
    connect_resolve,
    find_project_ref_media,
    import_project_assets,
    open_or_create_project,
    read_current_timeline_items,
)
from .xml_parser import parse_xml


DEFAULT_RESOLVE_PROJECT_NAME = "LocalConform_QC_Test"


def run_config(config: ToolConfig, workspace_dir: Path) -> list[tuple[Path, Path]]:
    """Run QC for each selected XML path and return report paths."""
    _validate_config(config)
    project_root = Path(config.project_root or ".")
    report_dir = project_root / "QC"
    cache_dir = Path(workspace_dir) / "cache" / "phase8_import_xml"
    cache_dir.mkdir(parents=True, exist_ok=True)

    resolve = connect_resolve()
    project = open_or_create_project(resolve, config.project_name or DEFAULT_RESOLVE_PROJECT_NAME)

    reports: list[tuple[Path, Path]] = []
    for xml_path in _xml_paths(config):
        reports.append(_run_one_xml(config, project, Path(xml_path), report_dir, cache_dir))
    return reports


def _validate_config(config: ToolConfig) -> None:
    if config.project_root is None:
        raise ValueError("Project root is required.")


def _run_one_xml(
    config: ToolConfig,
    project: object,
    xml_path: Path,
    report_dir: Path,
    cache_dir: Path,
) -> tuple[Path, Path]:
    project_root = Path(config.project_root or ".")
    media_root = _media_root(config)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"{_safe_report_name(xml_path.stem)}_{timestamp}"
    import_xml_path = cache_dir / f"{report_name}.xml"
    shutil.copyfile(xml_path, import_xml_path)

    scan_result = scan_project_media_with_stats(media_root, reference_paths=config.look_references)
    media_files = scan_result.media_files
    xml_result = parse_xml(xml_path)
    matches = match_xml_clips_to_media(xml_result.clips, media_files)
    import_paths = get_import_media_paths(matches, media_files=media_files, import_all_media=config.import_all_media)
    frame_rate_rows = scan_result.frame_rate_rows
    ref_media_paths = find_project_ref_media(project_root)

    import_result = import_project_assets(
        project=project,
        media_paths=import_paths,
        xml_path=import_xml_path,
        offline_reference_paths=[],
        look_reference_paths=config.look_references,
        project_root=project_root,
        ref_media_paths=ref_media_paths,
        xml_frame_rate=xml_result.sequence_timebase,
        media_folder_name=xml_path.stem,
    )
    timeline_result = read_current_timeline_items(project)
    qc_result = compare_timeline(xml_result, timeline_result)
    sections = build_import_difference_sections(xml_result, matches, import_result, timeline_result, qc_result)
    sections["\u7d20\u6750\u5e27\u7387\u7edf\u8ba1"] = frame_rate_rows
    problem_issues = collect_problem_issues(matches, import_result, timeline_result, qc_result)
    match_counts = Counter(match.status for match in matches)

    report = ReportData(
        status=qc_result.status,
        summary={
            "report_name": report_name,
            "\u6d4b\u8bd5XML": str(xml_path),
            "\u5bfc\u5165XML\u4e34\u65f6\u526f\u672c": str(import_xml_path),
            "\u9879\u76ee\u6839\u76ee\u5f55": str(project_root),
            "\u955c\u5934\u7d20\u6750\u76ee\u5f55": str(media_root),
            "Resolve\u9879\u76ee": project.GetName(),
            "Resolve\u65f6\u95f4\u7ebf": import_result.timeline_name or timeline_result.timeline_name,
            "XML\u5e27\u7387": xml_result.sequence_timebase,
            "\u5339\u914d\u6210\u529f\u767e\u5206\u6bd4": f"{calculate_match_success_percentage(xml_result, matches, qc_result):.2f}%",
            "XML\u7247\u6bb5\u603b\u6570": len(xml_result.clips),
            "\u626b\u63cf\u524d\u5a92\u4f53\u6587\u4ef6\u603b\u6570": scan_result.total_candidates,
            "\u4ee3\u7406\u7d20\u6750\u6392\u9664\u6570": scan_result.proxy_excluded,
            "\u626b\u63cf\u7d20\u6750\u6587\u4ef6\u603b\u6570": len(media_files),
            "\u5339\u914d\u7edf\u8ba1": dict(match_counts),
            "\u8bf7\u6c42\u5bfc\u5165\u7d20\u6750\u6570": len(import_paths),
            "Resolve\u5b9e\u9645\u5bfc\u5165\u7d20\u6750\u6570": len(import_result.imported_media),
            "Resolve\u5bfc\u5165ref\u6570": len(import_result.imported_ref_media),
            "Resolve\u65f6\u95f4\u7ebf\u7247\u6bb5\u6570": len(timeline_result.video_items),
            "Resolve\u79bb\u7ebf\u7247\u6bb5\u6570": sum(1 for item in timeline_result.video_items if item.is_offline),
            "QC\u72b6\u6001": qc_result.status,
            "\u95ee\u9898\u6570\u91cf": len(problem_issues),
        },
        issues=problem_issues,
        sections=sections,
    )
    return write_reports(report, report_dir)


def _xml_paths(config: ToolConfig) -> list[Path]:
    if config.xml_paths:
        xml_paths = [Path(path).expanduser() for path in config.xml_paths]
        missing = [path for path in xml_paths if not path.is_file()]
        if missing:
            raise ValueError("Selected XML file was not found: " + "; ".join(str(path) for path in missing))
        return xml_paths
    project_root = Path(config.project_root or ".")
    edit_dir = project_root / "edit"
    if not edit_dir.is_dir():
        raise ValueError(f"XML paths were not selected and edit folder was not found: {edit_dir}")
    xml_paths = sorted(edit_dir.rglob("*.xml"), key=lambda path: str(path).casefold())
    if not xml_paths:
        raise ValueError(f"No XML files were found under edit folder: {edit_dir}")
    return xml_paths


def _media_root(config: ToolConfig) -> Path:
    if config.media_root is not None:
        return Path(config.media_root)
    project_root = Path(config.project_root or ".")
    footage_dir = project_root / "footage"
    if not footage_dir.is_dir():
        raise ValueError(f"Shot media path was not selected and footage folder was not found: {footage_dir}")
    return footage_dir


def _safe_report_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value).strip("_")
    return safe or "local_conform_qc"
