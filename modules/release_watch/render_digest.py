#!/usr/bin/env python3
"""Render a GitHub checker digest JSON to Outlook-friendly HTML.

Reads JSON from stdin and prints HTML to stdout.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from html import escape
from typing import Any

BG = "#f4f6f8"
CARD = "#ffffff"
BORDER = "#d9e0e7"
TEXT = "#1f2937"
MUTED = "#64748b"
DARK = "#0f172a"
ACCENT = "#0ea5e9"

# Heading sizes
H1 = 36
H2 = 16
H3 = 16
H4 = 12
H5 = 12
SUCCESS_BG = "#ecfdf5"
SUCCESS_TEXT = "#166534"
INFO_BG = "#eff6ff"
INFO_TEXT = "#1d4ed8"
WARN_BG = "#fff7ed"
WARN_TEXT = "#9a3412"
ERROR_BG = "#fef2f2"
ERROR_TEXT = "#b91c1c"
TABLE_HEAD = "#eaf2f8"
TABLE_ROW = "#f8fafc"


def _load_digest() -> dict[str, Any]:
    raw = sys.stdin.read()
    return json.loads(raw)


def _esc(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _status_colors(status: str) -> tuple[str, str, str]:
    if status == "updated":
        return ("Updated", SUCCESS_BG, SUCCESS_TEXT)
    if status == "first_seen":
        return ("First seen", INFO_BG, INFO_TEXT)
    if status == "error":
        return ("Error", ERROR_BG, ERROR_TEXT)
    return ("Unchanged", TABLE_ROW, MUTED)


def _semver_badge(change: Any) -> str:
    mapping = {
        "major": ("Major", "#fee2e2", "#991b1b"),
        "minor": ("Minor", "#dbeafe", "#1d4ed8"),
        "patch": ("Patch", "#dcfce7", "#166534"),
        "non-semver": ("Non-semver", "#f3e8ff", "#7e22ce"),
        "same": ("Same", "#e5e7eb", "#4b5563"),
    }
    label, bg, fg = mapping.get(str(change or ""), (None, None, None))
    if not label:
        return ""
    return (
        f'<span style="display:inline-block;margin-left:8px;padding:2px 8px;'
        f'background:{bg};color:{fg};font-size:11px;line-height:16px;font-weight:bold;'
        f'border:1px solid {bg};border-radius:999px;">{_esc(label)}</span>'
    )


def _notes_excerpt_html(item: dict[str, Any]) -> str:
    excerpt = item.get("release_notes_excerpt") or ""
    if not excerpt:
        return ""
    return f'<div style="font-size:12px;line-height:18px;color:{TEXT};margin-top:6px;">{_esc(excerpt)}</div>'


def _attention_palette(level: Any) -> tuple[str, str]:
    palette = {
        "high": ("#fee2e2", "#991b1b"),
        "medium": ("#fef3c7", "#92400e"),
        "low": ("#dcfce7", "#166534"),
    }
    return palette.get(str(level), ("#e5e7eb", "#374151"))


def _trend_label(trend: Any) -> str:
    mapping = {
        "accelerating": "faster lately",
        "slowing": "slower lately",
        "stable": "steady",
        "volatile": "big upgrades lately",
        "noisy": "many small releases",
        "new": "too new to judge",
    }
    return mapping.get(str(trend), str(trend).replace("_", " ").title())


def _badge(text: str, bg: str, fg: str, *, border: str | None = None) -> str:
    border_color = border or bg
    return (
        f'<span style="display:inline-block;padding:2px 8px;'
        f'background:{bg};color:{fg};font-size:11px;line-height:16px;font-weight:bold;'
        f'border:1px solid {border_color};border-radius:999px;">{_esc(text)}</span>'
    )


def _signal_badges_html(item: dict[str, Any]) -> str:
    badges: list[str] = []

    if item.get("has_security_advisories"):
        count = item.get("advisories_count")
        text = f'Security{f" ({count})" if count not in (None, "") else ""}'
        badges.append(_badge(text, "#fff7ed", "#9a3412", border="#fed7aa"))

    level = item.get("release_attention")
    if level:
        bg, fg = _attention_palette(level)
        badges.append(_badge(f'Attention: {str(level).title()}', bg, fg))

    if not badges:
        return ""
    separator = f'<span style="color:{MUTED};font-size:11px;line-height:16px;">&nbsp;·&nbsp;</span>'
    return f'<div style="margin-top:8px;">{separator.join(badges)}</div>'


def _human_count(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return _esc(value)

    abs_number = abs(number)
    if abs_number < 1000:
        return str(number)
    if abs_number < 10000:
        return f'{number / 1000:.1f}k'.replace('.0k', 'k')
    if abs_number < 1_000_000:
        return f'{round(number / 1000):.0f}k'
    return f'{number / 1_000_000:.1f}M'.replace('.0M', 'M')


def _repo_context_html(item: dict[str, Any]) -> str:
    parts = []
    stars = item.get("stars")
    forks = item.get("forks")
    stars_delta = item.get("stars_delta")
    forks_delta = item.get("forks_delta")

    if stars is not None:
        star_text = _human_count(stars)
        if stars_delta not in (None, 0):
            star_text += f' ({_human_count(stars_delta) if int(stars_delta) < 0 else "+" + _human_count(stars_delta)})'
        parts.append(
            f'<span style="display:inline-block;color:{MUTED};font-size:13px;line-height:20px;white-space:nowrap;">'
            f'&nbsp;·&nbsp;<span style="color:#eab308;font-weight:bold;">★</span> {_esc(star_text)}</span>'
        )
    if forks is not None:
        fork_text = _human_count(forks)
        if forks_delta not in (None, 0):
            fork_text += f' ({_human_count(forks_delta) if int(forks_delta) < 0 else "+" + _human_count(forks_delta)})'
        parts.append(
            f'<span style="display:inline-block;color:{MUTED};font-size:13px;line-height:20px;white-space:nowrap;">'
            f'&nbsp;·&nbsp;<span style="color:{MUTED};font-weight:bold;">Forks</span> {_esc(fork_text)}</span>'
        )

    if not parts:
        return ""
    return ''.join(parts)


def _section_title_html(title: str) -> str:
    return f'<div style="font-size:13px;line-height:18px;font-weight:bold;letter-spacing:0.04em;text-transform:uppercase;color:{MUTED};">{_esc(title)}</div>'


def _summary_header_html(heading_badges_html: str = "") -> str:
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="border-collapse:collapse;margin-top:8px;width:100%;">'
        '<tr>'
        f'<td valign="top" style="font-size:13px;line-height:18px;font-weight:bold;letter-spacing:0.04em;text-transform:uppercase;color:{MUTED};">Latest release summary</td>'
        f'<td align="right" valign="top" style="font-size:11px;line-height:16px;color:{TEXT};white-space:nowrap;">{heading_badges_html}</td>'
        '</tr>'
        '</table>'
    )


def _detail_block_html(details: str) -> str:
    if not details:
        return ""
    return f'<div style="font-size:12px;line-height:18px;color:{TEXT};margin-top:4px;">{_esc(details)}</div>'


def _meaning_text(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "unchanged")
    error_text = item.get("error") or ""
    excerpt = item.get("release_notes_excerpt") or ""
    action = item.get("release_attention_action") or ""

    if status == "error":
        return error_text or "GitHub metadata was unavailable for this repository in this cycle."
    if excerpt:
        return excerpt
    if status == "first_seen":
        latest = item.get("latest_tag") or "latest release"
        return f'Newly added to tracking at {latest}.'
    if action:
        return action
    return ""


def _published_label(value: str | None) -> str:
    if not value:
        return "—"
    return _esc(value.replace("T", " ").replace("Z", " UTC"))


def _summary_card(label: str, value: Any, bg: str, fg: str) -> str:
    return (
        f'<td width="33.33%" valign="top" style="padding:0 8px 0 0;">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        f'style="border-collapse:collapse;background:{bg};border:1px solid {BORDER};">'
        f'<tr><td style="padding:14px 16px;">'
        f'<div style="font-size:12px;line-height:18px;color:{fg};text-transform:uppercase;letter-spacing:0.04em;">{_esc(label)}</div>'
        f'<div style="font-size:28px;line-height:32px;font-weight:bold;color:{fg};margin-top:4px;">{_esc(value)}</div>'
        f'</td></tr></table></td>'
    )


def _status_badge_html(item: dict[str, Any]) -> str:
    status = str(item.get("status") or "unchanged")
    if status == "unchanged":
        return ""
    label, bg, fg = _status_colors(status)
    return f'<span style="display:inline-block;vertical-align:middle;">&nbsp;·&nbsp;<span style="display:inline-block;padding:3px 8px;background:{bg};color:{fg};font-size:11px;line-height:16px;font-weight:bold;border:1px solid {bg};border-radius:999px;">{_esc(label)}</span></span>'


def _timing_meta_html(item: dict[str, Any]) -> str:
    days_since = item.get("days_since_last_release")
    avg = item.get("avg_release_interval_days")
    trend = item.get("repo_trend")
    parts = []
    if days_since is not None:
        parts.append(f'since {days_since}d')
    if avg is not None:
        parts.append(f'avg {avg}d')
    if trend:
        parts.append(f'pace {_trend_label(trend)}')
    if not parts:
        return ""
    return _esc(" · ".join(parts))


def _repo_entry_html(item: dict[str, Any], *, details_override: str | None = None, show_summary_heading: bool = True) -> str:
    repo = _esc(item.get("repo"))
    latest = _esc(item.get("latest_tag") or "—")
    link = _esc(item.get("html_url") or "")
    repo_html = f'<a href="{link}" style="color:{ACCENT};text-decoration:none;font-size:17px;line-height:24px;font-weight:bold;">{repo}</a>' if link else f'<span style="font-size:17px;line-height:24px;font-weight:bold;color:{DARK};">{repo}</span>'
    desc = item.get("description") or ''
    desc_html = (
        f'{_section_title_html("Project overview")}<div style="font-size:{H4}px;line-height:18px;color:{MUTED};margin-top:4px;">{_esc(desc)}</div>'
        if desc else ''
    )
    context_html = _repo_context_html(item)
    status_html = _status_badge_html(item)
    semver_change = item.get("semver_change")
    semver_html = "" if semver_change == "same" else _semver_badge(semver_change)
    version_html = f'<span style="display:inline-block;font-size:13px;line-height:20px;color:{TEXT};vertical-align:middle;">&nbsp;·&nbsp;{latest}{semver_html}</span>'
    timing_html = _timing_meta_html(item)
    signal_badges = _signal_badges_html(item)
    heading_badges_html = ""
    if signal_badges and show_summary_heading:
        heading_badges_html = signal_badges.replace('<div style="margin-top:8px;">', '', 1).replace('</div>', '', 1)
    meaning_text = details_override if details_override is not None else _meaning_text(item)
    summary_header_html = _summary_header_html(heading_badges_html) if show_summary_heading and meaning_text else ""
    meaning_html = _detail_block_html(meaning_text) if meaning_text else ""
    release_meta_html = f'<span style="display:inline-block;font-size:11px;line-height:16px;color:{MUTED};vertical-align:middle;">&nbsp;·&nbsp;{timing_html}</span>' if timing_html else ''
    header_html = f'<div style="font-size:17px;line-height:24px;font-weight:bold;color:{DARK};">{repo_html}{context_html}{status_html}{version_html}{release_meta_html}</div>'

    rows = [
        f'<tr><td style="padding:14px 16px 0 16px;font-size:13px;line-height:20px;color:{TEXT};">{header_html}</td></tr>'
    ]
    if desc_html:
        rows.append(
            f'<tr><td style="padding:8px 16px 0 16px;font-size:12px;line-height:18px;color:{MUTED};">{desc_html}</td></tr>'
        )
    if signal_badges and not show_summary_heading:
        rows.append(
            f'<tr><td style="padding:8px 16px 0 16px;font-size:11px;line-height:16px;color:{TEXT};">{signal_badges}</td></tr>'
        )
    if summary_header_html:
        rows.append(
            f'<tr><td style="padding:8px 16px 0 16px;font-size:11px;line-height:16px;color:{TEXT};">{summary_header_html}</td></tr>'
        )
    if meaning_html:
        rows.append(
            f'<tr><td style="padding:4px 16px 14px 16px;font-size:12px;line-height:18px;color:{TEXT};">{meaning_html}</td></tr>'
        )
    else:
        rows.append('<tr><td style="padding:0 0 14px 0;"></td></tr>')

    return (
        '<tr>'
        f'<td style="border-top:1px solid {BORDER};padding:0;">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:100%;">'
        + ''.join(rows)
        + '</table></td></tr>'
    )


def _render_highlights(results: list[dict[str, Any]]) -> str:
    items = [item for item in results if item.get("status") in {"updated", "first_seen", "error"}]
    if not items:
        return ""

    entries = []
    for item in items:
        status = str(item.get("status") or "unchanged")
        latest = item.get("latest_tag") or "—"
        previous = item.get("previous_tag") or "—"
        if status == "updated":
            details = f'{previous} → {latest}'
        elif status == "first_seen":
            details = f'First observed at {latest}'
        elif status == "error":
            details = 'Repository check needs attention'
        else:
            details = str(latest)
        entries.append(_repo_entry_html(item, details_override=details, show_summary_heading=False))

    return (
        '<tr><td style="padding:0 0 18px 0;">'
        f'<div style="font-size:18px;line-height:24px;font-weight:bold;color:{DARK};margin-bottom:10px;">Highlights</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:{CARD};border:1px solid {BORDER};">'
        + ''.join(entries)
        + '</table></td></tr>'
    )


def _render_categorized_table(results: list[dict[str, Any]], categories: list[dict[str, Any]]) -> str:
    """Render results grouped by categories."""
    if not results:
        return (
            '<tr><td style="padding:0 0 18px 0;">'
            f'<div style="font-size:18px;line-height:24px;font-weight:bold;color:{DARK};margin-bottom:10px;">Repository Status</div>'
            f'<div style="font-size:14px;line-height:22px;color:{MUTED};">No tracked repositories yet.</div>'
            '</td></tr>'
        )

    # Build a repo -> result lookup
    result_by_repo: dict[str, dict[str, Any]] = {}
    for item in results:
        result_by_repo[item.get("repo", "")] = item

    # Render categories
    category_sections = []
    uncategorized = []
    categorized_repos = set()

    if categories:
        for cat in categories:
            cat_name = _esc(cat.get("name", "Uncategorized"))
            cat_emoji = _esc(cat.get("emoji", ""))
            cat_desc = _esc(cat.get("description", ""))
            cat_repos = cat.get("repos", [])

            cat_items = []
            for repo in cat_repos:
                if repo in result_by_repo:
                    cat_items.append(result_by_repo[repo])
                    categorized_repos.add(repo)

            if not cat_items:
                continue

            # Category header
            header = (
                '<tr><td style="padding:16px 0 10px 0;">'
                f'<div style="font-size:17px;line-height:24px;font-weight:bold;color:{DARK};">{cat_emoji} {cat_name}</div>'
                f'<div style="font-size:12px;line-height:18px;color:{MUTED};margin-top:3px;">{cat_desc}</div>'
                '</td></tr>'
            )

            entries = ''.join(_repo_entry_html(item) for item in cat_items)
            table = (
                '<tr><td style="padding:0 0 4px 0;">'
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:{CARD};border:1px solid {BORDER};">'
                + entries
                + '</table></td></tr>'
            )

            category_sections.append(header + table)

    # Uncategorized repos
    for item in results:
        if item.get("repo", "") not in categorized_repos:
            uncategorized.append(item)

    if uncategorized:
        header = (
            '<tr><td style="padding:16px 0 10px 0;">'
            f'<div style="font-size:17px;line-height:24px;font-weight:bold;color:{DARK};">📋 Uncategorized</div>'
            '</td></tr>'
        )
        entries = ''.join(_repo_entry_html(item) for item in uncategorized)
        table = (
            '<tr><td style="padding:0 0 4px 0;">'
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:{CARD};border:1px solid {BORDER};">'
            + entries
            + '</table></td></tr>'
        )
        category_sections.append(header + table)

    if not category_sections:
        # Fallback to uncategorized flat table
        return _render_table(results)

    return ''.join(category_sections)


def _render_table(results: list[dict[str, Any]]) -> str:
    if not results:
        return (
            '<tr><td style="padding:0 0 18px 0;">'
            f'<div style="font-size:18px;line-height:24px;font-weight:bold;color:{DARK};margin-bottom:10px;">Repository Status</div>'
            f'<div style="font-size:14px;line-height:22px;color:{MUTED};">No tracked repositories yet.</div>'
            '</td></tr>'
        )

    entries = ''.join(_repo_entry_html(item) for item in results)
    return (
        '<tr><td style="padding:0 0 18px 0;">'
        f'<div style="font-size:18px;line-height:24px;font-weight:bold;color:{DARK};margin-bottom:10px;">Repository Status</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:{CARD};border:1px solid {BORDER};">'
        + entries
        + '</table></td></tr>'
    )


def _ecosystem_card_html(item: dict[str, Any]) -> str:
    repo = _esc(item.get("repo"))
    label = _esc(item.get("label") or repo)
    link = _esc(item.get("html_url") or f'https://github.com/{repo}')
    repo_html = f'<a href="{link}" style="color:{ACCENT};text-decoration:none;font-size:17px;line-height:24px;font-weight:bold;">{label}</a>'
    description = _esc(item.get("description") or "Interesting OpenClaw ecosystem repository")
    reason = _esc(item.get("reason") or "Worth tracking, but kept outside the release digest until it adopts GitHub releases.")
    stars = item.get("stars")
    forks = item.get("forks")
    updated_at = item.get("updated_at")
    meta_bits = []
    if stars is not None:
        meta_bits.append(f'★ {stars}')
    if forks is not None:
        meta_bits.append(f'Forks: {forks}')
    if updated_at:
        meta_bits.append(f'Updated: {_published_label(updated_at)}')
    meta = ' · '.join(meta_bits)
    return (
        '<tr>'
        f'<td style="border-top:1px solid {BORDER};padding:0;">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;width:100%;">'
        f'<tr><td style="padding:14px 16px 0 16px;"><div style="font-size:17px;line-height:24px;font-weight:bold;color:{DARK};">{repo_html}</div></td></tr>'
        f'<tr><td style="padding:4px 16px 0 16px;"><div style="font-size:12px;line-height:18px;color:{MUTED};">{description}</div></td></tr>'
        f'<tr><td style="padding:6px 16px 0 16px;"><div style="font-size:11px;line-height:16px;color:{MUTED};">{_esc(meta)}</div></td></tr>'
        f'<tr><td style="padding:8px 16px 0 16px;"><span style="display:inline-block;padding:3px 8px;background:#f3f4f6;color:#374151;font-size:11px;line-height:16px;font-weight:bold;border:1px solid #e5e7eb;border-radius:999px;">No releases yet</span></td></tr>'
        f'<tr><td style="padding:8px 16px 14px 16px;"><div style="font-size:12px;line-height:18px;color:{TEXT};">{reason}</div></td></tr>'
        '</table></td></tr>'
    )


def _render_interesting_repos(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    entries = ''.join(_ecosystem_card_html(item) for item in items)
    return (
        '<tr><td style="padding:0 0 18px 0;">'
        f'<div style="font-size:18px;line-height:24px;font-weight:bold;color:{DARK};margin-bottom:10px;">OpenClaw Ecosystem Watch</div>'
        f'<div style="font-size:12px;line-height:18px;color:{MUTED};margin-bottom:10px;">Interesting repositories worth tracking separately from the release digest.</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;background:{CARD};border:1px solid {BORDER};">'
        + entries
        + '</table></td></tr>'
    )


def render_html(data: dict[str, Any]) -> str:
    results = list(data.get("results") or [])
    updates = int(data.get("updates") or 0)
    failures = int(data.get("failures") or 0)
    monitored = len(results)
    attention_count = sum(1 for item in results if item.get("release_attention") in {"high", "medium"} or item.get("status") == "error")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Build dynamic subject with updated repo names
    updated_repos = [item.get("repo", "").split("/")[-1] for item in results if item.get("status") in {"updated", "first_seen"}]
    if updated_repos:
        # Take up to 4 repo names for the subject line
        names = updated_repos[:4]
        suffix = " and %d more" % (len(updated_repos) - 4) if len(updated_repos) > 4 else ""
        subject = ", ".join(names) + suffix + " — %d update%s across %d tracked repo%s" % (
            updates, "s" if updates != 1 else "", monitored, "s" if monitored != 1 else ""
        )
    else:
        subject = "No new releases — %d tracked repo%s stable" % (monitored, "s" if monitored != 1 else "")

    has_updates = any(item.get("status") in {"updated", "first_seen"} for item in results)
    intro = (
        "New releases or first-seen repositories were detected in the latest monitoring cycle."
        if has_updates
        else "No new releases were detected in the latest monitoring cycle."
    )

    if failures:
        hero_bg = "#7f1d1d"
        hero_accent = "#fb7185"
        updates_bg = ERROR_BG
        updates_fg = ERROR_TEXT
    elif has_updates:
        hero_bg = "#1d4ed8"
        hero_accent = "#38bdf8"
        updates_bg = "#dbeafe"
        updates_fg = "#1d4ed8"
    else:
        hero_bg = "#134e4a"
        hero_accent = "#5eead4"
        updates_bg = "#ccfbf1"
        updates_fg = "#0f766e"

    categories = list(data.get("categories") or [])
    interesting_repos = list(data.get("interesting_repos") or [])

    parts = [
        '<html><body style="margin:0;padding:0;background:%s;font-family:Arial,Helvetica,sans-serif;color:%s;">' % (BG, TEXT),
        '<table role="presentation" width="100%%" cellspacing="0" cellpadding="0" border="0" style="background:%s;">' % BG,
        '<tr><td align="center" style="padding:24px;">',
        '<table role="presentation" width="760" cellspacing="0" cellpadding="0" border="0" style="width:760px;max-width:760px;background:%s;border:1px solid %s;">' % (CARD, BORDER),
        '<tr><td style="background:%s;padding:24px 28px;color:#ffffff;border-bottom:4px solid %s;">' % (hero_bg, hero_accent),
        '<div style="font-size:12px;line-height:18px;letter-spacing:0.14em;text-transform:uppercase;opacity:0.88;">Built by <a href="https://firmade.ai" style="color:#ffffff;text-decoration:none;font-weight:700;">Firma de AI</a>, supported by <a href="https://firmade.it" style="color:#ffffff;text-decoration:none;font-weight:700;">Firma de IT</a>.</div>',
        '<table role="presentation" width="100%%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;margin-top:12px;">'
        '<tr><td style="font-size:0;line-height:0;height:3px;background:%s;">&nbsp;</td></tr>'
        '</table>' % hero_accent,
        '<div style="font-size:%dpx;line-height:42px;font-weight:bold;margin-top:12px;">GitHub Release Watch</div>' % H1,
        '<div style="font-size:20px;line-height:28px;font-weight:600;opacity:0.96;margin-top:8px;">%s</div>' % _esc(subject),
        '<div style="font-size:14px;line-height:22px;opacity:0.90;margin-top:10px;">%s</div>' % _esc(intro),
        '<div style="font-size:12px;line-height:18px;opacity:0.78;margin-top:10px;">Generated: %s</div>' % _esc(timestamp),
        '</td></tr>',
        '<tr><td style="padding:24px 28px;">',
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;margin-bottom:18px;">',
        '<tr>',
        _summary_card('Tracked repos', monitored, CARD, DARK),
        _summary_card('Updates', updates, updates_bg if updates or not failures else CARD, updates_fg if updates or not failures else DARK),
        _summary_card('Needs review', attention_count, WARN_BG if attention_count else CARD, WARN_TEXT if attention_count else DARK),
        '</tr></table>',
        _render_highlights(results),
        _render_categorized_table(results, categories) if categories else _render_table(results),
        _render_interesting_repos(interesting_repos),
        '<tr><td style="padding:0;">',
        '<div style="font-size:12px;line-height:18px;color:%s;">Next check: scheduled by cron.</div>' % MUTED,
        '</td></tr>',
        '</td></tr>',
        '<tr><td style="background:#eef2f7;padding:16px 28px;font-size:12px;line-height:18px;color:%s;border-top:3px solid %s;">'
        '<div style="margin:0;">Generated by <a href="https://github.com/asistent-alex/openclaw-github-release-watch" style="color:%s;text-decoration:none;font-weight:600;">GitHub Release Watch</a> · <a href="https://firmade.ai" style="color:%s;text-decoration:none;font-weight:600;">Firma de AI</a> · <a href="https://firmade.it" style="color:%s;text-decoration:none;font-weight:600;">Firma de IT</a></div>'
        '</td></tr>' % (MUTED, hero_accent, hero_accent, hero_accent, hero_accent),
        '</table></td></tr></table></body></html>',
    ]
    return ''.join(parts)


def main() -> int:
    try:
        data = _load_digest()
    except Exception:
        print('<p>Invalid digest</p>')
        return 1

    print(render_html(data))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
