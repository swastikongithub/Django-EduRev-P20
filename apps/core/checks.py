"""
Deployment checks (run with `manage.py check --deploy`, which CI and the Railway pre-deploy
command both run). They catch configurations that work on a laptop but lose data or silently
fail in production. Development (DEBUG=1) and one-click demo stacks (DEMO_MODE=1) are exempt.
"""

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

NON_DELIVERING_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
}
ANYMAIL_KEYS = {
    "anymail.backends.resend.EmailBackend": ["RESEND_API_KEY"],
    "anymail.backends.postmark.EmailBackend": ["POSTMARK_SERVER_TOKEN"],
    "anymail.backends.sendgrid.EmailBackend": ["SENDGRID_API_KEY"],
    "anymail.backends.mailgun.EmailBackend": ["MAILGUN_API_KEY", "MAILGUN_SENDER_DOMAIN"],
}


def _production() -> bool:
    return not settings.DEBUG and not settings.DEMO_MODE


@register(Tags.security, deploy=True)
def production_configuration(app_configs=None, **kwargs):
    if not _production():
        return []
    problems = []
    if not settings.USE_S3:
        problems.append(
            Error(
                "Uploaded photos would be written to the container's filesystem, which is lost on every redeploy.",
                hint="Set USE_S3=1 and the S3_* variables (docs/deployment-railway.md#object-storage).",
                id="lpu.E001",
            )
        )
    elif not getattr(settings, "STORAGES", {}).get("default", {}).get("OPTIONS", {}).get("bucket_name"):
        problems.append(Error("USE_S3=1 but S3_BUCKET is empty.", id="lpu.E003"))
    if settings.EMAIL_BACKEND in NON_DELIVERING_BACKENDS:
        problems.append(
            Error(
                f"EMAIL_BACKEND is {settings.EMAIL_BACKEND}, which does not deliver mail; booking "
                "confirmations, approval requests and reminders would never arrive.",
                hint="Use an HTTPS email API (anymail) or SMTP (docs/deployment-railway.md#email).",
                id="lpu.E002",
            )
        )
    for key in ANYMAIL_KEYS.get(settings.EMAIL_BACKEND, []):
        if not getattr(settings, "ANYMAIL", {}).get(key):
            problems.append(Error(f"EMAIL_BACKEND is {settings.EMAIL_BACKEND} but {key} is not set.", id="lpu.E004"))
    if settings.EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and settings.EMAIL_HOST in (
        "",
        "localhost",
        "127.0.0.1",
    ):
        problems.append(
            Warning(
                "SMTP is configured to localhost; there is no mail relay inside a platform container.",
                hint="Set EMAIL_HOST to your provider, or use an HTTPS email API.",
                id="lpu.W005",
            )
        )
    if not settings.REDIS_URL:
        problems.append(
            Warning(
                "REDIS_URL is not set: the cache is per process, so sign-in and API rate limits are multiplied "
                "by the number of gunicorn workers, and background jobs have no broker.",
                id="lpu.W003",
            )
        )
    if not settings.SITE_URL.startswith("https://"):
        problems.append(
            Warning(
                "SITE_URL is not https://; links in emails and QR codes would point at an insecure address.",
                id="lpu.W004",
            )
        )
    return problems
