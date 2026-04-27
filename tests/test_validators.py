import pytest

from src.validators import validate_email, validate_password


# ---------- email ----------

def test_validate_email_accepts_basic_company_address():
    validate_email("sarah@healthandgroup.com")


def test_validate_email_accepts_dots_and_plus():
    validate_email("sarah.khan+team@healthandgroup.com")


def test_validate_email_accepts_uppercase_local_part():
    validate_email("Sarah.Khan@healthandgroup.com")


def test_validate_email_rejects_missing_at():
    with pytest.raises(ValueError, match="format"):
        validate_email("sarahhealthandgroup.com")


def test_validate_email_rejects_wrong_domain():
    with pytest.raises(ValueError, match="@healthandgroup.com"):
        validate_email("sarah@example.com")


def test_validate_email_rejects_double_dash_anywhere():
    with pytest.raises(ValueError, match="--"):
        validate_email("sarah--khan@healthandgroup.com")


def test_validate_email_rejects_empty_string():
    with pytest.raises(ValueError):
        validate_email("")


def test_validate_email_rejects_malformed_tld():
    with pytest.raises(ValueError, match="format"):
        validate_email("sarah@healthandgroup.")


# ---------- password ----------

def test_validate_password_accepts_compliant():
    validate_password("Healthy123!")


def test_validate_password_rejects_too_short():
    with pytest.raises(ValueError, match="8 characters"):
        validate_password("Ab1!")


def test_validate_password_rejects_no_uppercase():
    with pytest.raises(ValueError, match="uppercase"):
        validate_password("healthy123!")


def test_validate_password_rejects_no_lowercase():
    with pytest.raises(ValueError, match="lowercase"):
        validate_password("HEALTHY123!")


def test_validate_password_rejects_no_digit():
    with pytest.raises(ValueError, match="number"):
        validate_password("HealthyAbc!")


def test_validate_password_rejects_no_special():
    with pytest.raises(ValueError, match="special"):
        validate_password("Healthy123A")


def test_validate_password_rejects_empty():
    with pytest.raises(ValueError):
        validate_password("")
