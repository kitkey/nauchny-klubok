"""S0-v2 PP-DocLayout: чистые _categorize/_assemble (без модели/torch)."""
from p2kg.ingest.pdf_layout import _assemble, _categorize


def test_categorize_maps_labels():
    assert _categorize("table") == "table"
    assert _categorize("doc_title") == "title"
    assert _categorize("paragraph_title") == "title"
    assert _categorize("text") == "text"
    assert _categorize("abstract") == "text"
    assert _categorize("figure") == "drop"
    assert _categorize("formula_number") == "drop"
    assert _categorize("page_header") == "drop"
    # caption таблицы — не сама таблица, идёт в текст
    assert _categorize("table_caption") == "text"


def test_assemble_builds_clean_parsed():
    raw, parsed = _assemble([
        ("title", "Introduction"),
        ("text", "Polymers are useful."),
        ("table", "T1: yield strength data"),
        ("title", "Results"),
        ("text", "We observe X."),
    ])
    assert "Polymers are useful." in raw and "We observe X." in raw
    assert [s.name for s in parsed.sections] == ["Introduction", "Results"]
    assert len(parsed.tables) == 1
    # секция Introduction покрывает СВОЁ тело (а не только заголовок) и не залезает в Results
    s0 = parsed.sections[0]
    body0 = raw[s0.span.start:s0.span.end]
    assert s0.name == "Introduction" and "Polymers are useful." in body0
    assert "We observe X." not in body0


def test_assemble_fallback_body_when_no_titles():
    raw, parsed = _assemble([("text", "No headings here.")])
    assert len(parsed.sections) == 1 and parsed.sections[0].name == "body"


def test_role_hint_strips_numbering_and_substring():
    from p2kg.ingest.pdf import role_hint_from_heading
    from p2kg.schema import Role
    assert role_hint_from_heading("I.\nINTRODUCTION") == Role.BACKGROUND
    assert role_hint_from_heading("2.2 Methodology") == Role.METHOD
    assert role_hint_from_heading("A. Results and discussion") == Role.RESULT
    assert role_hint_from_heading("References") == Role.OTHER
    assert role_hint_from_heading("Data availability statement") == Role.OTHER
    assert role_hint_from_heading("Pareto Fronts") is None


def test_label_sections_fills_role_hint():
    from p2kg.config import Config
    from p2kg.context import Deps
    from p2kg.llm.prompts import PromptManager
    from p2kg.provenance import text_hash
    from p2kg.roles import _SectionRole, label_sections
    from p2kg.schema import ParsedDoc, Paper, Role, Section, Span

    class FakeLLM:
        def complete(self, user, *, system=None, model, schema=None, **kw):
            return [_SectionRole(title="Pareto Fronts", role=Role.RESULT)]

    raw = "x" * 50
    paper = Paper(paper_ref="p", raw_text=raw, text_hash=text_hash(raw),
                  parsed=ParsedDoc(sections=[Section(sec_id="sec-0", name="Pareto Fronts",
                                                     role_hint=None, span=Span(start=0, end=10))]))
    deps = Deps(llm=FakeLLM(), embed=None, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None)
    label_sections(deps, paper)
    assert paper.parsed.sections[0].role_hint == Role.RESULT
