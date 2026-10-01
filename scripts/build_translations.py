"""
Build the Hindi and Punjabi message catalogues (locale/<lang>/LC_MESSAGES/django.po + .mo).

Django's `makemessages`/`compilemessages` need GNU gettext, which isn't available on every
developer machine (notably Windows). This script keeps the externalised strings and their
translations in one reviewed table and writes both the .po (for translators) and the
compiled .mo (for Django) with polib. Run after adding or changing translations:

    python scripts/build_translations.py

On a machine with gettext, `python manage.py makemessages -l hi -l pa` finds any newly
marked strings; add their translations here.
"""

from pathlib import Path

import polib

ROOT = Path(__file__).resolve().parent.parent

# msgid: (Hindi, Punjabi). Example queries stay in English because search parses English.
STRINGS = {
    "Home": ("होम", "ਹੋਮ"),
    "Find": ("खोजें", "ਲੱਭੋ"),
    "Calendar": ("कैलेंडर", "ਕੈਲੰਡਰ"),
    "Bookings": ("बुकिंग", "ਬੁਕਿੰਗ"),
    "Scan": ("स्कैन", "ਸਕੈਨ"),
    "Approvals": ("स्वीकृतियाँ", "ਮਨਜ਼ੂਰੀਆਂ"),
    "Board": ("बोर्ड", "ਬੋਰਡ"),
    "Resources": ("संसाधन", "ਸਰੋਤ"),
    "Upkeep": ("रखरखाव", "ਰੱਖ-ਰਖਾਅ"),
    "Stock": ("स्टॉक", "ਸਟਾਕ"),
    "Insights": ("विश्लेषण", "ਵਿਸ਼ਲੇਸ਼ਣ"),
    "Setup": ("सेटअप", "ਸੈੱਟਅੱਪ"),
    "Manage": ("प्रबंधन", "ਪ੍ਰਬੰਧ"),
    "Me": ("प्रोफ़ाइल", "ਪ੍ਰੋਫਾਈਲ"),
    "Theme": ("थीम", "ਥੀਮ"),
    "Skip to content": ("मुख्य सामग्री पर जाएँ", "ਮੁੱਖ ਸਮੱਗਰੀ ਤੇ ਜਾਓ"),
    "Campus resource booking": ("कैंपस संसाधन बुकिंग", "ਕੈਂਪਸ ਸਰੋਤ ਬੁਕਿੰਗ"),
    "Search resources": ("संसाधन खोजें", "ਸਰੋਤ ਲੱਭੋ"),
    "Try “lab for 40 tomorrow” or “projector block 34”": (
        "“lab for 40 tomorrow” या “projector block 34” आज़माएँ",
        "“lab for 40 tomorrow” ਜਾਂ “projector block 34” ਅਜ਼ਮਾਓ",
    ),
    "Good morning": ("सुप्रभात", "ਸ਼ੁਭ ਸਵੇਰ"),
    "Good afternoon": ("नमस्ते", "ਸਤ ਸ੍ਰੀ ਅਕਾਲ"),
    "Good evening": ("शुभ संध्या", "ਸ਼ੁਭ ਸ਼ਾਮ"),
    "What do you need, and when?": ("आपको क्या चाहिए, और कब?", "ਤੁਹਾਨੂੰ ਕੀ ਚਾਹੀਦਾ ਹੈ, ਅਤੇ ਕਦੋਂ?"),
    "Day": ("दिन", "ਦਿਨ"),
    "Today": ("आज", "ਅੱਜ"),
    "Tomorrow": ("कल", "ਕੱਲ੍ਹ"),
    "From": ("से", "ਤੋਂ"),
    "Until": ("तक", "ਤੱਕ"),
    "People": ("लोग", "ਲੋਕ"),
    "Show what's free": ("खाली क्या है, दिखाएँ", "ਖਾਲੀ ਕੀ ਹੈ, ਦਿਖਾਓ"),
    "Your next booking": ("आपकी अगली बुकिंग", "ਤੁਹਾਡੀ ਅਗਲੀ ਬੁਕਿੰਗ"),
    "Nothing booked yet": ("अभी तक कुछ बुक नहीं है", "ਹਾਲੇ ਕੁਝ ਬੁੱਕ ਨਹੀਂ ਹੈ"),
    "Your usual spots today": ("आज आपकी पसंदीदा जगहें", "ਅੱਜ ਤੁਹਾਡੀਆਂ ਪਸੰਦੀਦਾ ਥਾਵਾਂ"),
    "Sign in": ("साइन इन करें", "ਸਾਈਨ ਇਨ ਕਰੋ"),
    "Use your UMS VID or username.": ("अपनी UMS VID या यूज़रनेम डालें।", "ਆਪਣੀ UMS VID ਜਾਂ ਯੂਜ਼ਰਨੇਮ ਪਾਓ।"),
    "VID or username": ("VID या यूज़रनेम", "VID ਜਾਂ ਯੂਜ਼ਰਨੇਮ"),
    "Password": ("पासवर्ड", "ਪਾਸਵਰਡ"),
    "Language": ("भाषा", "ਭਾਸ਼ਾ"),
    "Save language": ("भाषा सहेजें", "ਭਾਸ਼ਾ ਸੰਭਾਲੋ"),
    "Choose the language for menus and the home screen. More screens follow as translations are reviewed.": (
        "मेनू और होम स्क्रीन की भाषा चुनें। अनुवाद की समीक्षा के साथ और स्क्रीन जुड़ेंगी।",
        "ਮੇਨੂ ਅਤੇ ਹੋਮ ਸਕ੍ਰੀਨ ਦੀ ਭਾਸ਼ਾ ਚੁਣੋ। ਅਨੁਵਾਦ ਦੀ ਸਮੀਖਿਆ ਨਾਲ ਹੋਰ ਸਕ੍ਰੀਨਾਂ ਜੁੜਨਗੀਆਂ।",
    ),
}

LANGS = {"hi": ("Hindi", 0), "pa": ("Punjabi", 1)}


def build():
    for code, (name, idx) in LANGS.items():
        po = polib.POFile()
        po.metadata = {
            "Project-Id-Version": "LPU Reserve",
            "Language": code,
            "MIME-Version": "1.0",
            "Content-Type": "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
            "Plural-Forms": "nplurals=2; plural=(n != 1);",
        }
        for msgid, translations in STRINGS.items():
            po.append(polib.POEntry(msgid=msgid, msgstr=translations[idx]))
        out = ROOT / "locale" / code / "LC_MESSAGES"
        out.mkdir(parents=True, exist_ok=True)
        po.save(str(out / "django.po"))
        po.save_as_mofile(str(out / "django.mo"))
        print(f"{name}: {len(po)} strings -> {out}")


if __name__ == "__main__":
    build()
