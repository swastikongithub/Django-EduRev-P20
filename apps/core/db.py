"""PostgreSQL expression helpers."""

from django.db.models import DateTimeField, DurationField, Func


class RangeLower(Func):
    function = "lower"
    output_field = DateTimeField()


class RangeUpper(Func):
    function = "upper"
    output_field = DateTimeField()


class RangeDuration(Func):
    """upper(range) - lower(range) as an interval."""

    template = "(upper(%(expressions)s) - lower(%(expressions)s))"
    output_field = DurationField()
