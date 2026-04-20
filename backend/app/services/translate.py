"""Russian → Chinese translation via Google Translate (public endpoint).

In-memory cache is per-process; sufficient for typical dashboard usage.
"""
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import httpx

_CACHE_MAX = 5000
_cache: "OrderedDict[str, str]" = OrderedDict()
_cache_lock = Lock()


def _cache_get(key: str) -> str | None:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    return None


def _cache_set(key: str, value: str) -> None:
    with _cache_lock:
        _cache[key] = value
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def _fetch_translation(text: str) -> str:
    try:
        resp = httpx.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "ru", "tl": "zh-CN", "dt": "t", "q": text},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return "".join(part[0] for part in data[0] if part[0])
    except Exception as e:
        print(f"[Translate] Error on '{text[:40]}...': {e}")
    return ""


def translate_ru_to_zh(text: str) -> str:
    if not text or not text.strip():
        return ""
    cached = _cache_get(text)
    if cached is not None:
        return cached
    translated = _fetch_translation(text)
    if not translated:
        # retry once on transient failure / rate limit
        time.sleep(0.3)
        translated = _fetch_translation(text)
    if translated:
        _cache_set(text, translated)  # only cache successful results
    return translated


def translate_batch(texts: list[str]) -> dict[str, str]:
    """Translate a list of Russian texts to Chinese.

    Returns a dict mapping original text → translation. Empty strings are skipped.
    Duplicates and cached items are deduped to minimize external calls.
    """
    unique = list({t for t in texts if t and t.strip()})
    result: dict[str, str] = {}
    uncached: list[str] = []
    for t in unique:
        cached = _cache_get(t)
        if cached is not None:
            result[t] = cached
        else:
            uncached.append(t)
    if uncached:
        # keep concurrency moderate — public Google endpoint throttles aggressively
        with ThreadPoolExecutor(max_workers=4) as ex:
            translations = list(ex.map(translate_ru_to_zh, uncached))
        for t, tr in zip(uncached, translations):
            if tr:
                result[t] = tr
    return result
