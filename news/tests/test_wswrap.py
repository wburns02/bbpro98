"""The model-written wrap of a complete bracket: bracket.SYSTEM, prompt and write (recap.draft over the template), and
Watcher.postseason_piece asking the model once the bracket is complete and never again for the same facts."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bracket   # noqa: E402
import gamedata  # noqa: E402
import recap     # noqa: E402
from tests.test_bracket import ASSOC, Pieces, finished, pieces, series, started  # noqa: E402,F401


def complete_ok(system, user, budget):
    return ('Ash take the 1998 flag\n\nAsh swept Birch 3-0, then beat Cedar 4-3 and took the World Series 4-0 over '
            'Dogwood.'), {'completion_tokens': 10}


class Model(Pieces):
    """Pieces with a budget and a stubbed complete(), every bracket.write call and every model ask recorded."""

    def __init__(self, tmp_path, monkeypatch, complete=complete_ok, budget=object()):
        super().__init__(tmp_path, monkeypatch)
        self.w.budget = budget
        self.inner = complete
        self.calls, self.asks = [], []
        real = bracket.write

        def write(f, b, c, attempts=2):
            self.calls.append(dict(f))
            return real(f, b, c, attempts)

        def ask(system, user, b):
            self.asks.append(user)
            return self.inner(system, user, b)

        monkeypatch.setattr(bracket, 'write', write)
        self.w.complete = ask


@pytest.fixture
def model(tmp_path, monkeypatch):
    return Model(tmp_path, monkeypatch)


def test_prompt_ends_with_the_rules_and_the_user_message_is_the_facts():
    f = bracket.facts(ASSOC, started(), 1998)
    system, user = bracket.prompt(f)
    assert system == ("You are a newspaper baseball writer. Write the wrap of the association's postseason: 150 to "
                      "250 words on how the champion got there, round by round, ending with the World Series. "
                      + recap.RULES)
    assert user == recap.facts_message(f)


def test_write_returns_the_model_story_that_passes_the_number_check():
    f = bracket.facts(ASSOC, finished(), 1998)
    got = bracket.write(f, object(), complete_ok)
    assert got['source'] == 'glm'
    assert got['headline'] == 'Ash take the 1998 flag'
    assert got['body'].startswith('Ash swept Birch 3-0')


def test_write_falls_back_to_the_template_after_two_bad_numbers():
    f = bracket.facts(ASSOC, finished(), 1998)

    def bad(system, user, budget):
        return 'Ash win 9-0 in 12 innings\n\nAsh swept everything, 6-0.', {}

    got = bracket.write(f, object(), bad)
    assert (got['source'], got['reason']) == ('template', 'numbers')
    assert got['headline'] == 'Ash win the 1998 World Series'


def test_an_incomplete_bracket_writes_the_template_and_never_calls_the_model(model):
    model.run()
    rec = model.read()
    assert (rec['source'], rec.get('reason')) == ('template', None)
    assert rec['headline'] == '1998 postseason'
    assert model.calls == []


def test_a_complete_bracket_gets_the_model_wrap(model):
    model.b = finished()
    model.run()
    rec = model.read()
    assert (rec['source'], rec['kind'], rec['created']) == ('glm', 'postseason', rec['created'])
    assert rec['headline'] == 'Ash take the 1998 flag'
    assert rec['facts'] == bracket.facts(ASSOC, finished(), 1998)
    assert len(model.calls) == 1 and model.calls[0]['champion'] == 'Ash'
    assert model.logs == ['A postseason 1998 (14 games) (glm)']


def test_a_second_pass_with_the_same_facts_calls_and_writes_nothing(model):
    model.b = finished()
    model.run()
    before = os.path.getmtime(model.path())
    model.run()
    assert os.path.getmtime(model.path()) == before and len(model.calls) == 1


def test_two_bad_replies_give_the_template_numbers_and_a_third_pass_calls_nothing(model):
    def bad(system, user, budget):
        return 'Ash win 9-0 in 12 innings\n\nAsh swept everything, 6-0.', {}

    model.inner = bad
    model.b = finished()
    model.run()
    rec = model.read()
    assert (rec['source'], rec['reason']) == ('template', 'numbers')
    assert rec['headline'] == 'Ash win the 1998 World Series'
    assert model.logs == ['A postseason 1998 (14 games) (template)']
    assert len(model.calls) == 1 and len(model.asks) == 2
    before = os.path.getmtime(model.path())
    model.run()
    assert os.path.getmtime(model.path()) == before and len(model.calls) == 1 and len(model.asks) == 2


def test_the_model_off_gives_the_template_off(model):
    model.w.complete = None
    model.b = finished()
    model.run()
    rec = model.read()
    assert (rec['source'], rec['reason']) == ('template', 'off')
    assert model.calls == [] and model.logs[-1] == 'A postseason 1998 (14 games) (template)'


def test_last_seasons_wrap_goes_to_the_past_folder(model):
    model.b = finished()
    model.b['current'] = False
    os.makedirs(os.path.join(model.out, 'past', '1998'))
    model.run(1999)
    rec = model.read('past', '1998')
    assert rec['source'] == 'glm' and rec['facts']['season'] == 1998
    assert not os.path.exists(model.path())
