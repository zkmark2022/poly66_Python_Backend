"""Unit tests for password hashing utilities."""

from src.pm_gateway.auth.password import hash_password, verify_password


def test_hash_is_not_plain():
    hashed = hash_password("MySecret1")
    assert hashed != "MySecret1"
    assert len(hashed) > 20


def test_verify_correct_password():
    hashed = hash_password("MySecret1")
    assert verify_password("MySecret1", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("MySecret1")
    assert verify_password("WrongPass9", hashed) is False


def test_same_plain_produces_different_hashes():
    # bcrypt uses random salt each time
    h1 = hash_password("MySecret1")
    h2 = hash_password("MySecret1")
    assert h1 != h2
