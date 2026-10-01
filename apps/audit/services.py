"""Audit interface for other modules: `record(...)`. Never raises into the caller's flow."""

import logging

from django.db import transaction
from django.forms.models import model_to_dict

from apps.core.http import client_ip

from .models import AuditLog

log = logging.getLogger(__name__)


def snapshot(instance, fields=None) -> dict:
    data = model_to_dict(instance, fields=fields)
    return {
        k: (str(v) if not isinstance(v, (int, float, bool, type(None), list, dict)) else v) for k, v in data.items()
    }


def record(actor, action: str, target, *, before=None, after=None, request=None, label: str | None = None):
    try:
        with transaction.atomic():
            return AuditLog.objects.create(
                institution_id=getattr(target, "institution_id", None) or getattr(actor, "institution_id", None) or 1,
                actor=actor if getattr(actor, "pk", None) else None,
                actor_label=str(actor) if actor else "system",
                action=action,
                target_type=target._meta.label_lower if hasattr(target, "_meta") else str(type(target).__name__),
                target_id=str(getattr(target, "pk", "")),
                target_label=(label or str(target))[:200],
                before=before,
                after=after,
                ip=client_ip(request),
            )
    except Exception:  # pragma: no cover - audit must never break the business flow
        log.exception("audit write failed for %s", action)
        return None
