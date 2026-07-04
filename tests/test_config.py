from p2kg.config import Config


def test_defaults():
    c = Config()
    assert c.chunk_token_budget == 6000 and c.verify_theta == 0.6
    assert c.use_rudder is False and c.embed_model == "intfloat/e5-base-v2"


def test_from_env(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://x:1")
    monkeypatch.setenv("MONGO_URI", "mongodb://y:2")
    c = Config.from_env()
    assert c.neo4j_uri == "bolt://x:1" and c.mongo_uri == "mongodb://y:2"
