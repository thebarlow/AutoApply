from core.schemas import ExtraSection, ParsedField, ParsedEntry
from core.parsed_sections import build_section_from_parsed


def test_markdown_kind():
    s = build_section_from_parsed(ExtraSection(name="About", kind="markdown", markdown="Hi."))
    assert s.name == "About" and s.role == ""
    assert len(s.children) == 1
    f = s.children[0]
    assert f.type == "field" and f.kind == "markdown" and f.value == "Hi."
    assert f.llm_output is False


def test_bullets_and_taglist_single_field():
    b = build_section_from_parsed(ExtraSection(name="Wins", kind="bullets", items=["a", "b"]))
    assert b.children[0].kind == "bullets" and b.children[0].value == ["a", "b"]
    t = build_section_from_parsed(ExtraSection(name="Langs", kind="taglist", items=["EN", "ES"]))
    assert t.children[0].kind == "taglist" and t.children[0].value == ["EN", "ES"]


def test_fields_kind_is_one_group():
    s = build_section_from_parsed(ExtraSection(
        name="Links", kind="fields",
        fields=[ParsedField(label="Portfolio", value="x.com"),
                ParsedField(label="Blog", value="y.com")]))
    assert len(s.children) == 1 and s.children[0].type == "group"
    g = s.children[0]
    assert [f.name for f in g.children] == ["Portfolio", "Blog"]
    assert [f.value for f in g.children] == ["x.com", "y.com"]
    assert all(f.kind == "text" for f in g.children)


def test_list_kind_builds_list_with_union_template():
    s = build_section_from_parsed(ExtraSection(
        name="Certifications", kind="list",
        entries=[
            ParsedEntry(fields=[ParsedField(label="Name", value="AWS"),
                                ParsedField(label="Year", value="2023")]),
            ParsedEntry(fields=[ParsedField(label="Name", value="GCP"),
                                ParsedField(label="Issuer", value="Google")]),
        ]))
    lst = s.children[0]
    assert lst.type == "list"
    # union of labels across entries, first-seen order
    assert [f.name for f in lst.item_template.children] == ["Name", "Year", "Issuer"]
    assert len(lst.children) == 2
    first = {f.name: f.value for f in lst.children[0].children}
    assert first["Name"] == "AWS" and first["Year"] == "2023" and first.get("Issuer", "") == ""
