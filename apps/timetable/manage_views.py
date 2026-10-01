"""Staff console: upload, check, stage and publish the term timetable (a hard availability constraint)."""

from datetime import date

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.audit.services import record
from apps.catalogue.manage_forms import read_csv_upload
from apps.core.errors import DomainError
from apps.core.manage_views import staff_required

from .models import AcademicTerm, PublicationStatus, TimetablePublication
from .services import COLUMNS, displacement_preview, export_csv, parse_rows, preview_rows, publish, stage

SAMPLE = (
    ",".join(COLUMNS) + "\n"
    "34-301,Mon,09:00,10:00,CSE326,Internet Programming Lab,K23KF,Dr. A. Sharma,Lecture\n"
    "34-301,Mon,10:00,11:00,CSE310,Programming in Java,K23KG,Dr. R. Kaur,Lecture\n"
    "38-LAB1,Wed,14:00,16:00,ECE249,Basic Electrical Lab,K23EP,Prof. V. Singh,Practical\n"
)
MAX_PASTE = 1024 * 1024


def _terms(inst):
    pubs = TimetablePublication.objects.select_related("published_by").order_by("-version")
    terms = list(
        AcademicTerm.objects.filter(institution_id=inst).prefetch_related(Prefetch("publications", queryset=pubs))
    )
    for t in terms:
        allp = list(t.publications.all())
        t.current = next((p for p in allp if p.status == PublicationStatus.PUBLISHED), None)
        t.drafts = [p for p in allp if p.status == PublicationStatus.DRAFT]
        t.history = allp
    return terms


def _csv(text, filename):
    resp = HttpResponse(text, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@staff_required("manage_timetable")
@require_http_methods(["GET", "POST"])
def timetable(request):
    inst = request.user.institution_id
    if request.GET.get("sample"):
        return _csv(SAMPLE, "lpu-reserve-timetable-template.csv")
    if request.GET.get("download", "").isdigit():
        pub = get_object_or_404(TimetablePublication, institution_id=inst, pk=request.GET["download"])
        return _csv(export_csv(pub), f"timetable-{pub.term.code}-v{pub.version}.csv")

    ctx = {"check": None}
    if request.method == "POST":
        action = request.POST.get("action")
        handler = {"check": _check, "stage": _stage, "publish": _publish, "discard": _discard, "term": _add_term}.get(
            action
        )
        if not handler:
            return HttpResponseBadRequest("Unknown action")
        result = handler(request)
        if not isinstance(result, dict):
            return result
        ctx.update(result)

    terms = _terms(inst)
    draft_id = request.GET.get("draft")
    draft = None
    if draft_id and draft_id.isdigit():
        draft = (
            TimetablePublication.objects.filter(institution_id=inst, pk=draft_id, status=PublicationStatus.DRAFT)
            .select_related("term")
            .first()
        )
    if draft is None and not ctx.get("check"):
        draft = (
            TimetablePublication.objects.filter(institution_id=inst, status=PublicationStatus.DRAFT)
            .select_related("term")
            .order_by("-created_at")
            .first()
        )
    if draft:
        ctx["draft"] = draft
        ctx["impact"] = displacement_preview(draft)
        ctx["draft_current"] = next((t.current for t in terms if t.pk == draft.term_id), None)
    published = request.GET.get("published")
    if published and published.isdigit():
        ctx["published"] = (
            TimetablePublication.objects.filter(institution_id=inst, pk=published).select_related("term").first()
        )
    ctx.update({"terms": terms, "columns": COLUMNS, "today": date.today()})
    return render(request, "manage/timetable.html", ctx)


def _read_source(request) -> str:
    upload = request.FILES.get("file")
    if upload:
        return read_csv_upload(upload)
    text = request.POST.get("csv_text", "")
    if not text.strip():
        raise ValidationError("Choose a CSV file, or paste the rows, to check.")
    if len(text) > MAX_PASTE:
        raise ValidationError("That's more than 1 MB of text. Upload it as a file in two parts instead.")
    return text


def _term(request):
    return AcademicTerm.objects.filter(
        institution_id=request.user.institution_id, pk=request.POST.get("term") or 0
    ).first()


def _check(request):
    term = _term(request)
    try:
        text = _read_source(request)
    except ValidationError as exc:
        return {"upload_error": exc.messages[0], "selected_term": term}
    if not term:
        return {"upload_error": "Choose which term this timetable is for.", "csv_text": text}
    preview = preview_rows(text, request.user.institution_id)
    entries, errors = parse_rows(text, request.user.institution_id) if not preview["missing"] else ([], [])
    bad = [r for r in preview["rows"] if r["errors"]]
    return {
        "check": {
            "term": term,
            "text": text,
            "rows": preview["rows"],
            "missing": preview["missing"],
            "bad": len(bad),
            "errors": errors,
            "ok": not errors and not preview["missing"] and bool(entries),
            "entries": len(entries),
            "rooms": len({e.resource_id for e in entries}),
        },
        "selected_term": term,
    }


def _stage(request):
    term = _term(request)
    text = request.POST.get("csv_text", "")
    if not term or not text.strip():
        return {"upload_error": "The file went missing between checking and saving. Check it again."}
    entries, errors = parse_rows(text, request.user.institution_id)
    if errors or not entries:
        result = _check(request)
        result["upload_error"] = "Something changed since the check (perhaps a room was renamed). Fix the rows below."
        return result
    pub = stage(term, entries, source="csv", actor=request.user, notes=f"Uploaded by {request.user.display_name}")
    record(
        request.user,
        "timetable.stage",
        pub,
        after={"version": pub.version, "entries": len(entries)},
        request=request,
        label=f"{term.code} v{pub.version} (draft)",
    )
    messages.success(
        request,
        f"Saved as draft v{pub.version} with {len(entries)} classes. Nothing changes for "
        "bookings until you publish it.",
    )
    return redirect(f"{reverse('manage:timetable')}?draft={pub.pk}#draft")


def _publish(request):
    pub = get_object_or_404(
        TimetablePublication.objects.select_related("term"),
        institution_id=request.user.institution_id,
        pk=request.POST.get("pub"),
    )
    try:
        result = publish(pub, request.user, request=request)
    except DomainError as exc:
        messages.error(request, exc.message)
        return redirect(f"{reverse('manage:timetable')}?draft={pub.pk}#draft")
    occ, disp, sup = result["occurrences"], result["displaced"], result["superseded"]
    msg = f"{pub.term.name} v{pub.version} is live: {occ:,} class sessions now block their rooms."
    if disp:
        msg += f" {disp} booking{'s were' if disp != 1 else ' was'} cancelled and the owners told, with alternatives."
    if sup:
        msg += " The previous version was retired in the same step."
    messages.success(request, msg)
    return redirect(f"{reverse('manage:timetable')}?published={pub.pk}")


def _discard(request):
    pub = get_object_or_404(
        TimetablePublication,
        institution_id=request.user.institution_id,
        pk=request.POST.get("pub"),
        status=PublicationStatus.DRAFT,
    )
    record(
        request.user,
        "timetable.discard",
        pub,
        before={"version": pub.version, "entries": pub.entry_count},
        request=request,
        label=f"{pub.term.code} v{pub.version} (draft)",
    )
    pub.delete()
    messages.success(request, "Draft discarded. The published timetable is unchanged.")
    return redirect("manage:timetable")


def _add_term(request):
    p = request.POST
    code, name = p.get("code", "").strip(), p.get("name", "").strip()
    try:
        starts, ends = date.fromisoformat(p.get("starts", "")), date.fromisoformat(p.get("ends", ""))
    except ValueError:
        return {"term_error": "Enter both dates."}
    if not code or not name:
        return {"term_error": "Give the term a code (as in UMS, e.g. 26271) and a name."}
    if starts >= ends:
        return {"term_error": "The term must end after it starts."}
    if AcademicTerm.objects.filter(institution_id=request.user.institution_id, code=code).exists():
        return {"term_error": f"Term {code} already exists."}
    term = AcademicTerm.objects.create(
        institution_id=request.user.institution_id, code=code[:16], name=name[:80], starts=starts, ends=ends
    )
    record(
        request.user,
        "timetable.term_create",
        term,
        after={"code": code, "starts": str(starts), "ends": str(ends)},
        request=request,
    )
    messages.success(request, f"{term.name} added. Upload its timetable next.")
    return redirect("manage:timetable")
