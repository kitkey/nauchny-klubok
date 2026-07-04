from types import SimpleNamespace

from p2kg.config import Config
from p2kg.context import Deps
from p2kg.link.concepts import (
    Concept, ConceptGraph, _DefineOut, _HierItem, _HierOut, _LinkOut,
    link_entities, relink_hierarchy,
)
from p2kg.llm.prompts import PromptManager
from p2kg.schema import EntityType


class FakeEmbed:
    def __init__(self, vmap):
        self.vmap = vmap

    def encode(self, texts):
        out = []
        for t in texts:
            v = [0.0, 0.0, 1.0]
            for key, vec in self.vmap.items():
                if key in t:
                    v = vec
                    break
            out.append(v)
        return out


class FakeLLM:
    def __init__(self, fn):
        self.fn = fn
        self.link_calls = 0
        self.hier_calls = 0
        self.define_calls = 0

    def complete(self, user, *, system=None, model, schema=None, **kw):
        if schema is _LinkOut:
            self.link_calls += 1
        elif schema is _HierOut:
            self.hier_calls += 1
        elif schema is _DefineOut:
            self.define_calls += 1
        return self.fn(schema, user)


def _deps(embed, fn):
    return Deps(llm=FakeLLM(fn), embed=embed, prompts=PromptManager(), cfg=Config(),
                graph=None, docs=None)


def _ent(uuid, name, t=EntityType.PROPERTY, aliases=()):
    return SimpleNamespace(uuid=uuid, canonical_name=name, type=t, aliases=list(aliases))


def _concept(uuid, name, vec, t=EntityType.PROPERTY, n=0):
    return Concept(uuid=uuid, name=name, type=t, aliases=[], vec=vec, n=n)


def test_link_matches_existing_via_llm():
    # cosine 0.8 ∈ [TH_BLOCK, T_MERGE) -> одна канопия, но НЕ пред-кластер -> e2 идёт в LLM-линк
    embed = FakeEmbed({"Egap": [1, 0, 0], "electronic bandgap": [0.8, 0.6, 0]})
    fn = lambda schema, user: _DefineOut(definition="d") if schema is _DefineOut else _LinkOut(match_id=0)
    deps = _deps(embed, fn)  # LLM-линк «совпало с кандидатом 0»
    cg = ConceptGraph()
    ents = [_ent("u1", "Egap"), _ent("u2", "electronic bandgap")]

    fresh = link_entities(deps, cg, ents, ctx={})

    assert len(cg.concepts) == 1            # второй слинковался в первый
    assert len(fresh) == 1
    assert {c for (_, c) in cg.instance} == {next(iter(cg.concepts))}   # обе сущности -> один концепт
    assert deps.llm.link_calls == 1         # для u1 кандидатов не было; для u2 — звался
    assert deps.llm.define_calls == 0       # n=2 < порога 3 -> define ещё НЕ вызывался (провизорный контекст)


def test_blend_rescues_same_name_different_context():
    from p2kg.embedder import cosine
    from p2kg.link.concepts import TH_BLOCK, _blend
    # одно имя [1,0,0], РАЗНЫЙ контекст [0,1,0] vs [0,0,1]
    b1, b2 = _blend([1, 0, 0], [0, 1, 0]), _blend([1, 0, 0], [0, 0, 1])
    assert cosine(b1, b2) >= TH_BLOCK        # имя-доминанта -> одноимённые в одной канопии
    assert cosine([0, 1, 0], [0, 0, 1]) < TH_BLOCK   # чистый контекст развёл бы их (старое поведение)


def test_is_conceptual_predicate():
    from p2kg.link.concepts import _is_conceptual
    assert _is_conceptual("bandgap")
    assert _is_conceptual("ICP RIE plasma etching")
    assert _is_conceptual("silicon dioxide")
    assert not _is_conceptual("gentle etch step 2 with ICP 500 W, RF 200 W, Ar 50 sccm")   # дамп параметров
    assert not _is_conceptual("diamond bonded to a 300 nm PECVD SiO2 layer on a fused-quartz carrier")  # длинно
    assert not _is_conceptual("")


def test_filter_skips_instance_specific_concept():
    deps = _deps(FakeEmbed({"bandgap": [1, 0, 0]}), lambda schema, user: None)   # junk -> дефолт-вектор, др. канопия
    cg = ConceptGraph()
    ents = [_ent("u1", "bandgap"),
            _ent("u2", "gentle etch step 2 with ICP 500 W, RF 200 W, Ar 50 sccm, O2 50 sccm")]

    link_entities(deps, cg, ents, ctx={})

    assert {c.name for c in cg.concepts.values()} == {"bandgap"}   # только концептуальная
    assert len(cg.instance) == 1                                    # junk без INSTANCE_OF


def test_refine_define_at_threshold():
    embed = FakeEmbed({"bandgap": [1, 0, 0]})
    fn = lambda schema, user: _DefineOut(definition="DEF") if schema is _DefineOut else _LinkOut(match_id=0)
    deps = _deps(embed, fn)
    cg = ConceptGraph()
    ents = [_ent("u1", "bandgap"), _ent("u2", "bandgap"), _ent("u3", "bandgap")]

    link_entities(deps, cg, ents, ctx={"u1": "s1", "u2": "s2", "u3": "s3"})

    c = next(iter(cg.concepts.values()))
    assert c.n == 3                         # три инстанса
    assert c.defined is True               # дозрел -> определение выяснено
    assert c.context == "DEF"              # контекст = определение из пула
    assert deps.llm.define_calls == 1      # ровно один define (на 3-м инстансе)


def test_link_creates_new_when_llm_says_none():
    # более специфичный ключ ПЕРВЫМ (FakeEmbed матчит подстроку по порядку); cosine 0.8 -> e2 идёт в LLM-линк
    embed = FakeEmbed({"electronic density": [0.8, 0.6, 0], "density": [1, 0, 0]})
    fn = lambda schema, user: _DefineOut(definition="d") if schema is _DefineOut else _LinkOut(match_id=None)
    deps = _deps(embed, fn)  # LLM: «не тот же концепт» -> два концепта
    cg = ConceptGraph()
    ents = [_ent("u1", "density"), _ent("u2", "electronic density")]

    link_entities(deps, cg, ents, ctx={})

    assert len(cg.concepts) == 2            # косинус близок, но LLM развёл -> два концепта


def test_hierarchy_intermediate_insertion():
    # было: bandgap --SUBTYPE_OF--> physical property (прямое); приходит electronic property (посередине)
    B = _concept("b", "bandgap", [1, 0, 0])
    PP = _concept("pp", "physical property", [1, 0, 0])
    cg = ConceptGraph(concepts={"b": B, "pp": PP}, subtype={("b", "pp")}, instance=[])
    EP = _concept("ep", "electronic property", [1, 0, 0], n=3)   # дозрел -> иерархия для него строится
    cg.add_concept(EP)

    def fn(schema, user):
        # bandgap -> child (⊂ EP); physical property -> parent (EP ⊂ него)
        return _HierOut(relations=[_HierItem(id=0, rel="child"), _HierItem(id=1, rel="parent")])
    deps = _deps(FakeEmbed({}), fn)

    relink_hierarchy(deps, cg)

    assert ("b", "ep") in cg.subtype        # bandgap -> electronic property
    assert ("ep", "pp") in cg.subtype       # electronic property -> physical property
    assert ("b", "pp") not in cg.subtype    # старое прямое ребро убрано (транзитивная редукция)


def test_hierarchy_cycle_guard():
    # есть A --SUBTYPE_OF--> B. Приходит C; LLM: A — родитель C (C->A), B — ребёнок C (B->C).
    # B->C создало бы цикл B->C->A->B -> должно быть ЗАБЛОКИРОВАНО.
    A = _concept("a", "A", [1, 0, 0])
    B = _concept("b", "B", [1, 0, 0])
    cg = ConceptGraph(concepts={"a": A, "b": B}, subtype={("a", "b")}, instance=[])  # A ⊂ B
    C = _concept("c", "C", [1, 0, 0], n=3)   # дозрел
    cg.add_concept(C)

    def fn(schema, user):
        # near (exclude C) = [A, B]; A=parent (ребро C->A), B=child (ребро B->C)
        return _HierOut(relations=[_HierItem(id=0, rel="parent"), _HierItem(id=1, rel="child")])
    deps = _deps(FakeEmbed({}), fn)

    relink_hierarchy(deps, cg)

    assert ("c", "a") in cg.subtype          # C ⊂ A добавлено
    assert ("b", "c") not in cg.subtype      # B ⊂ C заблокировано (создало бы цикл)
    from p2kg.link.concepts import _reachable
    for (x, y) in cg.subtype:                # реального цикла нет: ни для одного ребра x->y нет пути y->x
        assert not _reachable(cg, y, x)


def test_hierarchy_same_merges():
    A = _concept("a", "electronic property", [1, 0, 0])
    cg = ConceptGraph(concepts={"a": A}, subtype=set(), instance=[("e1", "a")])
    DUP = _concept("dup", "electronic properties", [1, 0, 0], n=3)   # дозрел
    cg.add_concept(DUP)
    cg.instance.append(("e2", "dup"))

    deps = _deps(FakeEmbed({}), lambda schema, user: _HierOut(relations=[_HierItem(id=0, rel="same")]))
    relink_hierarchy(deps, cg)

    assert "dup" not in cg.concepts                         # дубль слит
    assert ("e2", "a") in cg.instance                       # его instance переехал на оставшийся концепт
