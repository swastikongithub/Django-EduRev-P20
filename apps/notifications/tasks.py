from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.core.sweeps import run_sweep

from .models import Kind, Notification
from .services import notify


@shared_task(name="notifications.send_email", autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def send_notification_email(notification_id: int):
    n = Notification.objects.select_related("user").filter(pk=notification_id, emailed_at__isnull=True).first()
    if not n or not n.user.email:
        return False
    link = f"{settings.SITE_URL}{n.url}" if n.url.startswith("/") else n.url
    send_mail(f"[LPU Reserve] {n.title}", f"{n.body}\n\n{link}".strip(), None, [n.user.email], fail_silently=False)
    Notification.objects.filter(pk=n.pk).update(emailed_at=timezone.now())
    return True


def _reminders(now=None, lead_minutes=30):
    from apps.bookings.models import Booking, BookingStatus

    now = now or timezone.now()
    sent = 0
    with transaction.atomic():
        due = (
            Booking.objects.select_for_update(skip_locked=True)
            .filter(
                status=BookingStatus.APPROVED,
                reminder_sent_at__isnull=True,
                period__startswith__gt=now,
                period__startswith__lte=now + timedelta(minutes=lead_minutes),
            )
            .select_related("resource")
        )
        for b in due:
            start = timezone.localtime(b.start)
            extra = (
                f" Check in by {timezone.localtime(b.checkin_deadline):%H:%M} or it's released."
                if b.requires_checkin
                else ""
            )
            notify(
                b.booked_for,
                Kind.REMINDER,
                f"Starts {start:%H:%M} · {b.resource.name}",
                f"{b.resource.location_label}.{extra}",
                b.get_absolute_url(),
            )
            b.reminder_sent_at = now
            b.save(update_fields=["reminder_sent_at"])
            sent += 1
    return sent


def _checkin_nudges(now=None):
    """'Check-in required' with the grace countdown, once the booking has started."""
    from apps.bookings.models import Booking, BookingStatus

    now = now or timezone.now()
    sent = 0
    with transaction.atomic():
        due = (
            Booking.objects.select_for_update(skip_locked=True)
            .filter(
                status=BookingStatus.APPROVED,
                requires_checkin=True,
                checkin_nudge_sent_at__isnull=True,
                period__startswith__lte=now,
            )
            .select_related("resource")
        )
        for b in due:
            if b.checkin_deadline <= now:
                continue
            mins = max(1, int((b.checkin_deadline - now).total_seconds() // 60))
            notify(
                b.booked_for,
                Kind.CHECKIN_OPEN,
                f"Check in now · {mins} min left",
                f"Scan the QR at {b.resource.name} or tap Check in, or the slot is released at "
                f"{timezone.localtime(b.checkin_deadline):%H:%M}.",
                b.get_absolute_url(),
                email=False,
            )
            b.checkin_nudge_sent_at = now
            b.save(update_fields=["checkin_nudge_sent_at"])
            sent += 1
    return sent


@shared_task(name="notifications.send_reminders")
def send_reminders():
    return run_sweep("notifications.send_reminders", _reminders)


@shared_task(name="notifications.send_checkin_nudges")
def send_checkin_nudges():
    return run_sweep("notifications.send_checkin_nudges", _checkin_nudges)
