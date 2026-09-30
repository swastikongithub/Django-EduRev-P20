from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from . import signals  # noqa: F401
        from .permissions import sync_role_groups

        post_migrate.connect(sync_role_groups, sender=self)
