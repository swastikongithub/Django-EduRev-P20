from django.contrib.postgres.operations import BtreeGistExtension, TrigramExtension
from django.db import migrations


def create_default_institution(apps, schema_editor):
    Institution = apps.get_model("core", "Institution")
    Institution.objects.get_or_create(
        code="LPU", defaults={"name": "Lovely Professional University", "short_name": "LPU"}
    )


class Migration(migrations.Migration):
    """btree_gist lets a GiST exclusion constraint combine `resource =` with `period &&`."""

    dependencies = [("core", "0001_initial")]

    operations = [
        BtreeGistExtension(),
        TrigramExtension(),
        migrations.RunPython(create_default_institution, migrations.RunPython.noop),
    ]
