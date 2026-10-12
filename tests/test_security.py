import time

from kibo import security


def test_encrypt_decrypt_roundtrip():
    token = "super-secret-refresh-token"
    encrypted = security.encrypt(token)
    assert encrypted != token
    assert security.decrypt(encrypted) == token


def test_sign_and_verify_state_roundtrip():
    state = security.sign_state(12345)
    assert security.verify_state(state) == 12345


def test_verify_state_rejects_tampered_signature():
    state = security.sign_state(12345)
    tampered = state[:-4] + "abcd"
    assert security.verify_state(tampered) is None


def test_verify_state_rejects_garbage():
    assert security.verify_state("not-a-valid-state") is None


def test_verify_state_rejects_expired(monkeypatch):
    real_time = time.time
    monkeypatch.setattr(security.time, "time", lambda: real_time() - security.STATE_TTL_SECONDS - 10)
    state = security.sign_state(999)
    monkeypatch.setattr(security.time, "time", real_time)
    assert security.verify_state(state) is None
