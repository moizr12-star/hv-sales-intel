from src.crawler import _extract_doctor_name, _extract_doctor_phone


HOMEPAGE_WITH_DOCTOR = """
<html><body>
<h1>Smile Dental</h1>
<p>Dr. Sarah Smith, DDS leads our team. Call her direct line at (555) 123-4567.</p>
<footer>Front desk: (555) 999-0000</footer>
</body></html>
"""

NO_DOCTOR_PAGE = """
<html><body><h1>Smile Dental</h1><p>We treat everyone.</p></body></html>
"""


def test_extract_doctor_name_finds_dr_prefix():
    assert _extract_doctor_name(HOMEPAGE_WITH_DOCTOR) == "Dr. Sarah Smith"


def test_extract_doctor_name_finds_credential_suffix():
    text = "<h1>Sarah Smith, MD</h1>"
    assert _extract_doctor_name(text) == "Dr. Sarah Smith"


def test_extract_doctor_name_returns_none_when_absent():
    assert _extract_doctor_name(NO_DOCTOR_PAGE) is None


def test_extract_doctor_name_picks_most_frequent():
    text = """
    <p>Dr. Sarah Smith</p>
    <p>Dr. John Doe</p>
    <p>Dr. Sarah Smith</p>
    <p>Dr. Sarah Smith</p>
    """
    assert _extract_doctor_name(text) == "Dr. Sarah Smith"


def test_extract_doctor_phone_near_doctor_name():
    text = "Dr. Sarah Smith, DDS — direct (555) 123-4567"
    phone = _extract_doctor_phone(text, doctor_name="Dr. Sarah Smith", front_desk_phone=None)
    assert phone == "(555) 123-4567"


def test_extract_doctor_phone_skips_front_desk_match():
    text = "Dr. Sarah Smith, DDS — call (555) 999-0000"
    phone = _extract_doctor_phone(text, doctor_name="Dr. Sarah Smith", front_desk_phone="555-999-0000")
    assert phone is None


def test_extract_doctor_phone_returns_none_when_no_phone():
    text = "Dr. Sarah Smith, DDS leads our team."
    phone = _extract_doctor_phone(text, doctor_name="Dr. Sarah Smith", front_desk_phone=None)
    assert phone is None


def test_extract_doctor_phone_invalid_digits():
    text = "Dr. Sarah Smith — short 123"
    phone = _extract_doctor_phone(text, doctor_name="Dr. Sarah Smith", front_desk_phone=None)
    assert phone is None


def test_extract_doctor_phone_falls_back_to_label():
    text = "<p>contact us</p><p>Personal line: (555) 333-4444</p>"
    phone = _extract_doctor_phone(text, doctor_name=None, front_desk_phone=None)
    assert phone == "(555) 333-4444"
