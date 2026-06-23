from core.ats_tree_adapter import resume_document_for_ats
from core.profile_tree import FieldNode, GroupNode, RootNode, SectionNode


def _root():
    return RootNode(children=[
        SectionNode(name="Header", role="header", order=0, children=[
            GroupNode(name="Contact", children=[
                FieldNode(name="First Name", key="first_name", kind="text", value="Jane"),
                FieldNode(name="Last Name", key="last_name", kind="text", value="Doe"),
                FieldNode(name="Email", key="email", kind="text", value="j@x.co"),
                FieldNode(name="Phone", key="phone", kind="text", value="555"),
                FieldNode(name="Location", key="location", kind="text", value="NY"),
            ]),
        ]),
        SectionNode(name="Patents", order=1, children=[
            GroupNode(name="g", children=[
                FieldNode(name="d", key="d", kind="text", value="x"),
            ]),
        ]),
    ])


def test_header_projection():
    doc = resume_document_for_ats(_root())
    assert doc.header.name == "Jane Doe"
    assert doc.header.email == "j@x.co"
    assert doc.header.phone == "555"
    assert doc.header.location == "NY"


def test_section_order_lowercased():
    doc = resume_document_for_ats(_root())
    assert doc.section_order == ["header", "patents"]
