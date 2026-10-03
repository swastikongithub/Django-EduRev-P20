"""
Moving an installation's business state from one database to another, once and deliberately: for
example a fully built local installation into production (`export_state`, then `import_state`).

What travels (SPECS, in dependency order): the catalogue, rules, timetable, upkeep, stock,
bookings with their slots, approvals, check-ins, no-shows and pauses, the Insights data, saved
resources and notifications. Every row keeps the state that produces what the portal shows; the
availability engine reads the same slots, rules and blackouts on both sides, so it computes the
same answers.

What never travels (EXCLUDED): sessions, the audit trail (the target keeps its own and gets one
entry describing the import), background-job runs, permissions and groups (the target's own), and
every credential of the source. People are exported without their password hashes, MFA secrets,
last sign-in, superuser or Django-staff flags, lockout state or calendar-feed tokens.

New credentials: given the usernames that already exist on the target, the export can generate a
fresh random password for every other account (`generate_credentials`), each different and each
passing AUTH_PASSWORD_VALIDATORS. The plaintext goes only to the operator (a file outside the
repository, written by `export_state --credentials`); the bundle carries only its Django hash. On
import a new account gets that hash, or an unusable password when the bundle has none, and no MFA
enrolment: privileged roles enrol TOTP at their first sign-in, exactly as for any new account. An
account whose username already exists on the target is never touched (no new password, no MFA
change); the bundle's records are attached to it instead. Both sides print `accounts_digest` of the
usernames involved, so the operator can confirm the credential file lists exactly the accounts the
import created without any password passing through a log.
Bookings get fresh QR-pass tokens (a token opens the pass, so a development one must not work).

How rows are matched, so that running the import again adds nothing:
* a natural key where the schema has one (codes, references, one-row-per-booking links), and
  then the target row is brought up to date with the bundle;
* otherwise the row's full contents after remapping (a fingerprint); a matching row is left alone.
New rows keep their source primary key whenever the target has not used it, so links that are not
foreign keys (slot sources) and anything derived from an id (which curated photo a resource shows)
come out the same. Where a key is taken, the database assigns one and every reference follows.

Nothing in here sends a notification or an email: rows are written with bulk inserts and queryset
updates, so no model signal or save() runs, and timestamps are kept as they were.
"""

from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.core import serializers
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.color import no_style
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

FORMAT = 1


@dataclass(frozen=True)
class Spec:
    label: str
    key: tuple[str, ...] | None = None  # natural key (attnames, after remapping); None = fingerprint
    exclude: tuple[str, ...] = ()  # not exported; rebuilt or regenerated on the target


USER_EXCLUDE = (
    "password",
    "last_login",
    "is_superuser",
    "is_staff",
    "groups",
    "user_permissions",
    "mfa_secret",
    "mfa_enabled",
    "mfa_last_step",
    "failed_logins",
    "locked_until",
    "calendar_token",
)

SPECS: list[Spec] = [
    Spec("accounts.Department", ("institution_id", "code")),
    Spec("accounts.User", ("username",), USER_EXCLUDE),
    Spec("catalogue.Building", ("institution_id", "code")),
    Spec("catalogue.ResourceType", ("institution_id", "code")),
    Spec("catalogue.Feature", ("institution_id", "name")),
    Spec("catalogue.Resource", ("institution_id", "code"), ("search_vector",)),
    Spec("catalogue.ResourceAttribute"),
    Spec("catalogue.ResourceImage"),
    Spec("catalogue.Custodian", ("resource_id", "user_id")),
    Spec("catalogue.SavedResource", ("user_id", "resource_id")),
    Spec("rules.BookingPolicy"),
    Spec("rules.AvailabilityRule"),
    Spec("rules.Blackout"),
    Spec("rules.Quota"),
    Spec("rules.RestrictionTier", ("institution_id", "no_shows")),
    Spec("timetable.AcademicTerm", ("institution_id", "code")),
    Spec("timetable.TimetablePublication", ("term_id", "version")),
    Spec("timetable.TimetableEntry"),
    Spec("maintenance.MaintenanceWindow"),
    Spec("bookings.BookingSeries"),
    Spec("bookings.Booking", ("reference",), ("qr_token",)),
    Spec("bookings.BookingSlot"),
    Spec("bookings.BookingAttempt"),
    Spec("approvals.ApprovalWorkflow"),
    Spec("approvals.ApprovalStep", ("workflow_id", "order")),
    Spec("approvals.Approval", ("booking_id", "step_order")),
    Spec("checkins.CheckIn", ("booking_id",)),
    Spec("checkins.NoShow", ("booking_id",)),
    Spec("checkins.Restriction"),
    Spec("maintenance.BreakdownReport"),
    Spec("inventory.InventoryItem", ("institution_id", "sku")),
    Spec("inventory.Issuance", ("booking_id", "item_id")),
    Spec("inventory.StockMovement"),
    Spec("analytics.UtilisationSnapshot", ("resource_id", "date")),
    Spec("notifications.Notification"),
]

EXCLUDED = {
    "sessions.Session": "sign-ins belong to the environment that issued them",
    "audit.AuditLog": "the target keeps its own trail; the import adds one entry describing itself",
    "core.SweepRun": "background-job runs describe the source's workers, not the target's",
    "auth.Group / auth.Permission": "created by migrations on every database; roles are re-applied",
    "core.Institution": "matched by code, never copied",
}

# Slots that block time for something other than a booking point at it by type and id.
SLOT_SOURCES = {"timetable_entry": "timetable.TimetableEntry", "maintenance_window": "maintenance.MaintenanceWindow"}

# Files referenced by these fields travel inside the bundle.
MEDIA_FIELDS = {"catalogue.Resource": "image", "catalogue.ResourceImage": "image"}


class TransferError(Exception):
    pass


def spec_models():
    return [(s, apps.get_model(s.label)) for s in SPECS]


def applied_migrations() -> list[str]:
    return sorted(f"{a}.{n}" for a, n in MigrationRecorder.Migration.objects.values_list("app", "name"))


# ── Export ──────────────────────────────────────────────────────────────────


def _fields(model, spec):
    names = [f.name for f in model._meta.concrete_fields if not f.primary_key and f.name not in spec.exclude]
    names += [f.name for f in model._meta.many_to_many if f.name not in spec.exclude]
    return names


TYPEABLE_CHARACTERS = (
    "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"  # gitleaks:allow - a character set; no 0/O, 1/l/I
)


def new_password(user) -> str:
    """A random password (about 66 bits) in typeable groups, checked against the project's validators."""
    import secrets

    from django.contrib.auth import password_validation
    from django.core.exceptions import ValidationError

    while True:
        groups = ["".join(secrets.choice(TYPEABLE_CHARACTERS) for _ in range(4)) for _ in range(3)]
        candidate = "-".join(groups) + secrets.choice("23456789")
        try:
            password_validation.validate_password(candidate, user)
        except ValidationError:  # pragma: no cover - vanishingly unlikely for random strings
            continue
        return candidate


def accounts_digest(usernames) -> str:
    return hashlib.sha256("\n".join(sorted(u.lower() for u in usernames)).encode()).hexdigest()[:16]


def generate_credentials(bundle: dict, *, existing_usernames, public_vids=()) -> list[dict]:
    """
    Give every bundle account that the target does not already have a fresh password: its hash goes
    into the bundle, the plaintext only into the returned list (for the operator's private file).
    Accounts the target already has get nothing, so the import maps them and never resets them.

    `public_vids` names a few Student accounts whose passwords are meant to be published (the
    README's demo accounts). They get passwords exactly like the rest and are marked `public`; only
    active Students qualify, so a published credential can never be a privileged one.
    """
    from apps.accounts.models import Role, User

    taken = {u.lower() for u in existing_usernames}
    public = {v.strip() for v in public_vids if v.strip()}
    rows = {r["fields"].get("vid"): r["fields"] for r in bundle["models"]["accounts.User"] if r["fields"].get("vid")}
    for vid in public:
        f = rows.get(vid)
        if f is None:
            raise TransferError(f"No account with VID {vid} in the bundle.")
        if f["role"] != Role.STUDENT or not f.get("is_active", True) or f["username"].lower() in taken:
            raise TransferError(
                f"VID {vid} is not a new, active Student account, so it cannot be a public demo account."
            )
    issued, seen = [], set()
    roles = dict(Role.choices)
    for row in bundle["models"]["accounts.User"]:
        f = row["fields"]
        if f["username"].lower() in taken:
            continue
        probe = User(username=f["username"], first_name=f["first_name"], last_name=f["last_name"], email=f["email"])
        password = new_password(probe)
        while password in seen:  # pragma: no cover - 66 bits
            password = new_password(probe)
        seen.add(password)
        f["password"] = make_password(password)
        issued.append(
            {
                "name": f"{f['first_name']} {f['last_name']}".strip() or f["username"],
                "username": f["username"],
                "role": roles.get(f["role"], f["role"]),
                "email": f["email"],
                "vid": f.get("vid") or "",
                "password": password,
                "public": (f.get("vid") or "") in public,
            }
        )
    bundle["credentials"] = {
        "generated_for": len(issued),
        "accounts_digest": accounts_digest(i["username"] for i in issued),
    }
    return issued


def credentials_markdown(issued: list[dict], *, site_url: str = "") -> str:
    from django.conf import settings

    mfa_roles = {r.replace("_", " ") for r in settings.MFA_REQUIRED_ROLES}

    def cell(v):
        return str(v).replace("|", "\\|")

    lines = [
        "# LPU Reserve Demo Accounts",
        "",
        "Private. Generated once for the accounts created in production by `import_state`. Keep this",
        "file out of every repository, upload and chat; give each evaluator only their own row.",
        f"Sign in at {site_url or 'the production site'} with the username (or VID) and password.",
        f"{', '.join(sorted(r.title() for r in mfa_roles))} accounts set up an authenticator app at their first sign-in.",
        "",
        "| Name | Username | Role | Email | VID | Password |",
        "|---|---|---|---|---|---|",
    ]
    for i in sorted(issued, key=lambda x: (x["role"], x["username"])):
        lines.append(
            f"| {cell(i['name'])} | {cell(i['username'])} | "
            f"{cell(i['role'] + (' (public demo, in README)' if i.get('public') else ''))} | {cell(i['email'])} | "
            f"{cell(i['vid'])} | `{i['password']}` |"
        )
    return "\n".join(lines) + "\n"


def public_demo_markdown(issued: list[dict]) -> str:
    """Only the deliberately public Student accounts: VID and password, nothing personal."""
    rows = [i for i in issued if i.get("public")]
    lines = ["| Student ID | Password |", "|---|---|"]
    lines += [f"| `{i['vid']}` | `{i['password']}` |" for i in sorted(rows, key=lambda x: x["vid"])]
    return "\n".join(lines) + "\n"


def export_bundle(*, institution_code: str) -> dict:
    """Everything SPECS lists for one institution, sanitised, plus the media its rows reference."""
    from apps.core.models import Institution

    inst = Institution.objects.filter(code=institution_code).first()
    if inst is None:
        raise TransferError(f"No institution with code {institution_code!r} here.")
    bundle = {
        "format": FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "institution": {"code": inst.code, "name": inst.name, "short_name": inst.short_name},
        "migrations": applied_migrations(),
        "excluded": EXCLUDED,
        "models": {},
        "media": {},
    }
    for spec, model in spec_models():
        qs = model._base_manager.order_by("pk")
        if any(f.name == "institution" for f in model._meta.concrete_fields):
            qs = qs.filter(institution=inst)
        rows = json.loads(serializers.serialize("json", qs, fields=_fields(model, spec)))
        bundle["models"][spec.label] = rows
        media_field = MEDIA_FIELDS.get(spec.label)
        if media_field:
            for row in rows:
                name = row["fields"].get(media_field)
                if name and name not in bundle["media"]:
                    bundle["media"][name] = _media_entry(name)
    return bundle


def _media_entry(name):
    if not default_storage.exists(name):
        return {"missing": True}
    with default_storage.open(name, "rb") as fh:
        data = fh.read()
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "b64": base64.b64encode(data).decode()}


def write_bundle(bundle: dict, path) -> None:
    raw = json.dumps(bundle, cls=DjangoJSONEncoder, sort_keys=True).encode()
    with open(path, "wb") as fh, gzip.GzipFile(filename="", mode="wb", fileobj=fh, mtime=0) as gz:
        gz.write(raw)


def read_bundle(path) -> dict:
    with gzip.open(path, "rb") as gz:
        bundle = json.loads(gz.read())
    if bundle.get("format") != FORMAT:
        raise TransferError(f"Unsupported bundle format {bundle.get('format')!r}.")
    return bundle


def bundle_summary(bundle: dict) -> dict:
    media = bundle["media"]
    return {
        "counts": {label: len(rows) for label, rows in bundle["models"].items()},
        "media_files": sum(1 for m in media.values() if not m.get("missing")),
        "media_bytes": sum(m.get("size", 0) for m in media.values()),
        "media_missing": sorted(n for n, m in media.items() if m.get("missing")),
    }


# ── Import ──────────────────────────────────────────────────────────────────


@dataclass
class Report:
    created: dict = field(default_factory=dict)
    matched: dict = field(default_factory=dict)
    updated: dict = field(default_factory=dict)
    kept_source_pk: dict = field(default_factory=dict)
    existing_users_kept: list = field(default_factory=list)
    created_usernames: list = field(default_factory=list)
    media_uploaded: int = 0
    media_present: int = 0
    media_bytes: int = 0
    media_missing: list = field(default_factory=list)

    def as_dict(self):
        return self.__dict__


@contextlib.contextmanager
def _keep_timestamps(models):
    """Bulk inserts would stamp auto_now/auto_now_add fields with now: keep the source's values."""
    saved = []
    for model in models:
        for f in model._meta.concrete_fields:
            if getattr(f, "auto_now", False) or getattr(f, "auto_now_add", False):
                saved.append((f, f.auto_now, f.auto_now_add))
                f.auto_now = f.auto_now_add = False
    try:
        yield
    finally:
        for f, now, add in saved:
            f.auto_now, f.auto_now_add = now, add


def _fingerprint(obj, model, spec):
    values = []
    for f in model._meta.concrete_fields:
        if f.primary_key or f.name in spec.exclude:
            continue
        v = f.value_to_string(obj)
        values.append(v if isinstance(v, str) or v is None else json.dumps(v, sort_keys=True, cls=DjangoJSONEncoder))
    return tuple(values)


def _reset_sequences(models):
    with connection.cursor() as cursor:
        for sql in connection.ops.sequence_reset_sql(no_style(), models):
            cursor.execute(sql)


class Importer:
    def __init__(self, bundle: dict, *, report: Report | None = None):
        self.bundle = bundle
        self.report = report or Report()
        self.maps: dict[str, dict[int, int]] = {}
        self.errors: list[str] = []
        self.created_users: list[int] = []

    # The whole import, in one transaction. `dry_run` rolls it back after every check has run.
    def run(self, *, dry_run: bool = False) -> Report:
        from apps.core.models import Institution

        mine, theirs = set(applied_migrations()), set(self.bundle["migrations"])
        if mine != theirs:
            raise TransferError(
                "The bundle and this database are at different migrations; migrate both to the same "
                f"release first. Only here: {sorted(mine - theirs)[:5]}; only in the bundle: {sorted(theirs - mine)[:5]}"
            )
        with transaction.atomic():
            info = self.bundle["institution"]
            inst, _ = Institution.objects.get_or_create(
                code=info["code"], defaults={"name": info["name"], "short_name": info.get("short_name", "")}
            )
            self.inst = inst
            self._media(dry_run)
            models = [m for _, m in spec_models()]
            with _keep_timestamps(models):
                for spec, model in spec_models():
                    self._import_model(spec, model)
            if self.errors:
                raise TransferError("Nothing was imported:\n" + "\n".join(self.errors[:20]))
            _reset_sequences(models)
            self._after()
            connection.check_constraints()  # deferred foreign keys, checked now rather than at commit
            if dry_run:
                transaction.set_rollback(True)
        return self.report

    def _media(self, dry_run):
        for name, entry in sorted(self.bundle["media"].items()):
            if entry.get("missing"):
                self.report.media_missing.append(name)
                continue
            data = base64.b64decode(entry["b64"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise TransferError(f"Media file {name} is corrupt in the bundle.")
            self.report.media_bytes += len(data)
            if default_storage.exists(name):
                with default_storage.open(name, "rb") as fh:
                    if hashlib.sha256(fh.read()).hexdigest() == entry["sha256"]:
                        self.report.media_present += 1
                        continue
                raise TransferError(f"{name} already exists on the target with different contents.")
            if not dry_run:
                saved = default_storage.save(name, ContentFile(data))
                if saved != name:  # pragma: no cover - exists() said it was free
                    raise TransferError(f"Storage saved {name} as {saved}.")
            self.report.media_uploaded += 1

    def _remap(self, obj, model, label):
        for f in model._meta.concrete_fields:
            if not f.is_relation:
                continue
            old = getattr(obj, f.attname)
            if old is None:
                continue
            target = f.related_model._meta.label
            if target == "core.Institution":
                setattr(obj, f.attname, self.inst.pk)
                continue
            mapping = self.maps.get(target)
            if mapping is None or old not in mapping:
                self.errors.append(f"{label} {obj.pk}: {f.name} points at {target} {old}, which is not in the bundle")
                continue
            setattr(obj, f.attname, mapping[old])
        if label == "bookings.BookingSlot" and obj.source_type in SLOT_SOURCES:
            mapping = self.maps.get(SLOT_SOURCES[obj.source_type], {})
            if obj.source_id not in mapping:
                self.errors.append(
                    f"BookingSlot {obj.pk}: source {obj.source_type} {obj.source_id} is not in the bundle"
                )
            else:
                obj.source_id = mapping[obj.source_id]

    def _import_model(self, spec, model):
        label = spec.label
        rows = self.bundle["models"].get(label, [])
        self.maps[label] = mapping = {}
        manager = model._base_manager
        objects = list(serializers.deserialize("json", json.dumps(rows), ignorenonexistent=True))
        existing_pks = set(manager.values_list("pk", flat=True))
        existing, pool, pool_by_pk = {}, defaultdict(list), {}
        if spec.key:
            existing = {tuple(r[:-1]): r[-1] for r in manager.values_list(*spec.key, "pk")}
            if label == "accounts.User":
                existing = {(k[0].lower(),): pk for k, pk in existing.items()}
        elif existing_pks:
            # Without a natural key, a row is matched by its full contents, each target row at
            # most once: identical source rows stay as many rows as they were.
            for o in manager.all():
                fp = _fingerprint(o, model, spec)
                pool[fp].append(o.pk)
                pool_by_pk[o.pk] = fp

        with_pk, without_pk, m2m, updates = [], [], [], []
        for d in objects:
            obj, src = d.object, d.object.pk
            self._remap(obj, model, label)
            if spec.key:
                ident = (
                    (obj.username.lower(),) if label == "accounts.User" else tuple(getattr(obj, a) for a in spec.key)
                )
                found = existing.get(ident)
            else:
                fp = _fingerprint(obj, model, spec)
                found = None
                if pool_by_pk.get(src) == fp and src in pool[fp]:
                    found = src
                elif pool.get(fp):
                    found = pool[fp][0]
                if found is not None:
                    pool[fp].remove(found)
            if found is not None:
                mapping[src] = found
                self.report.matched[label] = self.report.matched.get(label, 0) + 1
                if label == "accounts.User":
                    self.report.existing_users_kept.append(obj.username)
                elif spec.key:
                    updates.append((found, obj))
                    m2m.append((found, d.m2m_data))
                continue
            if label == "accounts.User":
                self._sanitise_user(obj)
            if label == "bookings.Booking":
                from apps.bookings.models import _qr_token

                obj.qr_token = _qr_token()
            if src in existing_pks:
                obj.pk = None
                without_pk.append((src, obj, d.m2m_data))
            else:
                existing_pks.add(src)
                with_pk.append((src, obj, d.m2m_data))

        if with_pk:
            manager.bulk_create([o for _, o, _ in with_pk], batch_size=500)
            for src, obj, data in with_pk:
                mapping[src] = obj.pk
                m2m.append((obj.pk, data))
            _reset_sequences([model])
        if without_pk:
            manager.bulk_create([o for _, o, _ in without_pk], batch_size=500)
            for src, obj, data in without_pk:
                mapping[src] = obj.pk
                m2m.append((obj.pk, data))
        for pk, obj in updates:
            fields = {
                f.attname: getattr(obj, f.attname)
                for f in model._meta.concrete_fields
                if not f.primary_key and f.name not in spec.exclude and f.attname not in spec.key
            }
            manager.filter(pk=pk).update(**fields)
        for pk, data in m2m:
            for name, ids in (data or {}).items():
                rel = model._meta.get_field(name)
                target_map = self.maps.get(rel.related_model._meta.label, {})
                getattr(manager.get(pk=pk), name).set([target_map[i] for i in ids if i in target_map])

        created = len(with_pk) + len(without_pk)
        self.report.created[label] = created
        self.report.kept_source_pk[label] = len(with_pk)
        self.report.updated[label] = len(updates)
        if label == "accounts.User":
            self.created_users = [mapping[s] for s, _, _ in with_pk + without_pk]
            self.report.created_usernames = sorted(o.username for _, o, _ in with_pk + without_pk)

    @staticmethod
    def _sanitise_user(user):
        from django.contrib.auth.hashers import identify_hasher

        # Keep only a hash generate_credentials made for this target; anything else is unusable.
        try:
            identify_hasher(user.password)
        except ValueError:
            user.password = make_password(None)
        user.is_superuser = user.is_staff = False
        user.mfa_secret, user.mfa_enabled, user.mfa_last_step = "", False, None
        user.failed_logins, user.locked_until, user.last_login = 0, None, None
        user.calendar_token = uuid.uuid4()

    def _after(self):
        from apps.accounts.models import User
        from apps.accounts.permissions import assign_role_group
        from apps.audit.models import AuditLog
        from apps.catalogue.models import Resource
        from apps.catalogue.search import refresh_search_vectors

        for user in User.objects.filter(pk__in=self.created_users):
            assign_role_group(user)
        refresh_search_vectors(Resource.objects.filter(pk__in=self.maps.get("catalogue.Resource", {}).values()))
        AuditLog.objects.create(
            institution=self.inst,
            actor=None,
            actor_label="system",
            action="data.import_state",
            target_type="core.institution",
            target_id=str(self.inst.pk),
            target_label="Imported installation state",
            after={
                "created": {k: v for k, v in self.report.created.items() if v},
                "matched": {k: v for k, v in self.report.matched.items() if v},
                "media_uploaded": self.report.media_uploaded,
                "bundle_created_at": self.bundle["created_at"],
            },
        )


def import_bundle(bundle: dict, *, dry_run: bool = False) -> Report:
    return Importer(bundle).run(dry_run=dry_run)


# ── Inventory and availability, for comparing two installations ─────────────


def inventory(*, institution_code: str, resource_codes=(), days=(), now=None) -> dict:
    """Counts of everything SPECS covers, and the computed availability of chosen resources."""
    from django.contrib.auth.models import AnonymousUser

    from apps.bookings import availability
    from apps.catalogue.models import Resource
    from apps.core.models import Institution

    inst = Institution.objects.filter(code=institution_code).first()
    counts = {}
    for spec, model in spec_models():
        qs = model._base_manager.all()
        if inst and any(f.name == "institution" for f in model._meta.concrete_fields):
            qs = qs.filter(institution=inst)
        counts[spec.label] = qs.count()
    media = 0
    for label, fname in MEDIA_FIELDS.items():
        media += (
            apps.get_model(label)._base_manager.exclude(**{fname: ""}).exclude(**{f"{fname}__isnull": True}).count()
        )
    out = {"counts": counts, "media_references": media, "availability": {}}
    viewer = AnonymousUser()
    for code in resource_codes:
        r = Resource.objects.filter(institution=inst, code=code).select_related("type").first()
        if r is None:
            out["availability"][code] = None
            continue
        sched = availability.schedule(r, list(days), viewer, now=now)
        out["availability"][code] = {
            d.day.isoformat(): [f"{c.start.astimezone(UTC):%H:%M}Z {c.state} {c.reason}" for c in d.cells]
            for d in sched
        }
    return out


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, cls=DjangoJSONEncoder).encode()).hexdigest()[:16]
