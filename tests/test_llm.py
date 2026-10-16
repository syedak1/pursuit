"""The LLM stage, tested with a fake client: no network, no key. What matters is the gatekeeping:
a value is kept only if its quote is verbatim in the memo and consistent with the value."""

import sys
import types

from clock import llm


class FakeBlock:
    type = "tool_use"

    def __init__(self, data):
        self.input = data


class FakeUsage:
    def model_dump(self):
        return {"input_tokens": 1, "output_tokens": 1}


class FakeMessages:
    def __init__(self, data):
        self.data = data

    def create(self, **kw):
        assert kw["tool_choice"]["name"] == "record_contract"
        return types.SimpleNamespace(content=[FakeBlock(self.data)], usage=FakeUsage())


def run(monkeypatch, tmp_path, answer, memo):
    monkeypatch.setattr(llm, "CACHE", tmp_path)
    fake = types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=FakeMessages(answer)))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    events = {1: {"event_type": "contract", "vendor": "Acme", "vendor_key": "acme", "term_months": None,
                  "start_date": None, "end_date": None, "renewals": None, "route": None}}
    evidence = []
    stats = llm.fill_gaps(events, {1: {"title": "Agreement with Acme"}}, {1: memo}, evidence, model="test-model")
    return events[1], evidence, stats


def test_keeps_verified_values(monkeypatch, tmp_path):
    memo = "The City will enter a three-year agreement with Acme. Acme was chosen through RFP No. 25-1."
    answer = {"vendor": None, "start_date": None, "end_date": None, "renewals": None,
              "term_months": {"value": 36, "quote": "The City will enter a three-year agreement with Acme."},
              "route": {"value": "competitive", "quote": "Acme was chosen through RFP No. 25-1."}}
    ev, evidence, stats = run(monkeypatch, tmp_path, answer, memo)
    assert ev["term_months"] == 36 and ev["route"] == "competitive"
    assert {e["field"] for e in evidence} == {"term_months", "route"}
    assert all(e["method"] == "llm" and e["verified"] for e in evidence)


def test_drops_paraphrased_quote(monkeypatch, tmp_path):
    memo = "The City will enter a three-year agreement with Acme."
    answer = {"vendor": None, "start_date": None, "end_date": None, "renewals": None, "route": None,
              "term_months": {"value": 36, "quote": "The city will sign a 3 year deal with Acme."}}
    ev, evidence, stats = run(monkeypatch, tmp_path, answer, memo)
    assert ev["term_months"] is None and not evidence and stats["llm_quote_not_found"] == 1


def test_drops_real_quote_with_wrong_value(monkeypatch, tmp_path):
    memo = "Staff reviewed the history of the program. The agreement ends June 30, 2027."
    answer = {"vendor": None, "start_date": None, "renewals": None, "route": None, "term_months": None,
              "end_date": {"value": "2028-06-30", "quote": "The agreement ends June 30, 2027."}}
    ev, evidence, stats = run(monkeypatch, tmp_path, answer, memo)
    assert ev["end_date"] is None and stats["llm_quote_mismatch"] == 1
