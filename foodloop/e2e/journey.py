"""FoodLoop end-to-end journey in a real browser.

Walks through the whole MVP the way people would use it and saves screenshots:
  customer signs up -> reserves a meal -> kitchen hands it over with the pickup code ->
  kitchen lists new surplus -> a new kitchen registers (pending) -> admin approves it.

Before running (see e2e/README.md):
  * backend on :8000 and frontend on :5173 are running
  * sample data exists:  python -m app.cli seed-sample
  * an admin exists:     python -m app.cli create-admin --email admin@example.com --name "Admin"

Run:  python e2e/journey.py
"""

import os
import re
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("FOODLOOP_URL", "http://localhost:5173")
OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin-pass-2024")
CHROME = os.environ.get("CHROMIUM_PATH")  # optional: use an already-installed Chromium
console_errors = []


def watch(page, name):
    page.on("console", lambda m: m.type == "error" and console_errors.append(f"[{name}] {m.text}"))
    page.on("pageerror", lambda e: console_errors.append(f"[{name}] PAGEERROR {e}"))


def shot(page, name, full=True):
    page.wait_for_timeout(700)  # let rise animations finish
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def logout(page):
    page.goto(BASE + "/")
    page.get_by_role("button", name=re.compile("Log out")).first.click()
    expect(page.get_by_role("link", name="Log in").first).to_be_visible()


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=CHROME) if CHROME else p.chromium.launch()
    desk = browser.new_context(viewport={"width": 1280, "height": 860}, timezone_id="Asia/Kolkata")
    page = desk.new_page()
    watch(page, "desktop")

    # 1. Landing + browse (public)
    page.goto(BASE + "/")
    expect(page.get_by_role("heading", name=re.compile("Good food"))).to_be_visible()
    expect(page.get_by_text("Fresh surplus near you")).to_be_visible()
    page.wait_for_selector("a[href^='/meals/']")
    shot(page, "01-landing-desktop")
    page.goto(BASE + "/meals")
    page.wait_for_selector("a[href^='/meals/']")
    shot(page, "02-browse-desktop")
    page.get_by_role("button", name="Lunch").click()
    page.wait_for_timeout(600)
    assert "meal=lunch" in page.url
    cards = page.locator("a[href^='/meals/']")
    print("lunch cards:", cards.count())
    page.get_by_role("button", name=re.compile("Clear filters")).click()

    # 2. Customer signs up and reserves
    email = f"e2e-{uuid.uuid4().hex[:6]}@example.com"
    page.goto(BASE + "/register")
    page.get_by_label("Your name").fill("Priya Nair")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill("lunch-break-2026")
    page.get_by_role("button", name="Create account").click()
    page.wait_for_url(BASE + "/meals")
    page.get_by_role("link", name=re.compile("Veg thali")).first.click()
    expect(page.get_by_role("heading", name=re.compile("Veg thali"))).to_be_visible()
    shot(page, "03-detail-desktop")
    page.get_by_role("button", name="One more").click()
    page.get_by_role("button", name=re.compile(r"Reserve 2 for")).click()
    expect(page.get_by_text("Reserved! Here's your pickup code")).to_be_visible()
    code = page.locator("p.font-mono").first.inner_text().strip()
    print("pickup code:", code)
    shot(page, "04-reserved-desktop", full=False)
    page.get_by_role("link", name=re.compile("View my reservations")).click()
    expect(page.get_by_text(code)).to_be_visible()
    shot(page, "05-my-reservations-desktop")
    logout(page)

    # 3. Kitchen hands over the meal with the code
    page.goto(BASE + "/login")
    page.get_by_label("Email").fill("kitchen@example.com")
    page.get_by_label("Password", exact=True).fill("sample-pass-2024")
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(BASE + "/kitchen")
    expect(page.get_by_text("Priya Nair")).to_be_visible()
    shot(page, "06-kitchen-pickups-desktop")
    page.get_by_placeholder("K7Q2MX").fill(code)
    page.get_by_role("button", name="Confirm pickup").click()
    expect(page.get_by_text("Handed over to Priya Nair")).to_be_visible()
    shot(page, "07-kitchen-collected-desktop", full=False)

    # 4. Kitchen lists new surplus through the form
    page.get_by_role("tab", name="Listings").click()
    page.wait_for_timeout(500)
    shot(page, "08-kitchen-listings-desktop")
    page.get_by_role("link", name=re.compile("List surplus food")).click()
    page.get_by_label("Meal name").fill("Rajma chawal")
    page.get_by_label("Usual price (₹)").fill("70")
    page.get_by_label("FoodLoop price (₹)").fill("35")
    page.get_by_role("button", name="60 min").click()
    page.get_by_text("None of these allergens").click()
    for box in page.locator("section").filter(has_text="Food-safety checklist").get_by_role("checkbox").all():
        box.check()
    shot(page, "09-listing-form-desktop")
    page.get_by_role("button", name="Publish listing").click()
    page.wait_for_url(re.compile(r"/kitchen\?tab=listings"))
    expect(page.get_by_text("Rajma chawal")).to_be_visible()
    logout(page)

    # 5. A new kitchen registers and is pending
    page.goto(BASE + "/register/kitchen")
    page.get_by_label("Manager's name").fill("Arjun Mehta")
    page.get_by_label("Email").fill(f"kitchen-{uuid.uuid4().hex[:6]}@example.com")
    page.get_by_label("Password", exact=True).fill("hostel-mess-2026")
    page.get_by_label("Kitchen name").fill("Hostel 4 Mess")
    page.get_by_label("Type of kitchen").select_option("hostel_mess")
    page.get_by_label("Kitchen phone").fill("98765 43210")
    page.get_by_label("Address").fill("Hostel 4, ground floor dining hall")
    page.get_by_label("Area or campus").fill("South Campus")
    page.get_by_label("City").fill("Pune")
    page.get_by_label("PIN code").fill("411007")
    page.get_by_label("Licence / registration no.").fill("2152 1234 5678 90")
    page.get_by_label("Valid until").fill("2027-12-31")
    page.get_by_role("button", name="Submit for approval").click()
    page.wait_for_url(BASE + "/kitchen")
    expect(page.get_by_text("Waiting for approval")).to_be_visible()
    shot(page, "10-kitchen-pending-desktop")
    logout(page)

    # 6. Admin approves it
    page.goto(BASE + "/login")
    page.get_by_label("Email").fill(ADMIN_EMAIL)
    page.get_by_label("Password", exact=True).fill(ADMIN_PASSWORD)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(BASE + "/admin")
    expect(page.get_by_text("Hostel 4 Mess")).to_be_visible()
    shot(page, "11-admin-desktop")
    page.locator("article").filter(has_text="Hostel 4 Mess").get_by_role("button", name="Approve").click()
    page.wait_for_timeout(800)
    expect(page.locator("article").filter(has_text="Hostel 4 Mess")).to_have_count(0)
    page.get_by_role("tab", name="Activity log").click()
    expect(page.get_by_text("Kitchen approved").first).to_be_visible()
    shot(page, "12-admin-activity-desktop")
    logout(page)

    # 7. Mobile views
    mobile = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        timezone_id="Asia/Kolkata",
    )
    m = mobile.new_page()
    watch(m, "mobile")
    m.goto(BASE + "/")
    m.wait_for_selector("a[href^='/meals/']")
    shot(m, "13-landing-mobile")
    m.goto(BASE + "/meals")
    m.wait_for_selector("a[href^='/meals/']")
    shot(m, "14-browse-mobile", full=False)
    m.get_by_role("button", name="Menu").click()
    shot(m, "15-menu-mobile", full=False)
    m.goto(BASE + "/meals/" + "00000000-0000-0000-0000-000000000000")
    expect(m.get_by_text("We couldn't load this")).to_be_visible()
    shot(m, "16-not-found-mobile", full=False)

    # horizontal overflow check at phone width
    for path in ["/", "/meals", "/register/kitchen", "/login"]:
        m.goto(BASE + path)
        m.wait_for_timeout(400)
        overflow = m.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        print(f"overflow {path}: {overflow}px")
    browser.close()

# The only expected error is the deliberate 404 from opening a meal that doesn't exist.
unexpected = [error for error in console_errors if "404" not in error]
print("Unexpected console errors:", unexpected or "none")
print(f"Journey passed. Screenshots saved in {OUT}")
