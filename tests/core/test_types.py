from core.types import JobState, SearchConfig, UserProfile


def test_job_state_values():
    assert JobState.SCRAPED == "scraped"
    assert JobState.SCORED == "scored"
    assert JobState.PENDING_REVIEW == "pending_review"
    assert JobState.APPROVED == "approved"
    assert JobState.GENERATED == "generated"
    assert JobState.APPLIED == "applied"
    assert JobState.REJECTED == "rejected"
    assert JobState.FAILED == "failed"


def test_search_config_defaults():
    config = SearchConfig()
    assert config.keywords_whitelist == []
    assert config.keywords_blacklist == []
    assert config.remote_only is True
    assert config.full_time_only is True


def test_user_profile_defaults():
    profile = UserProfile()
    assert profile.name == ""
    assert profile.skills == []
    assert profile.work_history == []
    assert profile.education == []
