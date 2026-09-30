from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from apps.accounts.models import Department, Role
from apps.core.models import TenantModel, TimeStampedModel


class Building(TenantModel):
    """A campus block. LPU identifies blocks by number (e.g. "Block 34")."""

    code = models.CharField(max_length=16)
    name = models.CharField(max_length=120)
    zone = models.CharField(max_length=80, blank=True, help_text="Campus zone, e.g. Academic Zone, Sports Complex")
    description = models.CharField(max_length=240, blank=True)
    map_x = models.PositiveSmallIntegerField(default=50, help_text="Position on campus map (0-100)")
    map_y = models.PositiveSmallIntegerField(default=50)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uniq_building_code")]

    def __str__(self):
        return self.name


class ResourceCategory(models.TextChoices):
    SPACE = "space", "Space"
    LAB = "lab", "Laboratory"
    EQUIPMENT = "equipment", "Equipment"
    SPORTS = "sports", "Sports"
    VEHICLE = "vehicle", "Vehicle"


class ResourceType(TenantModel):
    code = models.SlugField(max_length=40)
    name = models.CharField(max_length=80)
    plural = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=16, choices=ResourceCategory.choices)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=40, default="box")
    accent = models.CharField(max_length=16, default="orange", help_text="Design-system accent token")
    allowed_roles = ArrayField(
        models.CharField(max_length=24, choices=Role.choices),
        default=list,
        blank=True,
        help_text="Roles allowed to book this type. Empty = everyone.",
    )
    sort_order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uniq_resourcetype_code")]

    def __str__(self):
        return self.name

    def role_may_book(self, role: str) -> bool:
        return not self.allowed_roles or role in self.allowed_roles


class Feature(TenantModel):
    name = models.CharField(max_length=60)
    icon = models.CharField(max_length=40, default="check")
    keywords = models.CharField(max_length=200, blank=True, help_text="Extra search terms")

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "name"], name="uniq_feature_name")]

    def __str__(self):
        return self.name


class ResourceStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    OUT_OF_SERVICE = "out_of_service", "Out of service"
    RETIRED = "retired", "Retired"


class Resource(TenantModel, TimeStampedModel):
    type = models.ForeignKey(ResourceType, on_delete=models.PROTECT, related_name="resources")
    code = models.CharField(max_length=32, help_text="Human code, e.g. 34-301")
    slug = models.SlugField(max_length=80)
    name = models.CharField(max_length=140)
    tagline = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    capacity = models.PositiveIntegerField(default=1)
    building = models.ForeignKey(Building, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources")
    floor = models.CharField(max_length=16, blank=True)
    room = models.CharField(max_length=24, blank=True)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources"
    )
    features = models.ManyToManyField(Feature, blank=True, related_name="resources")
    status = models.CharField(
        max_length=20, choices=ResourceStatus.choices, default=ResourceStatus.ACTIVE, db_index=True
    )
    status_note = models.CharField(max_length=200, blank=True)
    acquisition_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    image = models.ImageField(upload_to="resources/", blank=True)
    art = models.CharField(max_length=40, blank=True, help_text="Illustration key when no photo is uploaded")
    is_bookable = models.BooleanField(default=True)
    search_vector = SearchVectorField(null=True, editable=False)

    class Meta:
        ordering = ["type__sort_order", "building__code", "code"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "code"], name="uniq_resource_code"),
            models.UniqueConstraint(fields=["institution", "slug"], name="uniq_resource_slug"),
            models.CheckConstraint(condition=models.Q(capacity__gte=1), name="resource_capacity_positive"),
        ]
        indexes = [
            GinIndex(fields=["search_vector"], name="resource_search_gin"),
            GinIndex(fields=["name"], name="resource_name_trgm", opclasses=["gin_trgm_ops"]),
            models.Index(fields=["type", "status"]),
        ]

    def __str__(self):
        return f"{self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.name}")[:80]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalogue:detail", args=[self.slug])

    @property
    def location_label(self):
        bits = []
        if self.building:
            bits.append(self.building.name)
        if self.room:
            bits.append(f"Room {self.room}")
        elif self.floor:
            bits.append(f"Floor {self.floor}")
        return " · ".join(bits)

    @property
    def is_available_for_booking(self):
        return self.is_bookable and self.status == ResourceStatus.ACTIVE


class ResourceAttribute(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="attributes")
    key = models.CharField(max_length=60)
    value = models.CharField(max_length=200)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "key"]

    def __str__(self):
        return f"{self.key}: {self.value}"


class ResourceImage(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="resources/gallery/")
    caption = models.CharField(max_length=140, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]


class Custodian(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="custodians")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="custodianships")
    is_primary = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["resource", "user"], name="uniq_custodian")]

    def __str__(self):
        return f"{self.user} → {self.resource}"


class SavedResource(models.Model):
    """A user's starred resource — powers 'Your usual spots' on the home screen."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_resources")
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "resource"], name="uniq_saved_resource")]
