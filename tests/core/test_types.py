from core.types import JobState, SearchConfig, UserProfile


def test_job_state_values():
    assert JobState.PENDING == "pending"
    assert JobState.SCRAPED == "scraped"
    assert JobState.APPROVED == "approved"
    assert JobState.PENDING_REVIEW == "pending_review"
    assert JobState.GENERATED == "generated"
    assert JobState.APPLIED == "applied"
    assert JobState.REJECTED == "rejected"
    assert JobState.FAILED == "failed"
    assert len(JobState) == 8


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


from core.types import WorkHistoryEntry, EducationEntry


def test_work_history_entry_defaults():
    entry = WorkHistoryEntry(
        company="Acme",
        title="Engineer",
        start="2022-01",
        end="2024-01",
        summary="Built things.",
    )
    assert entry.company == "Acme"
    assert entry.title == "Engineer"
    assert entry.start == "2022-01"
    assert entry.end == "2024-01"
    assert entry.summary == "Built things."


def test_education_entry_defaults():
    entry = EducationEntry(
        institution="Columbia University",
        degree="B.S.",
        field="Electrical Engineering",
        graduated="2018",
        gpa=3.5,
    )
    assert entry.institution == "Columbia University"
    assert entry.degree == "B.S."
    assert entry.field == "Electrical Engineering"
    assert entry.graduated == "2018"
    assert entry.gpa == 3.5


def test_user_profile_uses_typed_subschemas():
    from core.types import UserProfile
    profile = UserProfile(
        work_history=[
            WorkHistoryEntry(
                company="Acme", title="Engineer",
                start="2022-01", end="2024-01", summary="Did stuff."
            )
        ],
        education=[
            EducationEntry(
                institution="MIT", degree="B.S.", field="CS",
                graduated="2020", gpa=3.8
            )
        ],
    )
    assert isinstance(profile.work_history[0], WorkHistoryEntry)
    assert isinstance(profile.education[0], EducationEntry)
