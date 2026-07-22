from core.schemas import ApplicationPlan, EnumeratedField, PlannedField


def test_enumerated_field_defaults():
    f = EnumeratedField(field_id="email")
    assert f.input_type == "text" and f.options == [] and f.required is False


def test_plan_roundtrips_json():
    plan = ApplicationPlan(
        job_key="linkedin_1",
        ats_type="greenhouse",
        generated_at="2026-07-20T00:00:00Z",
        fields=[
            PlannedField(
                field_id="email", value="a@b.c", status="filled", source="deterministic"
            )
        ],
    )
    dumped = plan.model_dump_json()
    back = ApplicationPlan.model_validate_json(dumped)
    assert back.fields[0].status == "filled"
