from __future__ import annotations

import csv
import json
import os
import re
from difflib import get_close_matches
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def _build_filter_queries(
    locations: list[str],
    sentiments: list[str],
    sarcasm_flags: list[str],
    min_rating: int,
) -> list[str]:
    fq = []
    if locations:
        values = ' OR '.join(f'"{value}"' for value in locations)
        fq.append(f'location:({values})')
    if sentiments:
        values = ' OR '.join(f'"{value}"' for value in sentiments)
        fq.append(f'sentiment:({values})')
    valid_sarcasm = [flag for flag in sarcasm_flags if flag in {'0', '1'}]
    if valid_sarcasm:
        values = ' OR '.join(valid_sarcasm)
        fq.append(f'pred_sarcasm:({values})')
    if min_rating > 0:
        lower = float(min_rating)
        upper = lower + 0.999
        # Match exact star bucket (e.g. 3.0-3.999) across both legacy/current fields.
        fq.append(
            f'(rating:[{lower} TO {upper}] OR star_rating:[{lower} TO {upper}])'
        )
    return fq


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sarcasm_label(value: Any) -> str:
    return 'Sarcastic' if _safe_int(value, 0) == 1 else 'Not Sarcastic'


def _build_sarcasm_summary(total: int, facet_queries: dict[str, Any]) -> dict[str, Any]:
    sarcastic_count = _safe_int(facet_queries.get('pred_sarcasm:1'), 0)
    non_sarcastic_count = _safe_int(facet_queries.get('pred_sarcasm:0'), 0)
    sarcasm_rate = round((sarcastic_count / total) * 100, 1) if total else 0.0
    return {
        'total': total,
        'sarcastic_count': sarcastic_count,
        'non_sarcastic_count': non_sarcastic_count,
        'sarcasm_rate': sarcasm_rate,
    }


@lru_cache(maxsize=1)
def _load_spellcheck_vocabulary() -> tuple[str, ...]:
    vocabulary: set[str] = {
        'chicken', 'rice', 'laksa', 'satay', 'noodle', 'noodles', 'mee', 'fish', 'soup', 'coffee', 'curry',
        'bak', 'chor', 'hokkien', 'char', 'kway', 'teow', 'rojak', 'dessert', 'sugarcane', 'kangkong', 'lontong',
        'wanton', 'beef', 'prawn', 'fried', 'stall', 'hawker', 'centre', 'center', 'food', 'market', 'tow', 'payoh',
    }

    repo_root = Path(__file__).resolve().parents[2]
    candidate_paths = [
        repo_root / 'Q5 Sarcasm detection' / 'final_dataset_with_sarcasm_merged.csv',
        repo_root / 'hawker_corpus_final10k.csv',
        repo_root / 'Q4 Classification' / 'hawker_corpus_final10k.csv',
    ]

    for csv_path in candidate_paths:
        if not csv_path.exists():
            continue
        try:
            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    for field_name in ('review_text', 'stall_name', 'hawker_centre', 'dish', 'review', 'stall'):
                        text = _clean_text(row.get(field_name, ''))
                        for token in re.findall(r'[a-zA-Z]{3,}', text.lower()):
                            vocabulary.add(token)
        except Exception:
            continue

    return tuple(sorted(vocabulary))


def _fallback_spellcheck_suggestions(query: str) -> list[str]:
    normalized = _clean_text(query).lower()
    if not normalized:
        return []

    tokens = re.findall(r"[a-zA-Z]{3,}", normalized)
    if not tokens:
        return []

    vocabulary = _load_spellcheck_vocabulary()
    corrected_tokens: list[str] = []
    changed = False

    for token in tokens:
        matches = get_close_matches(token, vocabulary, n=1, cutoff=0.74)
        if matches:
            suggestion = matches[0]
            corrected_tokens.append(suggestion)
            changed = changed or suggestion != token
        else:
            corrected_tokens.append(token)

    if not changed:
        joined = ' '.join(tokens)
        matches = get_close_matches(joined, vocabulary, n=1, cutoff=0.82)
        if matches and matches[0] != joined:
            return [matches[0]]
        return []

    corrected_query = ' '.join(corrected_tokens).strip()
    return [corrected_query] if corrected_query and corrected_query != normalized else []


def _clean_text(value: Any) -> str:
    """Normalize list-like string values such as "['foo']" or '["foo"]'."""
    if value is None:
        return ''

    if isinstance(value, (list, tuple, set)):
        for item in value:
            cleaned = _clean_text(item)
            if cleaned:
                return cleaned
        return ''

    text = str(value).strip()
    if not text:
        return ''

    # Collapse repeated list wrappers emitted by some crawlers/indexers.
    while text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return ''
        text = inner

    # Remove matching quote pairs around the whole value.
    while len(text) >= 2 and ((text[0] == "'" and text[-1] == "'") or (text[0] == '"' and text[-1] == '"')):
        text = text[1:-1].strip()

    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _normalize_doc(doc: dict[str, Any]) -> dict[str, Any]:
    dish = _clean_text(doc.get('dish') or doc.get('stall_name')) or 'Unknown Dish'
    stall = _clean_text(doc.get('stall') or doc.get('stall_name')) or 'Unknown Stall'
    hawker_centre = _clean_text(doc.get('hawker_centre')) or 'Unknown Hawker Centre'
    location = _clean_text(doc.get('location')) or 'Unknown'
    sentiment = _clean_text(doc.get('sentiment')) or 'Neutral'
    review = _clean_text(doc.get('review', doc.get('review_text'))) or 'No review text available.'
    author = _clean_text(doc.get('author')) or 'Anonymous'
    sarcasm_flag = _safe_int(doc.get('pred_sarcasm'), 0)

    return {
        'dish': dish,
        'stall': stall,
        'hawker_centre': hawker_centre,
        'location': location,
        'rating': _safe_float(doc.get('rating', doc.get('star_rating')), 0.0),
        'sentiment': sentiment,
        'pred_sarcasm': sarcasm_flag,
        'sarcasm_label': _sarcasm_label(sarcasm_flag),
        'review': review,
        'author': author,
    }


def search_opinions(
    query: str,
    locations: list[str],
    sentiments: list[str],
    sarcasm_flags: list[str],
    min_rating: int,
    page: int,
    page_size: int,
) -> dict[str, Any] | None:
    """Return paginated Solr results or None when Solr is not available/enabled."""
    enabled = os.getenv('ENABLE_SOLR', 'false').lower() in {'1', 'true', 'yes'}
    if not enabled:
        return None

    base_url = os.getenv('SOLR_BASE_URL', 'http://localhost:8983/solr').rstrip('/')
    core = os.getenv('SOLR_CORE', 'opinions')
    timeout = float(os.getenv('SOLR_TIMEOUT_SECONDS', '3'))

    params: dict[str, Any] = {
        'q': query or '*:*',
        'defType': 'edismax',
        'qf': 'dish stall stall_name hawker_centre review review_text',
        'fl': 'dish,stall,stall_name,hawker_centre,location,rating,star_rating,sentiment,pred_sarcasm,review,review_text,author',
        'start': max(0, (page - 1) * page_size),
        'rows': page_size,
        'facet': 'true',
        'facet.mincount': '1',
        'facet.limit': '8',
        'facet.field': ['sentiment', 'location', 'hawker_centre_exact'],
        'f.hawker_centre_exact.facet.limit': '-1',
        'facet.query': [
            'rating:[1 TO 1.999]',
            'rating:[2 TO 2.999]',
            'rating:[3 TO 3.999]',
            'rating:[4 TO 4.999]',
            'rating:[5 TO 5.999]',
            'pred_sarcasm:1',
            'pred_sarcasm:0',
        ],
        'stats': 'true',
        'stats.field': 'rating',
        'spellcheck': 'true',
        'spellcheck.q': query or '',
        'spellcheck.build': 'true',
        'spellcheck.collate': 'true',
        'spellcheck.collateExtendedResults': 'true',
        'spellcheck.maxCollations': '1',
        'spellcheck.count': '3',
        'wt': 'json',
    }

    fq = _build_filter_queries(locations, sentiments, sarcasm_flags, min_rating)
    if fq:
        params['fq'] = fq

    query_string = urlencode(params, doseq=True)
    url = f'{base_url}/{core}/select?{query_string}'

    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode('utf-8'))
        response_data = payload.get('response', {})
        docs = response_data.get('docs', [])

        facet_counts = payload.get('facet_counts', {})
        facet_fields = facet_counts.get('facet_fields', {})
        facet_queries = facet_counts.get('facet_queries', {})

        sentiment_pairs = facet_fields.get('sentiment', []) or []
        location_pairs = facet_fields.get('location', []) or []
        hawker_centre_pairs = facet_fields.get('hawker_centre_exact', []) or []

        sentiment_counts: dict[str, int] = {}
        for i in range(0, len(sentiment_pairs), 2):
            key = _clean_text(sentiment_pairs[i])
            value = _safe_int(sentiment_pairs[i + 1], 0)
            if key:
                sentiment_counts[key] = value

        location_counts: list[dict[str, Any]] = []
        for i in range(0, len(location_pairs), 2):
            key = _clean_text(location_pairs[i])
            value = _safe_int(location_pairs[i + 1], 0)
            if key:
                location_counts.append({'name': key, 'count': value})

        hawker_centre_counts: list[dict[str, Any]] = []
        for i in range(0, len(hawker_centre_pairs), 2):
            key = _clean_text(hawker_centre_pairs[i])
            value = _safe_int(hawker_centre_pairs[i + 1], 0)
            if key:
                hawker_centre_counts.append({'name': key, 'count': value})

        rating_buckets = {
            '1': _safe_int(facet_queries.get('rating:[1 TO 1.999]'), 0),
            '2': _safe_int(facet_queries.get('rating:[2 TO 2.999]'), 0),
            '3': _safe_int(facet_queries.get('rating:[3 TO 3.999]'), 0),
            '4': _safe_int(facet_queries.get('rating:[4 TO 4.999]'), 0),
            '5': _safe_int(facet_queries.get('rating:[5 TO 5.999]'), 0),
        }

        total_matches = int(response_data.get('numFound', 0))
        avg_rating = _safe_float(
            payload.get('stats', {}).get('stats_fields', {}).get('rating', {}).get('mean'),
            0.0,
        )

        analytics = {
            'avg_rating': round(avg_rating, 2) if avg_rating > 0 else 0.0,
            'sentiment_counts': sentiment_counts,
            'rating_buckets': rating_buckets,
            'location_counts': location_counts,
            'hawker_centre_counts': hawker_centre_counts,
        }

        sarcasm_summary = _build_sarcasm_summary(total_matches, facet_queries)

        spellcheck_data = payload.get('spellcheck', {})
        suggestions: list[str] = []
        for suggestion in spellcheck_data.get('suggestions', []):
            if isinstance(suggestion, dict):
                options = suggestion.get('suggestion', [])
                if options:
                    first_option = options[0]
                    if isinstance(first_option, dict):
                        option_word = first_option.get('word')
                    else:
                        option_word = first_option
                    cleaned = _clean_text(option_word)
                    if cleaned and cleaned.lower() != query.lower():
                        suggestions.append(cleaned)
        if not suggestions:
            collations = spellcheck_data.get('collations', [])
            for collation in collations:
                if isinstance(collation, dict):
                    collation_query = _clean_text(collation.get('collationQuery'))
                    if collation_query and collation_query.lower() != query.lower():
                        suggestions.append(collation_query)
                elif isinstance(collation, str):
                    cleaned = _clean_text(collation)
                    if cleaned and cleaned.lower() != query.lower():
                        suggestions.append(cleaned)
        if not suggestions:
            suggestions = _fallback_spellcheck_suggestions(query)
        return {
            'docs': [_normalize_doc(doc) for doc in docs],
            'total': total_matches,
            'analytics': analytics,
            'sarcasm_summary': sarcasm_summary,
            'spellcheck_suggestions': suggestions,
        }
    except Exception:
        return None


def fetch_word_cloud_rows(
    query: str,
    locations: list[str],
    sentiments: list[str],
    sarcasm_flags: list[str],
    min_rating: int,
    max_rows: int = 10000,
    batch_size: int = 1000,
) -> list[dict[str, Any]] | None:
    """Fetch review text across the full filtered Solr result set for word cloud building."""
    enabled = os.getenv('ENABLE_SOLR', 'false').lower() in {'1', 'true', 'yes'}
    if not enabled:
        return None

    base_url = os.getenv('SOLR_BASE_URL', 'http://localhost:8983/solr').rstrip('/')
    core = os.getenv('SOLR_CORE', 'opinions')
    timeout = float(os.getenv('SOLR_TIMEOUT_SECONDS', '3'))

    fq = _build_filter_queries(locations, sentiments, sarcasm_flags, min_rating)
    rows_per_request = max(1, min(batch_size, max_rows))

    collected: list[dict[str, Any]] = []
    start = 0
    total_found: int | None = None

    try:
        while len(collected) < max_rows:
            params: dict[str, Any] = {
                'q': query or '*:*',
                'defType': 'edismax',
                'qf': 'dish stall stall_name hawker_centre review review_text',
                'fl': 'review,review_text',
                'start': start,
                'rows': min(rows_per_request, max_rows - len(collected)),
                'wt': 'json',
            }
            if fq:
                params['fq'] = fq

            query_string = urlencode(params, doseq=True)
            url = f'{base_url}/{core}/select?{query_string}'

            with urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))

            response_data = payload.get('response', {})
            docs = response_data.get('docs', [])
            if total_found is None:
                total_found = _safe_int(response_data.get('numFound', 0), 0)

            if not docs:
                break

            for doc in docs:
                cleaned_review = _clean_text(doc.get('review', doc.get('review_text')))
                if cleaned_review:
                    collected.append({'review': cleaned_review})
                if len(collected) >= max_rows:
                    break

            start += len(docs)
            if total_found is not None and start >= total_found:
                break

        return collected
    except Exception:
        return None
