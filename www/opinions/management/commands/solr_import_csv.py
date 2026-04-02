from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError


REGION_KEYWORDS = {
    'East': ['bedok', 'tampines', 'pasir ris', 'eunos', 'marine parade', 'katong', 'changi'],
    'West': ['jurong', 'clementi', 'choa chu kang', 'bukit batok', 'boon lay', 'west coast'],
    'North': ['woodlands', 'sembawang', 'yishun', 'admiralty', 'marsiling'],
    'South': ['harbourfront', 'sentosa', 'keppel', 'bukit merah'],
    'Central': ['amoy', 'maxwell', 'newton', 'toa payoh', 'tiong bahru', 'adam road', 'bugis', 'orchard', 'chinatown'],
}

REQUIRED_CSV_COLUMNS = {
    'hawker_centre',
    'stall_name',
    'review_text',
    'star_rating',
    'sentiment',
    'word_count',
}


def infer_region(hawker_centre: str) -> str:
    value = hawker_centre.lower()
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in value for keyword in keywords):
            return region
    return 'Central'


def sanitize_sentiment(value: str) -> str:
    normalized = (value or '').strip().lower()
    if normalized == 'positive':
        return 'Positive'
    if normalized == 'negative':
        return 'Negative'
    return 'Neutral'


def clean_text(value: str) -> str:
    text = (value or '').strip()
    if not text:
        return ''

    while text.startswith('[') and text.endswith(']'):
        inner = text[1:-1].strip()
        if not inner:
            return ''
        text = inner

    while len(text) >= 2 and ((text[0] == "'" and text[-1] == "'") or (text[0] == '"' and text[-1] == '"')):
        text = text[1:-1].strip()

    return re.sub(r'\s+', ' ', text).strip()


def to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def infer_price_range(star_rating: float, word_count: int) -> str:
    score = star_rating * 0.8 + min(word_count, 300) / 100
    if score >= 6.8:
        return '$$$$'
    if score >= 5.3:
        return '$$$'
    if score >= 3.8:
        return '$$'
    return '$'


def normalize_csv_row(row: dict[str, str]) -> dict[str, str]:
    """Normalize CSV keys to handle BOM/spacing issues in headers."""
    normalized: dict[str, str] = {}
    for key, value in row.items():
        clean_key = (key or '').replace('\ufeff', '').strip()
        normalized[clean_key] = value
    return normalized


def build_doc(row: dict[str, str], index: int) -> dict[str, Any]:
    """Map source CSV schema -> Solr fields.

    Source CSV fields:
    - hawker_centre
    - stall_name
    - review_text
    - star_rating
    - sentiment
    - word_count
    """
    hawker_centre = clean_text(row.get('hawker_centre') or '')
    stall_name = clean_text(row.get('stall_name') or '')
    review_text = clean_text(row.get('review_text') or '')
    star_rating = to_float(row.get('star_rating', '0'), 0.0)
    sentiment = sanitize_sentiment(row.get('sentiment', 'Neutral'))
    word_count = to_int(row.get('word_count', '0'), 0)

    compact_stall = re.sub(r'\s+', ' ', stall_name) or 'Unknown Stall'

    return {
        'id': f'opinion-{index}',
        'hawker_centre': hawker_centre or 'Unknown Hawker Centre',
        'stall_name': compact_stall,
        'review_text': review_text,
        'star_rating': star_rating,
        'sentiment': sentiment,
        'word_count': word_count,
        'dish': compact_stall,
        'stall': compact_stall,
        'review': review_text,
        'rating': star_rating,
        'location': infer_region(hawker_centre),
        'price_range': infer_price_range(star_rating, word_count),
        'author': f'Reviewer{(index % 5000) + 1}',
        'created_at': f'{(index % 30) + 1} days ago',
        'likes': min(50 + word_count * 3, 9999),
        'comments': min(5 + word_count // 3, 999),
    }


def post_json(url: str, payload: Any, timeout: float = 30.0) -> Any:
    body = json.dumps(payload).encode('utf-8')
    request = Request(url, data=body, method='POST')
    request.add_header('Content-Type', 'application/json')
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


class Command(BaseCommand):
    help = 'Import hawker CSV opinions into Solr and ensure schema fields exist.'

    DEFAULT_CSV = '../classification/full_dataset_with_predictions.csv'

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            '--csv',
            default=self.DEFAULT_CSV,
            help=f'Absolute or relative path to CSV file. Defaults to {self.DEFAULT_CSV}.',
        )
        parser.add_argument('--solr-base', default='http://localhost:8983/solr', help='Solr base URL.')
        parser.add_argument('--core', default='opinions', help='Solr core name.')
        parser.add_argument('--batch-size', type=int, default=500, help='Batch size for Solr updates.')
        parser.add_argument('--append', action='store_true', help='Append without deleting existing docs.')

    def handle(self, *args, **options) -> None:
        csv_path = Path(options['csv']).expanduser().resolve()
        if not csv_path.exists():
            raise CommandError(f'CSV file does not exist: {csv_path}')

        solr_base = str(options['solr_base']).rstrip('/')
        core = str(options['core']).strip()
        batch_size = int(options['batch_size'])
        append = bool(options['append'])

        select_ping = f"{solr_base}/{core}/select?{urlencode({'q': '*:*', 'rows': 0, 'wt': 'json'})}"
        schema_url = f'{solr_base}/{core}/schema'
        update_url = f'{solr_base}/{core}/update?commit=true'

        try:
            with urlopen(select_ping, timeout=10):
                pass
        except (HTTPError, URLError) as exc:
            raise CommandError(
                f'Cannot reach Solr core at {select_ping}. Ensure Solr is running and core exists.\n{exc}'
            ) from exc

        self.stdout.write(self.style.NOTICE('Ensuring Solr schema fields...'))
        fields = [
            {'name': 'hawker_centre', 'type': 'text_general', 'stored': True, 'indexed': True},
            {'name': 'stall_name', 'type': 'text_general', 'stored': True, 'indexed': True},
            {'name': 'review_text', 'type': 'text_general', 'stored': True, 'indexed': True},
            {'name': 'star_rating', 'type': 'pfloat', 'stored': True, 'indexed': True},
            {'name': 'sentiment', 'type': 'string', 'stored': True, 'indexed': True},
            {'name': 'word_count', 'type': 'pint', 'stored': True, 'indexed': True},
            {'name': 'dish', 'type': 'text_general', 'stored': True, 'indexed': True},
            {'name': 'stall', 'type': 'text_general', 'stored': True, 'indexed': True},
            {'name': 'review', 'type': 'text_general', 'stored': True, 'indexed': True},
            {'name': 'rating', 'type': 'pfloat', 'stored': True, 'indexed': True},
            {'name': 'location', 'type': 'string', 'stored': True, 'indexed': True},
            {'name': 'price_range', 'type': 'string', 'stored': True, 'indexed': True},
            {'name': 'author', 'type': 'string', 'stored': True, 'indexed': True},
            {'name': 'created_at', 'type': 'string', 'stored': True, 'indexed': False},
            {'name': 'likes', 'type': 'pint', 'stored': True, 'indexed': True},
            {'name': 'comments', 'type': 'pint', 'stored': True, 'indexed': True},
        ]

        for field in fields:
            try:
                post_json(schema_url, {'add-field': field}, timeout=20)
            except HTTPError as exc:
                # Solr returns 400 when field already exists; safe to continue.
                if exc.code != 400:
                    raise CommandError(f'Failed to add field {field["name"]}: {exc}') from exc

        if not append:
            self.stdout.write(self.style.NOTICE('Clearing existing Solr documents...'))
            post_json(update_url, {'delete': {'query': '*:*'}}, timeout=30)

        self.stdout.write(self.style.NOTICE(f'Loading CSV: {csv_path}'))
        indexed = 0
        batch: list[dict[str, Any]] = []

        with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            fieldnames = [((name or '').replace('\ufeff', '').strip()) for name in (reader.fieldnames or [])]
            missing = sorted(REQUIRED_CSV_COLUMNS - set(fieldnames))
            if missing:
                raise CommandError(f'CSV header is missing required columns: {", ".join(missing)}')

            for i, row in enumerate(reader, start=1):
                normalized_row = normalize_csv_row(row)
                batch.append(build_doc(normalized_row, i))
                if len(batch) >= batch_size:
                    post_json(update_url, batch, timeout=60)
                    indexed += len(batch)
                    self.stdout.write(f'Indexed {indexed} docs...')
                    batch = []

        if batch:
            post_json(update_url, batch, timeout=60)
            indexed += len(batch)

        self.stdout.write(self.style.SUCCESS(f'Successfully indexed {indexed} documents into Solr core "{core}".'))
