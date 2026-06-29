"""Timeline conform QC utilities."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .models import (
    ClipComparison,
    ConformQcResult,
    Issue,
    MediaMatch,
    ResolveImportResult,
    TimelineItemRecord,
    TimelineReadbackResult,
    XmlClip,
    XmlPrecheckResult,
)


FRAME_FIELDS = ("start", "end", "duration")
SOURCE_FRAME_FIELDS = (
    ("source_in", "source_start"),
    ("source_out", "source_end"),
)
COMPOUND_XML_ISSUE_CODES = {"xml_nested_sequence"}
COMPOUND_NAME_MARKERS = ("compound", "nested", "multicam", "\u590d\u5408", "\u5d4c\u5957")


def compare_timeline(
    xml_result: XmlPrecheckResult | Iterable[XmlClip],
    timeline_result: TimelineReadbackResult,
) -> ConformQcResult:
    """Compare parsed XML clips with Resolve timeline readback data."""
    xml_clips = _xml_clips(xml_result)
    timeline_items = list(timeline_result.video_items)
    issues: list[Issue] = []
    comparisons: list[ClipComparison] = []

    if isinstance(xml_result, XmlPrecheckResult):
        issues.extend(_compound_xml_issues(xml_result.issues))

    xml_by_track = _group_xml_by_track(xml_clips)
    timeline_by_track = _group_timeline_by_track(timeline_items)
    track_indexes = sorted(set(xml_by_track) | set(timeline_by_track))

    if len(xml_clips) != len(timeline_items):
        issues.append(
            Issue(
                code="qc_clip_count_mismatch",
                severity="ERROR",
                message="XML clip count does not match Resolve timeline item count.",
                context={"xml_count": len(xml_clips), "timeline_count": len(timeline_items)},
            )
        )

    for track_index in track_indexes:
        xml_track = xml_by_track.get(track_index, [])
        timeline_track = timeline_by_track.get(track_index, [])
        if len(xml_track) != len(timeline_track):
            issues.append(
                Issue(
                    code="qc_track_count_mismatch",
                    severity="ERROR",
                    message="XML clip count does not match Resolve item count on one video track.",
                    context={
                        "track_index": track_index,
                        "xml_count": len(xml_track),
                        "timeline_count": len(timeline_track),
                    },
                )
            )
        max_count = max(len(xml_track), len(timeline_track))
        for item_offset in range(max_count):
            xml_clip = xml_track[item_offset] if item_offset < len(xml_track) else None
            timeline_item = timeline_track[item_offset] if item_offset < len(timeline_track) else None
            comparison = _compare_pair(track_index, item_offset + 1, xml_clip, timeline_item)
            comparisons.append(comparison)
            issues.extend(comparison.issues)

    status = "pass" if not any(issue.severity == "ERROR" for issue in issues) else "fail"
    return ConformQcResult(
        status=status,
        summary={
            "xml_clip_count": len(xml_clips),
            "timeline_item_count": len(timeline_items),
            "comparison_count": len(comparisons),
            "issue_count": len(issues),
            "error_count": sum(1 for issue in issues if issue.severity == "ERROR"),
            "warning_count": sum(1 for issue in issues if issue.severity == "WARNING"),
            "timeline_name": timeline_result.timeline_name,
        },
        comparisons=comparisons,
        issues=issues,
    )


def build_import_difference_sections(
    xml_result: XmlPrecheckResult,
    matches: Iterable[MediaMatch],
    import_result: ResolveImportResult,
    timeline_result: TimelineReadbackResult,
    qc_result: ConformQcResult,
) -> dict[str, object]:
    """Build report sections that explain concrete import differences."""
    match_list = list(matches)
    missing_media = [
        {
            "问题类型": "素材缺失",
            "问题描述": _missing_media_description(match),
            "XML片段序号": match.clip.index,
            "XML轨道": match.clip.track_index,
            "片段名称": match.clip.name,
            "XML原路径": match.clip.decoded_path or match.clip.pathurl or "空路径",
        }
        for match in match_list
        if match.status == "missing"
    ]
    multiple_candidates = [
        {
            "问题类型": "多个素材候选",
            "问题描述": f"XML 第 {match.clip.index} 个片段 `{match.clip.name}` 匹配到 {len(match.candidates)} 个本地素材候选，需要人工确认。",
            "XML片段序号": match.clip.index,
            "XML轨道": match.clip.track_index,
            "片段名称": match.clip.name,
            "候选数量": len(match.candidates),
            "候选素材": [str(path) for path in match.candidates],
        }
        for match in match_list
        if match.status == "multiple_candidates"
    ]
    comparison_rows = [_comparison_difference_row(comparison) for comparison in qc_result.comparisons if comparison.issues]
    timeline_offline = [
        {
            "问题类型": "时间线离线",
            "问题描述": f"Resolve V{item.track_index} 第 {item.item_index} 个片段 `{item.name}` 没有 Media Pool item，可能处于离线状态。",
            "Resolve轨道": item.track_index,
            "Resolve序号": item.item_index,
            "片段名称": item.name,
            "开始帧": item.start,
            "结束帧": item.end,
            "持续帧数": item.duration,
        }
        for item in timeline_result.video_items
        if item.is_offline
    ]
    track_differences = [_top_level_issue_row(issue) for issue in qc_result.issues if issue.code in {"qc_clip_count_mismatch", "qc_track_count_mismatch"}]
    failed_import_attempts = [
        {
            "问题类型": "XML导入尝试失败",
            "问题描述": f"第 {attempt.attempt} 次 XML 导入未成功。Resolve 返回类型：{attempt.result_type}。",
            "尝试序号": attempt.attempt,
            "导入选项": attempt.options,
            "错误": attempt.error,
            "返回值": attempt.result_repr,
        }
        for attempt in import_result.xml_import_attempts
        if not attempt.success
    ]

    return {
        "导入差异摘要": {
            "XML片段总数": len(xml_result.clips),
            "成功匹配片段数": sum(1 for match in match_list if match.selected_path is not None),
            "缺失素材数": len(missing_media),
            "多候选素材数": len(multiple_candidates),
            "请求导入去重素材数": len({str(match.selected_path).casefold() for match in match_list if match.selected_path is not None}),
            "Resolve实际导入素材数": len(import_result.imported_media),
            "Resolve时间线片段数": len(timeline_result.video_items),
            "时间线差异问题数": len(comparison_rows),
            "离线时间线片段数": len(timeline_offline),
        },
        "缺失素材": missing_media,
        "多个素材候选": multiple_candidates,
        "导入失败尝试": failed_import_attempts,
        "时间线轨道差异": track_differences,
        "时间线离线片段": timeline_offline,
        "问题片段明细": comparison_rows,
    }


def collect_problem_issues(
    matches: Iterable[MediaMatch],
    import_result: ResolveImportResult,
    timeline_result: TimelineReadbackResult,
    qc_result: ConformQcResult,
) -> list[Issue]:
    """Collect only issues that represent import or conform problems."""
    issues: list[Issue] = []
    for match in matches:
        if match.status in {"missing", "multiple_candidates"}:
            issues.extend(_localized_issue(issue) for issue in match.issues)
    issues.extend(_localized_issue(issue) for issue in import_result.issues)
    issues.extend(_localized_issue(issue) for issue in timeline_result.issues)
    issues.extend(_localized_issue(issue) for issue in qc_result.issues)
    return issues


def _compare_pair(
    track_index: int,
    item_index: int,
    xml_clip: XmlClip | None,
    timeline_item: TimelineItemRecord | None,
) -> ClipComparison:
    comparison = ClipComparison(
        track_index=track_index,
        item_index=item_index,
        xml_clip_index=xml_clip.index if xml_clip else None,
        timeline_item_index=timeline_item.item_index if timeline_item else None,
        xml_name=xml_clip.name if xml_clip else None,
        timeline_name=timeline_item.name if timeline_item else None,
        status="pass",
    )

    if xml_clip is None:
        comparison.status = "extra_timeline_item"
        comparison.issues.append(
            Issue(
                code="qc_extra_timeline_item",
                severity="ERROR",
                message="Resolve timeline has an item with no matching XML clip at this track position.",
                context=_comparison_context(track_index, item_index, xml_clip, timeline_item),
            )
        )
        return comparison

    if timeline_item is None:
        comparison.status = "missing_timeline_item"
        comparison.issues.append(
            Issue(
                code="qc_missing_timeline_item",
                severity="ERROR",
                message="XML clip has no matching Resolve timeline item at this track position.",
                context=_comparison_context(track_index, item_index, xml_clip, timeline_item),
            )
        )
        return comparison

    if timeline_item.is_offline:
        comparison.issues.append(
            Issue(
                code="qc_offline_timeline_item",
                severity="ERROR",
                message="Resolve timeline item has no Media Pool item.",
                context=_comparison_context(track_index, item_index, xml_clip, timeline_item),
            )
        )

    names_match = _normalize_name(xml_clip.name) == _normalize_name(timeline_item.name)
    if not names_match:
        comparison.issues.append(
            Issue(
                code="qc_name_mismatch",
                severity="ERROR",
                message="XML clip name does not match Resolve timeline item name.",
                context=_comparison_context(track_index, item_index, xml_clip, timeline_item),
            )
        )

    for field_name in FRAME_FIELDS:
        xml_value = _xml_timeline_frame_value(xml_clip, field_name)
        timeline_value = getattr(timeline_item, field_name)
        if xml_value is None or timeline_value is None:
            continue
        if field_name in {"start", "end"} and _frame_suffix_matches(xml_value, timeline_value):
            continue
        if xml_value != timeline_value:
            comparison.issues.append(
                Issue(
                    code=f"qc_{field_name}_mismatch",
                    severity="ERROR",
                    message=f"XML {field_name} does not match Resolve timeline item {field_name}.",
                    context={
                        **_comparison_context(track_index, item_index, xml_clip, timeline_item),
                        "xml_value": xml_value,
                        "timeline_value": timeline_value,
                    },
                )
            )

    if not names_match:
        for xml_field_name, timeline_field_name in SOURCE_FRAME_FIELDS:
            xml_value = getattr(xml_clip, xml_field_name)
            timeline_value = getattr(timeline_item, timeline_field_name)
            if xml_value is None:
                continue
            if timeline_value is None:
                comparison.issues.append(
                    Issue(
                        code=f"qc_{xml_field_name}_unavailable",
                        severity="WARNING",
                        message=f"Resolve timeline item {timeline_field_name} could not be read for source in/out QC.",
                        context={
                            **_comparison_context(track_index, item_index, xml_clip, timeline_item),
                            "xml_value": xml_value,
                            "timeline_field": timeline_field_name,
                        },
                    )
                )
                continue
            if xml_value != timeline_value:
                comparison.issues.append(
                    Issue(
                        code=f"qc_{xml_field_name}_mismatch",
                        severity="WARNING",
                        message=f"XML {xml_field_name} does not match Resolve timeline item {timeline_field_name}.",
                        context={
                            **_comparison_context(track_index, item_index, xml_clip, timeline_item),
                            "xml_value": xml_value,
                            "timeline_value": timeline_value,
                        },
                    )
                )

    if _looks_like_compound_name(xml_clip.name) or _looks_like_compound_name(timeline_item.name):
        comparison.issues.append(
            Issue(
                code="qc_possible_compound_item",
                severity="WARNING",
                message="Clip name contains a marker that may indicate a compound, nested, or multicam item.",
                context=_comparison_context(track_index, item_index, xml_clip, timeline_item),
            )
        )

    if comparison.issues:
        comparison.status = "fail" if any(issue.severity == "ERROR" for issue in comparison.issues) else "warning"
    return comparison


def _comparison_difference_row(comparison: ClipComparison) -> dict[str, object]:
    return {
        "问题类型": "、".join(_issue_label(issue.code) for issue in comparison.issues),
        "问题描述": _comparison_problem_description(comparison),
        "XML轨道": comparison.track_index,
        "轨道内序号": comparison.item_index,
        "XML片段序号": comparison.xml_clip_index,
        "Resolve片段序号": comparison.timeline_item_index,
        "XML片段名称": comparison.xml_name,
        "Resolve片段名称": comparison.timeline_name,
        "问题代码": [issue.code for issue in comparison.issues],
    }


def _missing_media_description(match: MediaMatch) -> str:
    if match.clip.decoded_path or match.clip.pathurl:
        return f"XML 第 {match.clip.index} 个片段 `{match.clip.name}` 指向的素材路径没有在本地素材目录中找到。"
    return f"XML 第 {match.clip.index} 个片段 `{match.clip.name}` 没有 file/pathurl，Resolve 可能无法按普通素材正确导入。"


def _top_level_issue_row(issue: Issue) -> dict[str, object]:
    return {
        "问题类型": _issue_label(issue.code),
        "问题描述": _top_level_issue_description(issue),
        "问题代码": issue.code,
        "严重程度": issue.severity,
        "上下文": issue.context,
    }


def _top_level_issue_description(issue: Issue) -> str:
    if issue.code == "qc_clip_count_mismatch":
        return f"XML 共有 {issue.context.get('xml_count')} 个片段，但 Resolve 时间线读回 {issue.context.get('timeline_count')} 个片段。"
    if issue.code == "qc_track_count_mismatch":
        return (
            f"XML V{issue.context.get('track_index')} 有 {issue.context.get('xml_count')} 个片段，"
            f"Resolve 对应轨道读回 {issue.context.get('timeline_count')} 个片段。"
        )
    return issue.message


SOURCE_TIMECODE_ISSUE_CODES = {
    "qc_source_in_mismatch",
    "qc_source_out_mismatch",
}
SOURCE_TIMECODE_REPORT_CODES = SOURCE_TIMECODE_ISSUE_CODES | {
    "qc_source_in_unavailable",
    "qc_source_out_unavailable",
}


def calculate_match_success_percentage(
    xml_result: XmlPrecheckResult,
    matches: Iterable[MediaMatch],
    qc_result: ConformQcResult,
) -> float:
    """Calculate conform success percent, counting source-only mismatches as success."""
    total = len(xml_result.clips)
    if total == 0:
        return 0.0
    comparisons_by_xml = _comparisons_by_xml_clip_index(qc_result)
    failed_clip_indexes: set[int] = set()
    for match in matches:
        if match.status in {"missing", "multiple_candidates"}:
            if match.status == "missing" and _ignore_empty_path_missing_match(
                match,
                comparisons_by_xml.get(match.clip.index),
            ):
                continue
            failed_clip_indexes.add(match.clip.index)
    for comparison in qc_result.comparisons:
        issue_codes = {issue.code for issue in comparison.issues}
        if not issue_codes:
            continue
        if issue_codes <= SOURCE_TIMECODE_ISSUE_CODES:
            continue
        if comparison.xml_clip_index is not None:
            failed_clip_indexes.add(comparison.xml_clip_index)
    return round(((total - len(failed_clip_indexes)) / total) * 100, 2)


def build_import_difference_sections(
    xml_result: XmlPrecheckResult,
    matches: Iterable[MediaMatch],
    import_result: ResolveImportResult,
    timeline_result: TimelineReadbackResult,
    qc_result: ConformQcResult,
) -> dict[str, object]:
    """Build problem-only Chinese report sections in the requested order."""
    match_list = list(matches)
    comparisons_by_xml = _comparisons_by_xml_clip_index(qc_result)
    missing_rows = [
        _missing_media_row_cn(match)
        for match in match_list
        if match.status == "missing"
        and not _ignore_empty_path_missing_match(match, comparisons_by_xml.get(match.clip.index))
    ]
    missing_rows.extend(
        _comparison_row_cn(comparison)
        for comparison in qc_result.comparisons
        if _comparison_has_any(comparison, {"qc_missing_timeline_item", "qc_extra_timeline_item"})
    )
    name_rows = [
        _comparison_row_cn(comparison)
        for comparison in qc_result.comparisons
        if _comparison_has_any(comparison, {"qc_name_mismatch"})
    ]
    multi_candidate_rows = [
        {
            "问题类型": "多个素材候选",
            "问题描述": f"XML 第 {match.clip.index} 个片段 `{match.clip.name}` 匹配到 {len(match.candidates)} 个本地素材候选，需要人工确认。",
            "XML片段序号": match.clip.index,
            "XML轨道": match.clip.track_index,
            "片段名称": match.clip.name,
            "候选数量": len(match.candidates),
            "候选素材": [str(path) for path in match.candidates],
        }
        for match in match_list
        if match.status == "multiple_candidates"
    ]
    import_failure_rows = [
        {
            "问题类型": "XML导入尝试失败",
            "问题描述": f"第 {attempt.attempt} 次 XML 导入未成功。Resolve 返回类型：{attempt.result_type}。",
            "尝试序号": attempt.attempt,
            "导入选项": attempt.options,
            "错误": attempt.error,
            "返回值": attempt.result_repr,
        }
        for attempt in import_result.xml_import_attempts
        if not attempt.success
    ]
    track_rows = [
        _top_level_issue_row_cn(issue)
        for issue in qc_result.issues
        if issue.code in {"qc_clip_count_mismatch", "qc_track_count_mismatch"}
    ]
    offline_rows = [
        {
            "问题类型": "时间线离线",
            "问题描述": f"Resolve V{item.track_index} 第 {item.item_index} 个片段 `{item.name}` 没有 Media Pool item，可能处于离线状态。",
            "Resolve轨道": item.track_index,
            "Resolve序号": item.item_index,
            "片段名称": item.name,
            "开始帧": item.start,
            "结束帧": item.end,
            "持续帧数": item.duration,
        }
        for item in timeline_result.video_items
        if item.is_offline
    ]
    other_rows = [
        _comparison_row_cn(comparison)
        for comparison in qc_result.comparisons
        if comparison.issues
        and not _comparison_has_any(
            comparison,
            {
                "qc_missing_timeline_item",
                "qc_extra_timeline_item",
                "qc_name_mismatch",
                *SOURCE_TIMECODE_REPORT_CODES,
            },
        )
    ]
    source_rows = [
        _comparison_row_cn(comparison)
        for comparison in qc_result.comparisons
        if _comparison_has_any(comparison, SOURCE_TIMECODE_REPORT_CODES)
    ]
    return {
        "镜头缺失报告": missing_rows,
        "镜头名不匹配报告": name_rows,
        "多个素材候选报告": multi_candidate_rows,
        "导入失败尝试": import_failure_rows,
        "轨道和数量差异": track_rows,
        "时间线离线片段": offline_rows,
        "其他问题": other_rows,
        "出入点时间码问题": source_rows,
    }


def collect_problem_issues(
    matches: Iterable[MediaMatch],
    import_result: ResolveImportResult,
    timeline_result: TimelineReadbackResult,
    qc_result: ConformQcResult,
) -> list[Issue]:
    """Collect report issues; source in/out mismatches are warnings."""
    issues: list[Issue] = []
    comparisons_by_xml = _comparisons_by_xml_clip_index(qc_result)
    for match in matches:
        if match.status in {"missing", "multiple_candidates"}:
            if match.status == "missing" and _ignore_empty_path_missing_match(
                match,
                comparisons_by_xml.get(match.clip.index),
            ):
                continue
            issues.extend(_localized_issue(issue) for issue in match.issues)
    issues.extend(_localized_issue(issue) for issue in import_result.issues)
    issues.extend(_localized_issue(issue) for issue in timeline_result.issues)
    issues.extend(_localized_issue(issue) for issue in qc_result.issues)
    return issues


def _missing_media_row_cn(match: MediaMatch) -> dict[str, object]:
    return {
        "问题类型": "素材缺失",
        "问题描述": _missing_media_description_cn(match),
        "XML片段序号": match.clip.index,
        "XML轨道": match.clip.track_index,
        "片段名称": match.clip.name,
        "XML原路径": match.clip.decoded_path or match.clip.pathurl or "空路径",
    }


def _comparison_row_cn(comparison: ClipComparison) -> dict[str, object]:
    return {
        "问题类型": "、".join(_issue_label(issue.code) for issue in comparison.issues),
        "问题描述": _comparison_problem_description_cn(comparison),
        "XML轨道": comparison.track_index,
        "轨道内序号": comparison.item_index,
        "XML片段序号": comparison.xml_clip_index,
        "Resolve片段序号": comparison.timeline_item_index,
        "XML片段名称": comparison.xml_name,
        "Resolve片段名称": comparison.timeline_name,
        "问题代码": [issue.code for issue in comparison.issues],
    }


def _comparison_has_any(comparison: ClipComparison, codes: set[str]) -> bool:
    return any(issue.code in codes for issue in comparison.issues)


def _missing_media_description_cn(match: MediaMatch) -> str:
    if match.clip.decoded_path or match.clip.pathurl:
        return f"XML 第 {match.clip.index} 个片段 `{match.clip.name}` 指向的素材路径没有在本地素材目录中找到。"
    return f"XML 第 {match.clip.index} 个片段 `{match.clip.name}` 没有 file/pathurl，Resolve 可能无法按普通素材正确导入。"


def _top_level_issue_row_cn(issue: Issue) -> dict[str, object]:
    return {
        "问题类型": _issue_label(issue.code),
        "问题描述": _top_level_issue_description_cn(issue),
        "问题代码": issue.code,
        "严重程度": issue.severity,
        "上下文": issue.context,
    }


def _top_level_issue_description_cn(issue: Issue) -> str:
    if issue.code == "qc_clip_count_mismatch":
        return f"XML 共有 {issue.context.get('xml_count')} 个片段，但 Resolve 时间线读回 {issue.context.get('timeline_count')} 个片段。"
    if issue.code == "qc_track_count_mismatch":
        return f"XML V{issue.context.get('track_index')} 有 {issue.context.get('xml_count')} 个片段，Resolve 对应轨道读回 {issue.context.get('timeline_count')} 个片段。"
    return issue.message


def _comparison_problem_description_cn(comparison: ClipComparison) -> str:
    return "；".join(_single_issue_description(issue, comparison) for issue in comparison.issues)


def _comparison_problem_description(comparison: ClipComparison) -> str:
    parts = [_single_issue_description(issue, comparison) for issue in comparison.issues]
    return "；".join(part for part in parts if part)


def _single_issue_description(issue: Issue, comparison: ClipComparison) -> str:
    if issue.code == "qc_missing_timeline_item":
        return f"XML V{comparison.track_index} 第 {comparison.item_index} 个片段 `{comparison.xml_name}` 在 Resolve 时间线中没有对应片段"
    if issue.code == "qc_extra_timeline_item":
        return f"Resolve V{comparison.track_index} 第 {comparison.item_index} 个片段 `{comparison.timeline_name}` 在 XML 中没有对应片段"
    if issue.code == "qc_name_mismatch":
        return f"XML 片段名是 `{comparison.xml_name}`，但 Resolve 对应位置是 `{comparison.timeline_name}`"
    if issue.code == "qc_offline_timeline_item":
        return f"Resolve 片段 `{comparison.timeline_name}` 没有 Media Pool item，可能离线"
    if issue.code == "qc_start_mismatch":
        return f"开始帧不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_end_mismatch":
        return f"结束帧不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_duration_mismatch":
        return f"持续帧数不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_possible_compound_item":
        return f"片段 `{comparison.xml_name or comparison.timeline_name}` 名称疑似嵌套/复合片段，需要人工复核"
    return issue.message


def _issue_label(code: str) -> str:
    return {
        "qc_clip_count_mismatch": "片段总数不一致",
        "qc_track_count_mismatch": "轨道片段数不一致",
        "qc_missing_timeline_item": "Resolve缺少片段",
        "qc_extra_timeline_item": "Resolve多出片段",
        "qc_name_mismatch": "片段名称不一致",
        "qc_offline_timeline_item": "片段离线",
        "qc_start_mismatch": "开始帧不一致",
        "qc_end_mismatch": "结束帧不一致",
        "qc_duration_mismatch": "持续帧数不一致",
        "qc_possible_compound_item": "疑似嵌套/复合片段",
        "qc_possible_compound_xml": "XML含嵌套序列",
    }.get(code, code)


def _localized_issue(issue: Issue) -> Issue:
    return Issue(
        code=issue.code,
        severity=issue.severity,
        message=_issue_message_cn(issue),
        context=issue.context,
    )


def _issue_message_cn(issue: Issue) -> str:
    if issue.code == "media_missing":
        return f"没有找到 XML 片段 `{issue.context.get('clip_name')}` 对应的本地素材。"
    if issue.code == "media_multiple_candidates":
        return f"XML 片段 `{issue.context.get('clip_name')}` 匹配到多个本地素材候选，需要人工确认。"
    if issue.code == "resolve_xml_import_failed":
        return "Resolve 没有从 XML 创建新的当前时间线。"
    if issue.code == "qc_possible_compound_xml":
        return "XML 中发现嵌套序列信息，需要人工复核复合/嵌套片段。"
    if issue.code in {"qc_clip_count_mismatch", "qc_track_count_mismatch"}:
        return _top_level_issue_description(issue)
    if issue.code == "qc_missing_timeline_item":
        return f"XML 片段 `{issue.context.get('xml_name')}` 在 Resolve 时间线中没有对应片段。"
    if issue.code == "qc_extra_timeline_item":
        return f"Resolve 片段 `{issue.context.get('timeline_name')}` 在 XML 中没有对应片段。"
    if issue.code == "qc_name_mismatch":
        return f"XML 片段 `{issue.context.get('xml_name')}` 与 Resolve 片段 `{issue.context.get('timeline_name')}` 名称不一致。"
    if issue.code == "qc_offline_timeline_item":
        return f"Resolve 片段 `{issue.context.get('timeline_name')}` 处于离线或缺少 Media Pool item。"
    if issue.code == "qc_possible_compound_item":
        return f"片段 `{issue.context.get('xml_name') or issue.context.get('timeline_name')}` 疑似嵌套/复合片段，需要人工复核。"
    if issue.code == "qc_start_mismatch":
        return "XML 与 Resolve 的开始帧不一致。"
    if issue.code == "qc_end_mismatch":
        return "XML 与 Resolve 的结束帧不一致。"
    if issue.code == "qc_duration_mismatch":
        return "XML 与 Resolve 的持续帧数不一致。"
    return issue.message


def _xml_clips(xml_result: XmlPrecheckResult | Iterable[XmlClip]) -> list[XmlClip]:
    if isinstance(xml_result, XmlPrecheckResult):
        return list(xml_result.clips)
    return list(xml_result)


def _group_xml_by_track(clips: Iterable[XmlClip]) -> dict[int, list[XmlClip]]:
    grouped: dict[int, list[XmlClip]] = defaultdict(list)
    for clip in clips:
        grouped[clip.track_index or 1].append(clip)
    return dict(grouped)


def _group_timeline_by_track(items: Iterable[TimelineItemRecord]) -> dict[int, list[TimelineItemRecord]]:
    grouped: dict[int, list[TimelineItemRecord]] = defaultdict(list)
    for item in items:
        grouped[item.track_index].append(item)
    return {track: sorted(track_items, key=lambda value: value.item_index) for track, track_items in grouped.items()}


def _comparison_context(
    track_index: int,
    item_index: int,
    xml_clip: XmlClip | None,
    timeline_item: TimelineItemRecord | None,
) -> dict[str, object]:
    return {
        "track_index": track_index,
        "item_index": item_index,
        "xml_clip_index": xml_clip.index if xml_clip else None,
        "xml_name": xml_clip.name if xml_clip else None,
        "timeline_item_index": timeline_item.item_index if timeline_item else None,
        "timeline_name": timeline_item.name if timeline_item else None,
        "media_pool_name": timeline_item.media_pool_name if timeline_item else None,
        "media_file_name": Path(timeline_item.media_file_path).name if timeline_item and timeline_item.media_file_path else None,
    }


def _compound_xml_issues(xml_issues: Iterable[Issue]) -> list[Issue]:
    issues: list[Issue] = []
    for issue in xml_issues:
        if issue.code not in COMPOUND_XML_ISSUE_CODES:
            continue
        issues.append(
            Issue(
                code="qc_possible_compound_xml",
                severity="WARNING",
                message="XML precheck found nested sequence metadata that may require compound/nested review.",
                context=issue.context,
            )
        )
    return issues


def _normalize_name(value: str | None) -> str:
    return (value or "").strip().casefold()


def _frame_suffix_matches(xml_value: int, timeline_value: int) -> bool:
    xml_digits = str(abs(int(xml_value)))
    timeline_digits = str(abs(int(timeline_value)))
    return bool(xml_digits) and timeline_digits.endswith(xml_digits)


def _comparisons_by_xml_clip_index(qc_result: ConformQcResult) -> dict[int, ClipComparison]:
    return {
        comparison.xml_clip_index: comparison
        for comparison in qc_result.comparisons
        if comparison.xml_clip_index is not None
    }


def _ignore_empty_path_missing_match(match: MediaMatch, comparison: ClipComparison | None) -> bool:
    if match.status != "missing":
        return False
    if match.clip.decoded_path or match.clip.pathurl:
        return False
    if comparison is None:
        return False
    return _normalize_name(match.clip.name) == _normalize_name(comparison.timeline_name)


def _xml_timeline_frame_value(xml_clip: XmlClip, field_name: str) -> int | None:
    if field_name == "duration":
        if xml_clip.start is None or xml_clip.end is None:
            return None
        return xml_clip.end - xml_clip.start
    return getattr(xml_clip, field_name)


def _looks_like_compound_name(value: str | None) -> bool:
    text = _normalize_name(value)
    return any(marker in text for marker in COMPOUND_NAME_MARKERS)


def _single_issue_description(issue: Issue, comparison: ClipComparison) -> str:
    if issue.code == "qc_missing_timeline_item":
        return f"XML V{comparison.track_index} 第 {comparison.item_index} 个片段 `{comparison.xml_name}` 在 Resolve 时间线中没有对应片段"
    if issue.code == "qc_extra_timeline_item":
        return f"Resolve V{comparison.track_index} 第 {comparison.item_index} 个片段 `{comparison.timeline_name}` 在 XML 中没有对应片段"
    if issue.code == "qc_name_mismatch":
        return f"XML 片段名是 `{comparison.xml_name}`，但 Resolve 对应位置是 `{comparison.timeline_name}`"
    if issue.code == "qc_offline_timeline_item":
        return f"Resolve 片段 `{comparison.timeline_name}` 没有 Media Pool item，可能离线"
    if issue.code == "qc_start_mismatch":
        return f"开始帧不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_end_mismatch":
        return f"结束帧不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_duration_mismatch":
        return f"持续帧数不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_source_in_mismatch":
        return f"源入点不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_source_out_mismatch":
        return f"源出点不一致：XML={issue.context.get('xml_value')}，Resolve={issue.context.get('timeline_value')}"
    if issue.code == "qc_source_in_unavailable":
        return "Resolve 源入点无法读取，不能确认该片段源入点是否正确"
    if issue.code == "qc_source_out_unavailable":
        return "Resolve 源出点无法读取，不能确认该片段源出点是否正确"
    if issue.code == "qc_possible_compound_item":
        return f"片段 `{comparison.xml_name or comparison.timeline_name}` 名称疑似嵌套/复合片段，需要人工复核"
    return issue.message


def _issue_label(code: str) -> str:
    return {
        "qc_clip_count_mismatch": "片段总数不一致",
        "qc_track_count_mismatch": "轨道片段数不一致",
        "qc_missing_timeline_item": "Resolve缺少片段",
        "qc_extra_timeline_item": "Resolve多出片段",
        "qc_name_mismatch": "片段名称不一致",
        "qc_offline_timeline_item": "片段离线",
        "qc_start_mismatch": "开始帧不一致",
        "qc_end_mismatch": "结束帧不一致",
        "qc_duration_mismatch": "持续帧数不一致",
        "qc_source_in_mismatch": "源入点不一致",
        "qc_source_out_mismatch": "源出点不一致",
        "qc_source_in_unavailable": "源入点无法读取",
        "qc_source_out_unavailable": "源出点无法读取",
        "qc_possible_compound_item": "疑似嵌套/复合片段",
        "qc_possible_compound_xml": "XML含嵌套序列",
    }.get(code, code)


def _issue_message_cn(issue: Issue) -> str:
    if issue.code == "media_missing":
        return f"没有找到 XML 片段 `{issue.context.get('clip_name')}` 对应的本地素材。"
    if issue.code == "media_multiple_candidates":
        return f"XML 片段 `{issue.context.get('clip_name')}` 匹配到多个本地素材候选，需要人工确认。"
    if issue.code == "resolve_xml_import_failed":
        return "Resolve 没有从 XML 创建新的当前时间线。"
    if issue.code == "qc_possible_compound_xml":
        return "XML 中发现嵌套序列信息，需要人工复核复合/嵌套片段。"
    if issue.code in {"qc_clip_count_mismatch", "qc_track_count_mismatch"}:
        return _top_level_issue_description(issue)
    if issue.code == "qc_missing_timeline_item":
        return f"XML 片段 `{issue.context.get('xml_name')}` 在 Resolve 时间线中没有对应片段。"
    if issue.code == "qc_extra_timeline_item":
        return f"Resolve 片段 `{issue.context.get('timeline_name')}` 在 XML 中没有对应片段。"
    if issue.code == "qc_name_mismatch":
        return f"XML 片段 `{issue.context.get('xml_name')}` 与 Resolve 片段 `{issue.context.get('timeline_name')}` 名称不一致。"
    if issue.code == "qc_offline_timeline_item":
        return f"Resolve 片段 `{issue.context.get('timeline_name')}` 处于离线或缺少 Media Pool item。"
    if issue.code == "qc_possible_compound_item":
        return f"片段 `{issue.context.get('xml_name') or issue.context.get('timeline_name')}` 疑似嵌套/复合片段，需要人工复核。"
    if issue.code == "qc_start_mismatch":
        return "XML 与 Resolve 的开始帧不一致。"
    if issue.code == "qc_end_mismatch":
        return "XML 与 Resolve 的结束帧不一致。"
    if issue.code == "qc_duration_mismatch":
        return "XML 与 Resolve 的持续帧数不一致。"
    if issue.code == "qc_source_in_mismatch":
        return f"XML 片段 `{issue.context.get('xml_name')}` 与 Resolve 的源入点不一致。"
    if issue.code == "qc_source_out_mismatch":
        return f"XML 片段 `{issue.context.get('xml_name')}` 与 Resolve 的源出点不一致。"
    if issue.code == "qc_source_in_unavailable":
        return f"Resolve 无法读取片段 `{issue.context.get('timeline_name')}` 的源入点。"
    if issue.code == "qc_source_out_unavailable":
        return f"Resolve 无法读取片段 `{issue.context.get('timeline_name')}` 的源出点。"
    return issue.message
