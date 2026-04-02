from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


def _build_filter_queries(
    locations: list[str],
    sentiments: list[str],
    price_ranges: list[str],
    min_rating: int,
) -> list[str]:
    fq = []
    if locations:
        values = ' OR '.join(f'"{value}"' for value in locations)
        fq.append(f'location:({values})')
    if sentiments:
        values = ' OR '.join(f'"{value}"' for value in sentiments)
        fq.append(f'sentiment:({values})')
    if price_ranges:
        values = ' OR '.join(f'"{value}"' for value in price_ranges)
        fq.append(f'price_range:({values})')
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
    price_range = _clean_text(doc.get('price_range')) or '$'
    review = _clean_text(doc.get('review', doc.get('review_text'))) or 'No review text available.'
    author = _clean_text(doc.get('author')) or 'Anonymous'
    created_at = _clean_text(doc.get('created_at')) or 'Recently'

    return {
        'dish': dish,
        'stall': stall,
        'hawker_centre': hawker_centre,
        'location': location,
        'rating': _safe_float(doc.get('rating', doc.get('star_rating')), 0.0),
        'sentiment': sentiment,
        'price_range': price_range,
        'review': review,
        'author': author,
        'created_at': created_at,
        'likes': _safe_int(doc.get('likes'), 0),
        'comments': _safe_int(doc.get('comments'), 0),
    }


def search_opinions(
    query: str,
    locations: list[str],
    sentiments: list[str],
    price_ranges: list[str],
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
        'fl': 'dish,stall,stall_name,hawker_centre,location,rating,star_rating,sentiment,price_range,review,review_text,author,created_at,likes,comments',
        'start': max(0, (page - 1) * page_size),
        'rows': page_size,
        'facet': 'true',
        'facet.mincount': '1',
        'facet.limit': '8',
        'facet.field': ['sentiment', 'location'],
        'facet.query': [
            'rating:[1 TO 1.999]',
            'rating:[2 TO 2.999]',
            'rating:[3 TO 3.999]',
            'rating:[4 TO 4.999]',
            'rating:[5 TO 5.999]',
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

    fq = _build_filter_queries(locations, sentiments, price_ranges, min_rating)
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

        rating_buckets = {
            '1': _safe_int(facet_queries.get('rating:[1 TO 1.999]'), 0),
            '2': _safe_int(facet_queries.get('rating:[2 TO 2.999]'), 0),
            '3': _safe_int(facet_queries.get('rating:[3 TO 3.999]'), 0),
            '4': _safe_int(facet_queries.get('rating:[4 TO 4.999]'), 0),
            '5': _safe_int(facet_queries.get('rating:[5 TO 5.999]'), 0),
        }

        avg_rating = _safe_float(
            payload.get('stats', {}).get('stats_fields', {}).get('rating', {}).get('mean'),
            0.0,
        )

        analytics = {
            'avg_rating': round(avg_rating, 2) if avg_rating > 0 else 0.0,
            'sentiment_counts': sentiment_counts,
            'rating_buckets': rating_buckets,
            'location_counts': location_counts,
        }

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
        return {
            'docs': [_normalize_doc(doc) for doc in docs],
            'total': int(response_data.get('numFound', 0)),
            'analytics': analytics,
            'spellcheck_suggestions': suggestions,
        }
    except Exception:
        return None
