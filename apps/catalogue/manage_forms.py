"""
Resource console: scope helpers, the edit form, safe photo handling and CSV bulk import.

Views stay thin; every rule a facility manager meets on these screens lives here and
answers in a sentence they can act on.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.accounts.models import Department, Role, User
from apps.accounts.permissions import can_manage_resource, has_cap, is_campus_wide
from apps.audit.services import record, snapshot

from .models import Building, Custodian, Feature, Resource, ResourceAttribute, ResourceStatus, ResourceType
from .search import refresh_search_vectors

# ── Scope ───────────────────────────────────────────────────────────────────


def manageable_resources(user):
    """Resources this person may see in the console: campus-wide roles see all, others their own."""
    qs = Resource.objects.filter(institution_id=user.institution_id)
    if is_campus_wide(user):
        return qs
    if user.role == Role.CUSTODIAN:
        return qs.filter(custodians__user=user)
    if user.role == Role.DEPT_HEAD and user.department_id:
        return qs.filter(department_id=user.department_id)
    return qs.none()


def can_edit_resource(user, resource) -> bool:
    return has_cap(user, "manage_resources") and can_manage_resource(user, resource)


def can_create_resources(user) -> bool:
    return has_cap(user, "manage_resources") and is_campus_wide(user)


# ── Styling ─────────────────────────────────────────────────────────────────


class StyledFormMixin:
    """Design-system classes on widgets, and aria-invalid on fields with errors."""

    def style(self):
        for name, f in self.fields.items():
            w = f.widget
            if isinstance(w, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect, forms.FileInput)):
                continue
            cls = "select" if isinstance(w, forms.Select) else "textarea" if isinstance(w, forms.Textarea) else "input"
            w.attrs.setdefault("class", cls)
            if self.is_bound and name in self.errors:
                w.attrs["aria-invalid"] = "true"
                w.attrs["aria-describedby"] = f"{self.auto_id % name}-err" if self.auto_id else ""
        return self

    def full_clean(self):
        super().full_clean()
        self.style()


# ── Photos ──────────────────────────────────────────────────────────────────

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/pjpeg"}
MAX_IMAGE_SIDE = 1600
MAX_PIXELS = 40_000_000


def sniff_image(head: bytes) -> str | None:
    """Identify JPEG / PNG / WebP from their magic bytes (never trust the filename or browser type)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    return None


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f}".rstrip("0").rstrip(".")


def clean_image(upload) -> ContentFile:
    """
    Validate an uploaded photo and re-encode it.

    Size cap, declared MIME type, magic bytes, Pillow verify(), a decoded-format check and a
    pixel cap (decompression bombs). The output is a fresh WebP (max 1600 px) with no EXIF,
    GPS or ICC metadata, so nothing from the original file is served back.
    """
    limit = settings.MAX_IMAGE_UPLOAD_BYTES
    if upload.size > limit:
        raise ValidationError(f"That photo is {_mb(upload.size)} MB. Photos can be up to {_mb(limit)} MB.")
    declared = (getattr(upload, "content_type", "") or "").lower()
    if declared and declared not in ALLOWED_IMAGE_TYPES:
        raise ValidationError("Upload a JPEG, PNG or WebP photo. Other file types aren't accepted.")
    upload.seek(0)
    fmt = sniff_image(upload.read(16))
    upload.seek(0)
    if fmt is None:
        raise ValidationError("That file isn't a JPEG, PNG or WebP photo, whatever its name says.")
    try:
        with Image.open(upload) as probe:
            probe.verify()
        upload.seek(0)
        img = Image.open(upload)
        if img.format not in ALLOWED_IMAGE_FORMATS or img.format != fmt:
            raise ValidationError("Upload a JPEG, PNG or WebP photo. Other file types aren't accepted.")
        if img.width * img.height > MAX_PIXELS:
            raise ValidationError("That photo is too large to process. Resize it below 40 megapixels and try again.")
        img.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValidationError("That photo couldn't be read. It may be damaged; export it again and retry.")
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:  # noqa: BLE001,S110 - a broken orientation tag is not worth refusing the photo
        pass
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA" if has_alpha else "RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    img.save(out, "WEBP", quality=82, method=4)  # no exif=/icc_profile= passed: metadata is dropped
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex[:16]}.webp")


# ── Edit form ───────────────────────────────────────────────────────────────

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,31}$")
MAX_ATTRIBUTES = 30


class ResourceForm(StyledFormMixin, forms.ModelForm):
    photo = forms.FileField(
        required=False, widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})
    )
    remove_photo = forms.BooleanField(required=False)
    custodians = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Resource
        fields = [
            "name",
            "code",
            "type",
            "tagline",
            "description",
            "capacity",
            "building",
            "floor",
            "room",
            "department",
            "features",
            "status",
            "status_note",
            "is_bookable",
            "acquisition_cost",
        ]
        widgets = {
            "features": forms.CheckboxSelectMultiple,
            "status": forms.RadioSelect,
            "description": forms.Textarea(attrs={"rows": 4}),
            "capacity": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
            "acquisition_cost": forms.NumberInput(attrs={"min": 0, "step": "1", "inputmode": "decimal"}),
        }
        labels = {
            "is_bookable": "Bookable online",
            "status_note": "Why, and until when?",
            "acquisition_cost": "Acquisition cost (₹)",
            "type": "Type",
            "building": "Block",
        }
        help_texts = {
            "code": "The code on the door, e.g. 34-301. It also forms the door QR link.",
            "tagline": "One line people see in search results.",
            "capacity": "People for rooms and courts, units for equipment.",
            "acquisition_cost": "Used for cost-per-hour in insights. Optional.",
        }
        error_messages = {
            "name": {"required": "Give the resource a name people will recognise."},
            "code": {"required": "Add the resource code, e.g. 34-301."},
            "type": {"required": "Choose what type of resource this is."},
            "capacity": {
                "required": "Say how many people (or units) it holds.",
                "min_value": "Capacity must be at least 1.",
            },
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        inst = user.institution_id
        self.fields["type"].queryset = ResourceType.objects.filter(institution_id=inst)
        self.fields["building"].queryset = Building.objects.filter(institution_id=inst)
        self.fields["department"].queryset = Department.objects.filter(institution_id=inst)
        self.fields["features"].queryset = Feature.objects.filter(institution_id=inst)
        self.fields["building"].empty_label = "No block (campus-wide or mobile)"
        self.fields["department"].empty_label = "No owning department"
        self.campus_wide = is_campus_wide(user)
        if self.campus_wide:
            self.fields["custodians"].queryset = (
                User.objects.filter(institution_id=inst, is_active=True)
                .exclude(role__in=[Role.STUDENT, Role.FACULTY, Role.STAFF])
                .order_by("first_name", "last_name")
            )
            current = set(self.instance.custodians.values_list("user_id", flat=True)) if self.instance.pk else set()
            if current:  # keep anyone already assigned visible, whatever their role now
                self.fields["custodians"].queryset = User.objects.filter(
                    Q(pk__in=self.fields["custodians"].queryset.values("pk")) | Q(pk__in=current)
                ).order_by("first_name", "last_name")
            self.fields["custodians"].label_from_instance = lambda u: (
                f"{u.display_name}, {u.get_role_display().lower()}"
            )
            if self.instance.pk and not self.is_bound:
                self.initial["custodians"] = list(self.instance.custodians.values_list("user_id", flat=True))
        else:
            # Custodians run their resources day to day; identity and ownership stay with facilities.
            del self.fields["custodians"]
            for name in ("code", "type", "department"):
                self.fields[name].disabled = True
                self.fields[name].help_text = "Only facility managers can change this."
        self.style()

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not CODE_RE.match(code):
            raise ValidationError("Use letters, numbers, dashes, dots or slashes in the code, e.g. 34-301.")
        clash = Resource.objects.filter(institution_id=self.user.institution_id, code__iexact=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(f"Another resource already uses the code {code}.")
        return code

    def clean_photo(self):
        upload = self.cleaned_data.get("photo")
        if not upload:
            return None
        return clean_image(upload)

    def clean(self):
        data = super().clean()
        if (
            data.get("status")
            and data["status"] != ResourceStatus.ACTIVE
            and not (data.get("status_note") or "").strip()
        ):
            self.add_error("status_note", "Say why it's unavailable so people know when to expect it back.")
        cost = data.get("acquisition_cost")
        if cost is not None and cost < 0:
            self.add_error("acquisition_cost", "The cost can't be negative.")
        return data


def parse_attributes(post) -> tuple[list[tuple[str, str]], list[str]]:
    """Key/value rows from the inline editor (attr_key / attr_value lists). Blank rows are ignored."""
    keys, values = post.getlist("attr_key"), post.getlist("attr_value")
    rows, errors = [], []
    for i, (k, v) in enumerate(zip(keys, values, strict=False), start=1):
        k, v = k.strip(), v.strip()
        if not k and not v:
            continue
        if not k or not v:
            errors.append(f"Detail row {i} needs both a name and a value.")
            continue
        if len(k) > 60 or len(v) > 200:
            errors.append(f"Detail row {i} is too long: keep names under 60 characters and values under 200.")
            continue
        rows.append((k, v))
    if len(rows) > MAX_ATTRIBUTES:
        errors.append(f"Keep it to {MAX_ATTRIBUTES} details or fewer.")
    return rows, errors


def resource_snapshot(r: Resource) -> dict:
    data = snapshot(
        r,
        fields=[
            "name",
            "code",
            "type",
            "tagline",
            "description",
            "capacity",
            "building",
            "floor",
            "room",
            "department",
            "status",
            "status_note",
            "is_bookable",
            "acquisition_cost",
        ],
    )
    data["features"] = sorted(f.name for f in r.features.all())
    data["custodians"] = sorted(c.user.username for c in r.custodians.select_related("user"))
    data["attributes"] = [f"{a.key}: {a.value}" for a in r.attributes.all()]
    data["image"] = r.image.name if r.image else ""
    return data


def save_resource(form: ResourceForm, attributes, *, actor, request=None) -> Resource:
    """Persist the form, photo, details and custodians as one change, audited before/after."""
    creating = form.instance.pk is None
    before = None if creating else resource_snapshot(Resource.objects.get(pk=form.instance.pk))
    with transaction.atomic():
        resource = form.save(commit=False)
        if creating:
            resource.institution_id = actor.institution_id
        photo = form.cleaned_data.get("photo")
        if photo:
            resource.image.save(photo.name, photo, save=False)
        elif form.cleaned_data.get("remove_photo"):
            resource.image = ""
        resource.save()
        form.save_m2m()
        ResourceAttribute.objects.filter(resource=resource).delete()
        ResourceAttribute.objects.bulk_create(
            [ResourceAttribute(resource=resource, key=k, value=v, sort_order=i) for i, (k, v) in enumerate(attributes)]
        )
        if "custodians" in form.fields:
            wanted = {u.pk for u in form.cleaned_data.get("custodians") or []}
            Custodian.objects.filter(resource=resource).exclude(user_id__in=wanted).delete()
            have = set(Custodian.objects.filter(resource=resource).values_list("user_id", flat=True))
            Custodian.objects.bulk_create([Custodian(resource=resource, user_id=uid) for uid in wanted - have])
        refresh_search_vectors(Resource.objects.filter(pk=resource.pk))
        after = resource_snapshot(resource)
        record(
            actor,
            "resource.create" if creating else "resource.update",
            resource,
            before=before,
            after=after,
            request=request,
        )
    return resource


# ── CSV bulk import ─────────────────────────────────────────────────────────

IMPORT_COLUMNS = [
    "code",
    "name",
    "type_code",
    "building_code",
    "capacity",
    "floor",
    "room",
    "department_code",
    "features",
    "description",
]
IMPORT_REQUIRED = ["code", "name", "type_code", "capacity"]
MAX_IMPORT_BYTES = 1024 * 1024
MAX_IMPORT_ROWS = 1000
CSV_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "application/vnd.ms-excel",
    "text/x-csv",
    "application/octet-stream",
    "",
}

SAMPLE_CSV = (
    ",".join(IMPORT_COLUMNS) + "\n"
    "34-305,Room 34-305,classroom,34,60,3,305,CSE,Projector;Whiteboard,Ground-facing classroom with a projector\n"
    "38-LAB2,Electronics Lab 2,electronics-lab,38,30,2,212,ECE,Lab bench power,Oscilloscopes at every bench\n"
)


def read_csv_upload(upload) -> str:
    """Size cap, declared type and a text sniff (no NUL bytes, valid UTF-8). Returns the text."""
    if upload is None:
        raise ValidationError("Choose a CSV file to check.")
    if not upload.name.lower().endswith((".csv", ".txt")):
        raise ValidationError("Upload a .csv file. Save spreadsheets as 'CSV UTF-8' first.")
    if upload.size > MAX_IMPORT_BYTES:
        raise ValidationError(f"That file is {_mb(upload.size)} MB. Import files can be up to 1 MB; split it in two.")
    if (getattr(upload, "content_type", "") or "").lower() not in CSV_TYPES:
        raise ValidationError("That file doesn't look like a CSV. Save the sheet as 'CSV UTF-8' and try again.")
    raw = upload.read()
    if b"\x00" in raw[:4096] or raw[:4] in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0"):
        raise ValidationError("That's a spreadsheet file, not a CSV. In Excel use Save As, then 'CSV UTF-8'.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("The file isn't UTF-8 text. In Excel use Save As, then 'CSV UTF-8'.")


@dataclass
class ImportRow:
    line: int
    data: dict
    errors: list[str] = field(default_factory=list)
    type: ResourceType | None = None
    building: Building | None = None
    department: Department | None = None
    features: list[Feature] = field(default_factory=list)
    capacity: int | None = None

    @property
    def ok(self):
        return not self.errors


@dataclass
class ImportPreview:
    rows: list[ImportRow]
    problems: list[str]

    @property
    def bad_rows(self):
        return [r for r in self.rows if not r.ok]

    @property
    def ok(self):
        return bool(self.rows) and not self.problems and not self.bad_rows


def parse_import(text: str, institution_id: int) -> ImportPreview:
    """Validate every row against the catalogue. Nothing is written here."""
    reader = csv.DictReader(io.StringIO(text.strip()))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    reader.fieldnames = header
    missing = [c for c in IMPORT_REQUIRED if c not in header]
    if missing:
        return ImportPreview(
            [],
            [
                f"The file is missing the column{'s' if len(missing) > 1 else ''} "
                f"{', '.join(missing)}. The first row must name the columns: {', '.join(IMPORT_COLUMNS)}."
            ],
        )
    raw_rows = list(reader)
    if not raw_rows:
        return ImportPreview([], ["The file has a header row but no resources under it."])
    if len(raw_rows) > MAX_IMPORT_ROWS:
        return ImportPreview([], [f"The file has {len(raw_rows)} rows. Import up to {MAX_IMPORT_ROWS} at a time."])

    types = {t.code.lower(): t for t in ResourceType.objects.filter(institution_id=institution_id)}
    buildings = {b.code.lower(): b for b in Building.objects.filter(institution_id=institution_id)}
    depts = {d.code.lower(): d for d in Department.objects.filter(institution_id=institution_id)}
    feats = {f.name.lower(): f for f in Feature.objects.filter(institution_id=institution_id)}
    existing = Resource.objects.filter(institution_id=institution_id)
    taken_codes = {c.lower() for c in existing.values_list("code", flat=True)}
    taken_slugs = set(existing.values_list("slug", flat=True))
    seen_codes, seen_slugs = {}, set()

    rows = []
    for n, raw in enumerate(raw_rows, start=2):
        data = {c: (raw.get(c) or "").strip() for c in IMPORT_COLUMNS}
        row = ImportRow(line=n, data=data)
        code = data["code"]
        if not code:
            row.errors.append("Code is empty.")
        elif not CODE_RE.match(code):
            row.errors.append(f"Code '{code}' has characters other than letters, numbers, dashes, dots or slashes.")
        elif code.lower() in taken_codes:
            row.errors.append(f"{code} already exists in the catalogue.")
        elif code.lower() in seen_codes:
            row.errors.append(f"{code} also appears on row {seen_codes[code.lower()]}.")
        else:
            seen_codes[code.lower()] = n
        if not data["name"]:
            row.errors.append("Name is empty.")
        elif len(data["name"]) > 140:
            row.errors.append("Name is longer than 140 characters.")
        if code and data["name"]:
            slug = slugify(f"{code}-{data['name']}")[:80]
            if slug in taken_slugs or slug in seen_slugs:
                row.errors.append("Code and name together match an existing resource's web address; change the name.")
            seen_slugs.add(slug)
        row.type = types.get(data["type_code"].lower())
        if not row.type:
            row.errors.append(
                f"Type '{data['type_code']}' doesn't exist. Use one of: {', '.join(sorted(types))}."
                if data["type_code"]
                else "Type code is empty."
            )
        if data["building_code"]:
            row.building = buildings.get(data["building_code"].lower())
            if not row.building:
                row.errors.append(f"Block '{data['building_code']}' doesn't exist.")
        if data["department_code"]:
            row.department = depts.get(data["department_code"].lower())
            if not row.department:
                row.errors.append(f"Department '{data['department_code']}' doesn't exist.")
        try:
            row.capacity = int(data["capacity"])
            if row.capacity < 1:
                raise ValueError
        except ValueError:
            row.errors.append(f"Capacity '{data['capacity']}' must be a whole number of 1 or more.")
        for name in [x.strip() for x in data["features"].split(";") if x.strip()]:
            f = feats.get(name.lower())
            if f:
                row.features.append(f)
            else:
                row.errors.append(f"Feature '{name}' isn't in the feature list.")
        if len(data["floor"]) > 16 or len(data["room"]) > 24:
            row.errors.append("Floor or room is too long (16 and 24 characters at most).")
        rows.append(row)
    return ImportPreview(rows, [])


def commit_import(preview: ImportPreview, *, actor, request=None) -> list[Resource]:
    """All or nothing: every row is created in one transaction, each one audited."""
    if not preview.ok:
        raise ValidationError("Fix the highlighted rows first; nothing was imported.")
    created = []
    with transaction.atomic():
        for row in preview.rows:
            d = row.data
            r = Resource.objects.create(
                institution_id=actor.institution_id,
                code=d["code"],
                name=d["name"],
                type=row.type,
                building=row.building,
                department=row.department,
                capacity=row.capacity,
                floor=d["floor"],
                room=d["room"],
                description=d["description"],
            )
            if row.features:
                r.features.set(row.features)
            created.append(r)
        refresh_search_vectors(Resource.objects.filter(pk__in=[r.pk for r in created]))
        for r in created:
            record(actor, "resource.import", r, after=resource_snapshot(r), request=request)
    return created
