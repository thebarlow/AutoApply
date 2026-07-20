from core.application_fields import CANONICAL_FIELDS
from core.ats_schemas import STATIC_SCHEMAS, schema_for


def test_supported_ats_have_schemas():
    assert set(STATIC_SCHEMAS) == {"greenhouse", "lever", "ashby"}


def test_every_schema_field_maps_to_a_real_canonical_key():
    for ats, fields in STATIC_SCHEMAS.items():
        for f in fields:
            assert f.canonical_key in CANONICAL_FIELDS, f"{ats}:{f.field_id}"


def test_greenhouse_covers_core_contact_fields():
    keys = {f.canonical_key for f in schema_for("greenhouse")}
    assert {"first_name", "last_name", "email", "resume_file"} <= keys


def test_unknown_ats_returns_empty():
    assert schema_for("workday") == []
