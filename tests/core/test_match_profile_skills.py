import json
from types import SimpleNamespace

from core.job import Job, profile_skill_hash


def test_profile_skill_hash_order_independent():
    assert profile_skill_hash(["Python", "AWS"]) == profile_skill_hash(["aws", " python "])


class _FakeChoice:
    def __init__(self, content):
        self.message = SimpleNamespace(content=content)
        self.finish_reason = "stop"


class _FakeClient:
    def __init__(self, content):
        self._content = content

    class _Chat:
        pass

    @property
    def chat(self):
        client = self

        class _Completions:
            def create(self_inner, **kwargs):
                return SimpleNamespace(
                    choices=[_FakeChoice(client._content)],
                    usage=SimpleNamespace(cost=0.0),
                )

        return SimpleNamespace(completions=_Completions())


def test_match_profile_skills_stores_matched_and_hash():
    job = Job(job_key="k1", profile_id=1, description="d")
    job.ext_required_skills = "Python, Bachelors degree"
    job.ext_preferred_skills = "Docker"
    job.ext_tech_stack = ""
    user = SimpleNamespace(skills=["Python"], work_history="", education="", projects="")
    client = _FakeClient('{"matched": ["Python", "Bachelors degree"]}')

    class _FakeDB:
        def flush(self):
            pass

    job.match_profile_skills(user, client, "m", _FakeDB(), "SKILLS:\n{skills_to_match}")
    stored = json.loads(job.ext_skill_match)
    assert set(stored["matched"]) == {"Python", "Bachelors degree"}
    assert stored["profile_hash"] == profile_skill_hash(["Python"])


def test_match_profile_skills_no_chips_is_noop_call():
    job = Job(job_key="k2", profile_id=1, description="d")
    job.ext_required_skills = ""
    job.ext_preferred_skills = ""
    job.ext_tech_stack = ""
    user = SimpleNamespace(skills=["Python"], work_history="", education="", projects="")

    class _BoomClient:
        @property
        def chat(self):
            raise AssertionError("LLM must not be called when there are no chips")

    class _FakeDB:
        def flush(self):
            pass

    job.match_profile_skills(user, _BoomClient(), "m", _FakeDB(), "{skills_to_match}")
    stored = json.loads(job.ext_skill_match)
    assert stored["matched"] == []
