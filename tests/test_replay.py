"""A recorded mission replays in about the time asked for: tiny gaps add up, idle stretches are cut."""
import json
import time

from fastapi.testclient import TestClient

from atlas import server


def log(tmp_path, monkeypatch, ts):
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    lines = [json.dumps({"t": t, "kind": "tool", "case": "C1", "agent": "locator", "data": {}}) for t in ts]
    (run / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(server, "DATA", tmp_path)


def replay(duration):
    t0 = time.monotonic()
    with TestClient(server.app) as c:
        body = c.get(f"/api/runs/r1/events?duration={duration}").text
    return time.monotonic() - t0, body.count("data: {\"t\"")


def test_thousands_of_tiny_gaps_keep_their_total(tmp_path, monkeypatch):
    # 2,000 events 0.5 s apart in the recording: 1,000 s, replayed in 1 s, each gap is 0.5 ms
    log(tmp_path, monkeypatch, [i * 0.5 for i in range(2000)])
    took, n = replay(1.0)
    assert n == 2000
    assert 0.8 < took < 1.8


def test_an_idle_stretch_does_not_stall_the_replay(tmp_path, monkeypatch):
    # a mission stopped for 15 minutes and resumed: the pause is cut, the work before and after keeps its share
    log(tmp_path, monkeypatch, [i * 0.5 for i in range(200)] + [1000 + i * 0.5 for i in range(200)])
    took, n = replay(1.0)
    assert n == 400
    assert 0.8 < took < 1.8
