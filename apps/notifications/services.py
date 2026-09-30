"""Notification interface: in-app inbox + email (sent by Celery after commit)."""

from django.db import transaction

from .models import Kind, Notification

TONES = {
    Kind.BOOKING_CONFIRMED: "success",
    Kind.APPROVED: "success",
    Kind.APPROVAL_REQUIRED: "warning",
    Kind.APPROVAL_PENDING: "info",
    Kind.REJECTED: "danger",
    Kind.REMINDER: "info",
    Kind.CHECKIN_OPEN: "warning",
    Kind.AUTO_RELEASED: "danger",
    Kind.RESTRICTED: "danger",
    Kind.MAINTENANCE: "warning",
    Kind.UNAVAILABLE: "danger",
    Kind.CANCELLED: "info",
    Kind.EXPIRED: "info",
    Kind.STOCK_LOW: "warning",
    Kind.BREAKDOWN: "danger",
    Kind.SERIES: "success",
}


def notify(user, kind, title, body="", url="", *, email=True):
    if user is None:
        return None
    n = Notification.objects.create(
        user=user, kind=kind, title=title[:160], body=body[:500], url=url, tone=TONES.get(kind, "info")
    )
    if email and user.email:
        from .tasks import send_notification_email

        transaction.on_commit(lambda: send_notification_email.delay(n.pk))
    return n


def notify_many(users, kind, title, body="", url="", *, email=True):
    seen = set()
    for u in users:
        if u and u.pk not in seen:
            seen.add(u.pk)
            notify(u, kind, title, body, url, email=email)


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_all_read(user):
    from django.utils import timezone

    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())
