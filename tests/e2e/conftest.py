"""Shared fixtures for browser journeys."""

from datetime import time

import pytest

from apps.rules.models import AvailabilityRule, BookingPolicy


@pytest.fixture
def open_all_week(room_type, lpu):
    """Make the classroom type open every day 07:00–23:00 so journeys run at any hour."""
    AvailabilityRule.objects.filter(resource_type=room_type).delete()
    for wd in range(7):
        AvailabilityRule.objects.create(
            institution=lpu, scope="type", resource_type=room_type, weekday=wd, opens=time(7, 0), closes=time(23, 0)
        )
    BookingPolicy.objects.filter(resource_type=room_type).update(checkin_opens_minutes=120)
