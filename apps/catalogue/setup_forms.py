"""
Catalogue setup forms: resource types, buildings (blocks) and departments.

These are the campus structure every resource and person hangs off. They are edited by
campus-wide staff (facility managers and administrators) in the console; codes are unique per
institution, compared without regard to case, and every rule answers in a sentence.
"""

from __future__ import annotations

from django import forms
from django.utils.text import slugify

from apps.accounts.models import Department, Role

from .models import Building, ResourceCategory, ResourceType

# Icons that exist in static/img/icons.svg and suit a resource type, and the accents the
# design system renders (apps.core.templatetags.ui.ACCENT_ART).
TYPE_ICONS = [
    ("door-open", "Door (rooms)"),
    ("presentation", "Lectern (lecture theatres)"),
    ("monitor", "Monitor (computer labs)"),
    ("cpu", "Chip (electronics labs)"),
    ("flask-conical", "Flask (science labs)"),
    ("mic", "Microphone (halls)"),
    ("users", "People (meeting rooms)"),
    ("trophy", "Trophy (sports)"),
    ("dumbbell", "Dumbbell (fitness)"),
    ("camera", "Camera (equipment)"),
    ("bus", "Bus (vehicles)"),
    ("palette", "Palette (studios)"),
    ("box", "Box (anything else)"),
]
TYPE_ACCENTS = [
    ("orange", "Orange"),
    ("amber", "Amber"),
    ("blue", "Blue"),
    ("indigo", "Indigo"),
    ("green", "Green"),
    ("ink", "Ink"),
]


class _InstitutionCodeForm(forms.ModelForm):
    """Shared duplicate check: a code is unique within the institution, regardless of case."""

    code_noun = "code"

    def __init__(self, *args, institution_id: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.institution_id = institution_id

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        clash = self._meta.model.objects.filter(institution_id=self.institution_id, code__iexact=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(f"{clash.first()} already uses the {self.code_noun} {code}. Choose another.")
        return code


class ResourceTypeForm(_InstitutionCodeForm):
    code_noun = "code"
    icon = forms.ChoiceField(choices=TYPE_ICONS, initial="box")
    accent = forms.ChoiceField(choices=TYPE_ACCENTS, initial="orange")
    allowed_roles = forms.MultipleChoiceField(
        choices=Role.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Who may book",
        help_text="Leave every box empty to let everyone book this type.",
    )

    class Meta:
        model = ResourceType
        fields = ["name", "plural", "code", "category", "icon", "accent", "allowed_roles", "sort_order", "description"]
        labels = {"plural": "Plural name", "sort_order": "Order in lists"}
        help_texts = {
            "code": "Short identifier used in imports and links, for example classroom. Letters, numbers and hyphens.",
            "sort_order": "Lower numbers come first.",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False  # derived from the name when left empty

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            code = slugify(self.data.get(self.add_prefix("name"), ""))[:40]
            if not code:
                raise forms.ValidationError("Give the type a name or a code.")
        self.cleaned_data["code"] = code.lower()
        return super().clean_code().lower()

    def clean_plural(self):
        name = (self.cleaned_data.get("name") or "").strip()
        return (self.cleaned_data.get("plural") or "").strip() or (f"{name}s" if name else "")

    def clean_category(self):
        value = self.cleaned_data.get("category")
        if value not in ResourceCategory.values:
            raise forms.ValidationError("Choose a category.")
        return value


class BuildingForm(_InstitutionCodeForm):
    code_noun = "block code"

    class Meta:
        model = Building
        fields = ["code", "name", "zone", "description", "map_x", "map_y"]
        labels = {
            "code": "Block code",
            "zone": "Campus zone",
            "map_x": "Map position across (0-100)",
            "map_y": "Map position down (0-100)",
        }
        help_texts = {"code": "As signposted on campus, for example 34 or UNI-MALL."}

    def _bounded(self, name):
        value = self.cleaned_data.get(name)
        if value is not None and not 0 <= value <= 100:
            raise forms.ValidationError("Use a number from 0 to 100.")
        return value

    def clean_map_x(self):
        return self._bounded("map_x")

    def clean_map_y(self):
        return self._bounded("map_y")


class DepartmentForm(_InstitutionCodeForm):
    code_noun = "department code"

    class Meta:
        model = Department
        fields = ["code", "name", "school"]
        labels = {"code": "Department code"}
        help_texts = {"code": "For example CSE or ECE. Used to scope department heads and quotas."}
