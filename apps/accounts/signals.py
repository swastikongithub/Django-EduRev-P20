from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User
from .permissions import assign_role_group


@receiver(post_save, sender=User)
def keep_role_group_in_sync(sender, instance, **kwargs):
    assign_role_group(instance)
