"""The sidecar's only network code: one chat completion from GLM-5.3-Flash on Hive, under a daily budget.

The key is read at call time from a file outside the repo (BBNEWS_KEY_FILE, default ~/.config/hivemodels/api_key.env,
a HIVEMODELS_API_KEY=... line). Hive streams only and ignores reasoning controls; GLM spends most of its output on
reasoning, so max_tokens stays large and only the visible content is returned.
"""
import datetime
import json
import os
import re
import urllib.request

URL = 'https://api-cdn.thehive.ai/api/v3/chat/completions'
MODEL = 'zai-org/glm-5.3-flash'
KEY_FILE = os.environ.get('BBNEWS_KEY_FILE', os.path.expanduser('~/.config/hivemodels/api_key.env'))
THINK = re.compile(r'<think>.*?</think>', re.S)


def _load_hive_usage():
    """~/bin/hive_usage.py (the workstation Hive spend ledger read by `hive-spend`), or None off the workstation."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("hive_usage", os.path.expanduser("~/bin/hive_usage.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


_HIVE_USAGE = _load_hive_usage()


def _log_hive(tool, model, usage):
    if _HIVE_USAGE is not None:
        _HIVE_USAGE.log_call(tool, model, usage)


class HiveError(RuntimeError):
    pass


class BudgetExceeded(HiveError):
    pass


def load_key(path=KEY_FILE):
    """The API key from path. A missing or unreadable file is a HiveError, like a file without the key."""
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                name, sep, value = line.strip().partition('=')
                if sep and name.strip() == 'HIVEMODELS_API_KEY' and value.strip():
                    return value.strip().strip('"\'')
    except (OSError, ValueError) as e:     # ValueError: a file that is not UTF-8
        raise HiveError('cannot read the key file %s: %s' % (path, type(e).__name__)) from None
    raise HiveError('no HIVEMODELS_API_KEY in %s' % path)


class Budget:
    """Calls and output tokens spent today (local date), kept in a JSON file so restarts do not reset it."""

    def __init__(self, path, calls_per_day, tokens_per_day):
        self.path, self.calls_per_day, self.tokens_per_day = path, calls_per_day, tokens_per_day

    def _load(self):
        today = datetime.date.today().isoformat()
        try:
            with open(self.path, encoding='utf-8') as fh:
                st = json.load(fh)
        except (OSError, ValueError):
            st = {}
        if not isinstance(st, dict) or st.get('date') != today:
            st = {'date': today, 'calls': 0, 'out_tokens': 0, 'in_tokens': 0}
        return st

    def _save(self, st):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(st, fh)
        os.replace(tmp, self.path)

    def status(self):
        st = self._load()
        st['calls_per_day'], st['tokens_per_day'] = self.calls_per_day, self.tokens_per_day
        return st

    def reserve(self):
        st = self._load()
        if st['calls'] >= self.calls_per_day or st['out_tokens'] >= self.tokens_per_day:
            raise BudgetExceeded('daily budget spent: %d calls, %d output tokens' % (st['calls'], st['out_tokens']))
        st['calls'] += 1
        self._save(st)

    def record(self, usage):
        st = self._load()
        st['out_tokens'] += _count(usage.get('completion_tokens'))
        st['in_tokens'] += _count(usage.get('prompt_tokens'))
        self._save(st)


def _count(value):
    """A token count from a usage block: a non-negative int, 0 for anything else."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def complete(system, user, budget, max_tokens=16000, temperature=0.7, timeout=180, key=None):
    """(text, usage). Raises BudgetExceeded before spending, HiveError on any failure or empty answer. The key is read
    before a call is reserved, so a missing key file costs nothing."""
    key = key or load_key()
    budget.reserve()
    payload = {'model': MODEL, 'stream': True, 'max_tokens': max_tokens, 'temperature': temperature,
               'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode('utf-8'), method='POST', headers={
        'Content-Type': 'application/json', 'Accept': 'text/event-stream',
        'Authorization': 'Bearer ' + key})
    text, usage, spent = [], {}, [0]
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data: '):
                    continue
                data = line[6:]
                if data == '[DONE]':
                    break
                obj = json.loads(data)
                if not isinstance(obj, dict):
                    continue        # valid JSON that is not an event: skipped, never an AttributeError out of draft()
                if isinstance(obj.get('usage'), dict) and obj['usage']:
                    usage = obj['usage']
                choices = obj.get('choices')
                for ch in choices if isinstance(choices, list) else []:
                    delta = ch.get('delta') if isinstance(ch, dict) else None
                    if not isinstance(delta, dict):
                        continue
                    content, thought = delta.get('content'), delta.get('reasoning_content')
                    content = content if isinstance(content, str) else ''
                    text.append(content)
                    spent[0] += len(content) + (len(thought) if isinstance(thought, str) else 0)
    except (OSError, ValueError, RecursionError) as e:      # URLError, HTTPError are OSErrors; ValueError: bad JSON
        raise HiveError('%s: %s' % (type(e).__name__, e)) from None
    finally:
        # A stream that ends without a usage block still costs: charge about four characters per token.
        budget.record(usage or {'completion_tokens': spent[0] // 4})
        _log_hive('bbpro98-news', MODEL, usage)
    out = THINK.sub('', ''.join(text)).strip()
    if not out:
        raise HiveError('empty answer (usage %s)' % usage)
    return out, usage
