"""Staff console: the immutable audit log, filterable, with before/after diffs and CSV export."""

import csv
import json
from datetime import datetime, time, timedelta

from django.core.paginator import Paginator
from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.http import date_param
from apps.core.manage_views import staff_required

from .models import AuditLog

MAX_EXPORT = 50_000


def _parse_date(v):
    return date_param(v)


def filtered(request):
    g = request.GET
    f = {k: g.get(k, "").strip() for k in ("actor", "action", "target", "since", "until")}
    qs = AuditLog.objects.filter(institution_id=request.user.institution_id)
    if f["actor"]:
        qs = qs.filter(actor_label__icontains=f["actor"])
    if f["action"]:
        qs = qs.filter(action__startswith=f["action"])
    if f["target"]:
        qs = qs.filter(target_type=f["target"])
    tz = timezone.get_current_timezone()
    since, until = _parse_date(f["since"]), _parse_date(f["until"])
    if since:
        qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(since, time.min), tz))
    if until:
        qs = qs.filter(created_at__lt=timezone.make_aware(datetime.combine(until + timedelta(days=1), time.min), tz))
    return qs.order_by("-created_at", "-id"), f


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def diff(before, after):
    """[(field, before, after, changed)] across both snapshots; non-dict payloads become one 'value' row."""
    b = before if isinstance(before, dict) else ({} if before is None else {"value": before})
    a = after if isinstance(after, dict) else ({} if after is None else {"value": after})
    rows = []
    for k in list(dict.fromkeys([*b.keys(), *a.keys()])):
        bv, av = _fmt(b.get(k)), _fmt(a.get(k))
        rows.append(
            {
                "field": k.replace("_", " "),
                "before": bv,
                "after": av,
                "changed": (k in b and k in a and bv != av),
                "only": "after" if k not in b else "before" if k not in a else "",
            }
        )
    rows.sort(key=lambda r: not r["changed"])
    return rows


class _Echo:
    def write(self, value):
        return value


def _export(qs):
    writer = csv.writer(_Echo())

    def rows():
        yield writer.writerow(
            ["time", "actor", "action", "target_type", "target_id", "target", "ip", "before", "after"]
        )
        for e in qs[:MAX_EXPORT].iterator(chunk_size=2000):
            yield writer.writerow(
                [
                    timezone.localtime(e.created_at).isoformat(timespec="seconds"),
                    e.actor_label,
                    e.action,
                    e.target_type,
                    e.target_id,
                    e.target_label,
                    e.ip or "",
                    _fmt(e.before),
                    _fmt(e.after),
                ]
            )

    resp = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="audit-log-{timezone.localdate():%Y%m%d}.csv"'
    return resp


@staff_required("view_audit_log")
def audit(request):
    qs, f = filtered(request)
    if request.GET.get("format") == "csv":
        return _export(qs)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    for e in page:
        e.rows = diff(e.before, e.after)
        e.changed = sum(1 for r in e.rows if r["changed"])
    base = AuditLog.objects.filter(institution_id=request.user.institution_id)
    actions = sorted({a.split(".")[0] for a in base.order_by().values_list("action", flat=True).distinct()})
    params = request.GET.copy()
    params.pop("page", None)
    return render(
        request,
        "manage/audit.html",
        {
            "page": page,
            "filters": f,
            "filtered": any(f.values()),
            "action_prefixes": [a + "." for a in actions],
            "target_types": list(base.order_by("target_type").values_list("target_type", flat=True).distinct()),
            "querystring": params.urlencode(),
            "max_export": MAX_EXPORT,
        },
    )
