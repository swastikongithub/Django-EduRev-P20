"""Keep the full-text document current whenever a resource or its features change."""

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .models import Resource


@receiver(post_save, sender=Resource)
def refresh_vector_on_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    from .search import refresh_search_vectors

    refresh_search_vectors(Resource.objects.filter(pk=instance.pk))


@receiver(m2m_changed, sender=Resource.features.through)
def refresh_vector_on_features(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and isinstance(instance, Resource):
        from .search import refresh_search_vectors

        refresh_search_vectors(Resource.objects.filter(pk=instance.pk))
