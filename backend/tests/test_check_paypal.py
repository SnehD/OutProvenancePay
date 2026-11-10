"""The credential checker, against the in-memory fake PayPal only. No network, no real credentials."""
import httpx

from app.config import Settings
from app.services.mock_paypal import FakePayPal
from app.services.paypal import PayPalClient
from check_paypal import run


def _run(tmp_path, *, fake=None, make_order=False, base="https://paypal.mock", configured=True):
    fake = fake or FakePayPal()
    settings = Settings(data_dir=tmp_path, paypal_base_url=base,
                        paypal_client_id="id-test" if configured else "", paypal_client_secret="TOPSECRET-test" if configured else "")
    lines = []
    code = run(settings, PayPalClient(settings, transport=httpx.MockTransport(fake.handler)), make_order, out=lines.append)
    return code, "\n".join(lines), fake


def test_not_configured_exits_2_and_explains(tmp_path):
    code, text, fake = _run(tmp_path, configured=False)
    assert code == 2 and "NOT CONFIGURED" in text and fake.calls == []


def test_live_host_is_refused_before_any_request(tmp_path):
    code, text, fake = _run(tmp_path, base="https://api-m.paypal.com")
    assert code == 3 and "REFUSED" in text and fake.calls == []


def test_bad_credentials_exit_1(tmp_path):
    fake = FakePayPal(); fake.fail_oauth = True
    code, text, _ = _run(tmp_path, fake=fake)
    assert code == 1 and "FAILED" in text


def test_good_credentials_check_token_only_and_never_print_secrets(tmp_path):
    code, text, fake = _run(tmp_path)
    assert code == 0 and "OK" in text
    assert fake.orders == {}  # no order unless --order
    assert "TOPSECRET" not in text and "mock-token" not in text


def test_order_flag_creates_one_order_and_never_captures(tmp_path):
    code, text, fake = _run(tmp_path, make_order=True)
    assert code == 0 and len(fake.orders) == 1 and fake.capture_calls() == 0
    assert "Buyer approval link" in text and "No money has moved" in text
