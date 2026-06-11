import db.database as database


def test_migrate_helpers_are_gone():
    # The hand-rolled PRAGMA/data migrations must be fully retired.
    leftovers = [n for n in dir(database) if n.startswith("_migrate_")]
    assert leftovers == [], f"stale migration helpers still present: {leftovers}"


def test_init_db_runs_alembic_not_create_all(monkeypatch):
    calls = {"upgrade": 0, "create_all": 0}

    monkeypatch.setattr("alembic.command.upgrade", lambda cfg, rev: calls.__setitem__("upgrade", calls["upgrade"] + 1))
    monkeypatch.setattr(
        database.Base.metadata, "create_all",
        lambda *a, **k: calls.__setitem__("create_all", calls["create_all"] + 1),
    )
    import db.events as events
    monkeypatch.setattr(events, "register_tenant_guard", lambda: None)
    import db.seed as seed
    for fn in ("seed_field_help", "seed_user_profile_field_help",
               "seed_prompt_defaults", "migrate_file_prompts_to_db", "seed_skill_aliases"):
        monkeypatch.setattr(seed, fn, lambda *a, **k: None)
    # _seed_ats_parse_prompt opens its own session; stub it on the database module.
    monkeypatch.setattr(database, "_seed_ats_parse_prompt", lambda: None)

    database.init_db()

    assert calls["upgrade"] == 1
    assert calls["create_all"] == 0
