from web.middleware_impersonation import is_blocked


def test_get_never_blocked():
    assert is_blocked("GET", "/api/jobs", {"impersonate_profile_id": 9}) is False


def test_post_blocked_while_impersonating():
    assert is_blocked("POST", "/api/jobs/x/generate", {"impersonate_profile_id": 9}) is True


def test_post_allowed_without_flag():
    assert is_blocked("POST", "/api/jobs/x/generate", {}) is False


def test_stop_allowlisted():
    assert is_blocked("POST", "/api/admin/impersonate/stop", {"impersonate_profile_id": 9}) is False


def test_logout_allowlisted():
    assert is_blocked("POST", "/auth/logout", {"impersonate_profile_id": 9}) is False
