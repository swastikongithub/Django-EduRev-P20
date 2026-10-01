"""
Two-step sign-in in a real browser: a privileged account enrols an authenticator on its first
sign-in, then signs in again with a code from the same secret (the path that failed locally on
2026-10-01 after the secret key changed; see tests/test_mfa.py for the unit-level regression).
"""

import os
import time

import pyotp
import pytest

os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # Playwright's sync API runs an event loop
pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

PASSWORD = "x-test-password-123"


def password_step(page, live_server, user):
    page.goto(f"{live_server.url}/login/")
    page.fill("#id_username", user.username)
    page.fill("#id_password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url("**/login/verify/", wait_until="domcontentloaded")


def test_enrol_then_sign_in_again_with_the_authenticator(page, live_server, admin_user):
    password_step(page, live_server, admin_user)
    assert "Set up two-step sign-in" in page.content()
    assert page.locator(".mfa-qr svg").count() == 1
    key = page.locator("code.mfa-key").text_content().strip()
    totp = pyotp.TOTP(key)  # what Google Authenticator computes from the scanned QR code

    page.fill("#code", totp.now())
    page.click("button[type=submit]")
    page.wait_for_url(f"{live_server.url}/home/", wait_until="domcontentloaded")

    page.goto(f"{live_server.url}/me/")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url("**/login/**", wait_until="domcontentloaded")

    password_step(page, live_server, admin_user)
    assert "Enter your 6-digit code" in page.content()
    page.fill("#code", totp.at(time.time() + 30))  # the next code: the first one is spent
    page.click("button[type=submit]")
    page.wait_for_url(f"{live_server.url}/home/", wait_until="domcontentloaded")
    assert "didn't match" not in page.content()
