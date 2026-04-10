from __future__ import annotations

import hashlib
import math

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .solr_client import search_opinions


REGION_CENTROIDS = {
	'Central': (1.2906, 103.8510),
	'East': (1.3450, 103.9430),
	'West': (1.3400, 103.7060),
	'North': (1.4300, 103.8200),
	'South': (1.2750, 103.8100),
}

REGION_KEYWORDS = {
	'East': ['bedok', 'tampines', 'pasir ris', 'eunos', 'marine parade', 'katong', 'changi'],
	'West': ['jurong', 'clementi', 'choa chu kang', 'bukit batok', 'boon lay', 'west coast'],
	'North': ['woodlands', 'sembawang', 'yishun', 'admiralty', 'marsiling'],
	'South': ['harbourfront', 'sentosa', 'keppel', 'bukit merah'],
	'Central': ['amoy', 'maxwell', 'newton', 'toa payoh', 'tiong bahru', 'adam road', 'bugis', 'orchard', 'chinatown'],
}

# Common centres seen in the current corpus; fallback still covers unmatched names.
HAWKER_COORDS = {
	'adam road food centre': (1.3240, 103.8140),
	'amoy street food centre': (1.2794, 103.8458),
	'maxwell food centre': (1.2802, 103.8448),
	'lau pa sat': (1.2809, 103.8500),
	'tiong bahru market': (1.2848, 103.8331),
	'newton food centre': (1.3119, 103.8396),
	'old airport road food centre': (1.3082, 103.8850),
	'bedok interchange hawker centre': (1.3247, 103.9303),
	'blk 210 toa payoh lorong 8': (1.3358, 103.8531),
	'toa payoh lorong 8': (1.3358, 103.8531),
	'golden mile food centre': (1.3026, 103.8639),
	'hong lim market & food centre': (1.2862, 103.8452),
	'tekka centre': (1.3061, 103.8503),
	'marine parade central market': (1.3036, 103.9052),
	'east coast lagoon food village': (1.3023, 103.9129),
	'west coast market square': (1.2913, 103.7674),
	'yishun park hawker centre': (1.4296, 103.8359),
	'chomp chomp food centre': (1.3644, 103.8665),
}

SAMPLE_OPINIONS = [
	{
		'dish': 'Hainanese Chicken Rice',
		'stall': 'Tian Tian Hainanese Chicken Rice',
		'hawker_centre': 'Maxwell Food Centre',
		'location': 'Central',
		'rating': 4.5,
		'sentiment': 'Positive',
		'pred_sarcasm': 0,
		'sarcasm_label': 'Not Sarcastic',
		'review': 'The chicken is tender and the rice is fragrant with garlic and ginger. Queue moves fast.',
		'author': 'FoodieJohn',
	},
	{
		'dish': 'Char Kway Teow',
		'stall': 'Outram Park Fried Kway Teow Mee',
		'hawker_centre': 'Hong Lim Market & Food Centre',
		'location': 'Central',
		'rating': 4.8,
		'sentiment': 'Positive',
		'pred_sarcasm': 0,
		'sarcasm_label': 'Not Sarcastic',
		'review': 'Excellent wok hei and generous lap cheong. Slightly oily but worth it.',
		'author': 'HawkerFan88',
	},
	{
		'dish': 'Laksa',
		'stall': '328 Katong Laksa',
		'hawker_centre': 'East Coast Road',
		'location': 'East',
		'rating': 4.2,
		'sentiment': 'Neutral',
		'pred_sarcasm': 0,
		'sarcasm_label': 'Not Sarcastic',
		'review': 'Rich broth with decent spice, but can feel heavy from the coconut.',
		'author': 'MaryTan',
	},
	{
		'dish': 'Bak Chor Mee',
		'stall': 'Tai Hwa Pork Noodle',
		'hawker_centre': 'Crawford Lane',
		'location': 'Central',
		'rating': 4.6,
		'sentiment': 'Positive',
		'pred_sarcasm': 0,
		'sarcasm_label': 'Not Sarcastic',
		'review': 'Flavorful minced pork and a balanced vinegar-chili mix. Premium but solid.',
		'author': 'NoodleLover',
	},
	{
		'dish': 'Satay',
		'stall': 'Lau Pa Sat Satay Street',
		'hawker_centre': 'Lau Pa Sat',
		'location': 'Central',
		'rating': 3.5,
		'sentiment': 'Negative',
		'pred_sarcasm': 1,
		'sarcasm_label': 'Sarcastic',
		'review': 'Touristy pricing and sauce is overly sweet. There are better neighborhood stalls.',
		'author': 'LocalEats',
	},
	{
		'dish': 'Hokkien Mee',
		'stall': 'Fried Hokkien Prawn Mee',
		'hawker_centre': 'Tiong Bahru Market',
		'location': 'South',
		'rating': 4.7,
		'sentiment': 'Positive',
		'pred_sarcasm': 0,
		'sarcasm_label': 'Not Sarcastic',
		'review': 'Great prawn stock depth and sambal on the side ties everything together.',
		'author': 'PrawnMeeFanatic',
	},
]

def _build_local_analytics(rows: list[dict]) -> dict:
	if not rows:
		return {
			'avg_rating': 0.0,
			'sentiment_counts': {'Positive': 0, 'Neutral': 0, 'Negative': 0},
			'rating_buckets': {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0},
			'location_counts': [],
		}

	sentiment_counts = {'Positive': 0, 'Neutral': 0, 'Negative': 0}
	rating_buckets = {'1': 0, '2': 0, '3': 0, '4': 0, '5': 0}
	location_map: dict[str, int] = {}

	total_rating = 0.0
	for row in rows:
		rating_value = float(row.get('rating', 0))
		total_rating += rating_value

		sentiment = str(row.get('sentiment', 'Neutral'))
		if sentiment in sentiment_counts:
			sentiment_counts[sentiment] += 1

		if rating_value >= 5:
			rating_buckets['5'] += 1
		elif rating_value >= 4:
			rating_buckets['4'] += 1
		elif rating_value >= 3:
			rating_buckets['3'] += 1
		elif rating_value >= 2:
			rating_buckets['2'] += 1
		elif rating_value >= 1:
			rating_buckets['1'] += 1

		location = str(row.get('location', 'Unknown'))
		location_map[location] = location_map.get(location, 0) + 1

	location_counts = [
		{'name': name, 'count': count}
		for name, count in sorted(location_map.items(), key=lambda item: item[1], reverse=True)[:8]
	]

	return {
		'avg_rating': round(total_rating / len(rows), 2),
		'sentiment_counts': sentiment_counts,
		'rating_buckets': rating_buckets,
		'location_counts': location_counts,
	}


def _build_sarcasm_summary(rows: list[dict]) -> dict:
	total = len(rows)
	sarcastic_count = sum(1 for row in rows if int(row.get('pred_sarcasm', 0) or 0) == 1)
	non_sarcastic_count = max(0, total - sarcastic_count)
	sarcasm_rate = round((sarcastic_count / total) * 100, 1) if total else 0.0
	return {
		'total': total,
		'sarcastic_count': sarcastic_count,
		'non_sarcastic_count': non_sarcastic_count,
		'sarcasm_rate': sarcasm_rate,
	}


def _stable_offset(name: str) -> tuple[float, float]:
	# Stable tiny jitter prevents overlapping markers for centres sharing a fallback centroid.
	digest = hashlib.md5(name.encode('utf-8')).digest()
	lat_offset = ((digest[0] / 255) - 0.5) * 0.04
	lng_offset = ((digest[1] / 255) - 0.5) * 0.04
	return lat_offset, lng_offset


def _infer_region_from_centre_name(hawker_centre: str) -> str:
	value = (hawker_centre or '').lower()
	for region, keywords in REGION_KEYWORDS.items():
		if any(keyword in value for keyword in keywords):
			return region
	return 'Central'


def _coordinate_for_centre(hawker_centre: str, region: str) -> tuple[float, float, bool]:
	normalized = ' '.join((hawker_centre or '').lower().split())
	if normalized in HAWKER_COORDS:
		lat, lng = HAWKER_COORDS[normalized]
		return lat, lng, True

	base_lat, base_lng = REGION_CENTROIDS.get(region, REGION_CENTROIDS['Central'])
	offset_lat, offset_lng = _stable_offset(normalized or region)
	return base_lat + offset_lat, base_lng + offset_lng, False


def _build_map_points(rows: list[dict]) -> list[dict]:
	centres: dict[str, dict] = {}
	for row in rows:
		name = str(row.get('hawker_centre', 'Unknown Hawker Centre'))
		region = str(row.get('location', 'Central'))
		if name not in centres:
			lat, lng, is_exact = _coordinate_for_centre(name, region)
			centres[name] = {
				'name': name,
				'region': region,
				'lat': round(lat, 6),
				'lng': round(lng, 6),
				'is_exact': is_exact,
				'review_count': 0,
			}
		centres[name]['review_count'] += 1

	return sorted(centres.values(), key=lambda item: item['review_count'], reverse=True)


def _build_map_points_from_counts(centre_counts: list[dict]) -> list[dict]:
	points: list[dict] = []
	for item in centre_counts:
		name = str(item.get('name', 'Unknown Hawker Centre'))
		review_count = int(item.get('count', 0) or 0)
		region = str(item.get('region', '')) or _infer_region_from_centre_name(name)
		lat, lng, is_exact = _coordinate_for_centre(name, region)
		points.append(
			{
				'name': name,
				'region': region,
				'lat': round(lat, 6),
				'lng': round(lng, 6),
				'is_exact': is_exact,
				'review_count': review_count,
			}
		)

	return sorted(points, key=lambda point: point['review_count'], reverse=True)


def _apply_local_filters(opinions: list[dict], selected: dict) -> list[dict]:
	"""Filter fallback in-memory records to mirror Solr-driven behavior."""
	filtered = opinions

	if selected['q']:
		term = selected['q'].lower()
		filtered = [
			row
			for row in filtered
			if term in row['dish'].lower()
			or term in row['stall'].lower()
			or term in row['hawker_centre'].lower()
			or term in row['review'].lower()
		]

	if selected['locations']:
		filtered = [row for row in filtered if row['location'] in selected['locations']]

	if selected['sentiments']:
		filtered = [row for row in filtered if row['sentiment'] in selected['sentiments']]

	if selected['sarcasm_flags']:
		allowed = {int(flag) for flag in selected['sarcasm_flags'] if flag in {'0', '1'}}
		filtered = [row for row in filtered if int(row.get('pred_sarcasm', 0) or 0) in allowed]

	if selected['min_rating'] > 0:
		lower = float(selected['min_rating'])
		upper = lower + 0.999
		filtered = [row for row in filtered if lower <= float(row['rating']) <= upper]

	return filtered


def home(request: HttpRequest) -> HttpResponse:
	return render(
		request,
		'opinions/home.html',
		{
			'quick_queries': [
				'Where to find the best laksa?',
				'Is Tian Tian chicken rice worth the queue?',
				'Halal options at Bedok hawker centre',
			],
			'dish_types': ['Chicken Rice', 'Noodles', 'Seafood', 'BBQ & Satay', 'Drinks & Desserts', 'Local Favorites'],
		},
	)


def search_results(request: HttpRequest) -> HttpResponse:
	page = max(1, int(request.GET.get('page', '1') or '1'))
	page_size = 30

	selected = {
		'q': request.GET.get('q', '').strip(),
		'locations': request.GET.getlist('location'),
		'sentiments': request.GET.getlist('sentiment'),
		'sarcasm_flags': request.GET.getlist('sarcasm'),
		'min_rating': int(request.GET.get('rating', '0')),
	}

	search_payload = search_opinions(
		query=selected['q'],
		locations=selected['locations'],
		sentiments=selected['sentiments'],
		sarcasm_flags=selected['sarcasm_flags'],
		min_rating=selected['min_rating'],
		page=page,
		page_size=page_size,
	)
	if search_payload is None:
		local_results = _apply_local_filters(SAMPLE_OPINIONS, selected)
		total_count = len(local_results)
		start = (page - 1) * page_size
		end = start + page_size
		results = local_results[start:end]
		analytics = _build_local_analytics(local_results)
		sarcasm_summary = _build_sarcasm_summary(local_results)
		map_points = _build_map_points(local_results)
		spellcheck_suggestions = []
		corrected_query = ''
	else:
		results = search_payload['docs']
		total_count = search_payload['total']
		analytics = search_payload.get('analytics', _build_local_analytics(results))
		sarcasm_summary = search_payload.get('sarcasm_summary', _build_sarcasm_summary(results))
		map_points = _build_map_points_from_counts(analytics.get('hawker_centre_counts', []))
		spellcheck_suggestions = search_payload.get('spellcheck_suggestions', [])
		corrected_query = ''

		if not results and selected['q'] and spellcheck_suggestions:
			corrected_query = spellcheck_suggestions[0]
			corrected_payload = search_opinions(
				query=corrected_query,
				locations=selected['locations'],
				sentiments=selected['sentiments'],
				sarcasm_flags=selected['sarcasm_flags'],
				min_rating=selected['min_rating'],
				page=page,
				page_size=page_size,
			)
			if corrected_payload:
				results = corrected_payload['docs']
				total_count = corrected_payload['total']
				analytics = corrected_payload.get('analytics', _build_local_analytics(results))
				sarcasm_summary = corrected_payload.get('sarcasm_summary', _build_sarcasm_summary(results))
				map_points = _build_map_points_from_counts(analytics.get('hawker_centre_counts', []))
				spellcheck_suggestions = corrected_payload.get('spellcheck_suggestions', spellcheck_suggestions)

	total_pages = max(1, math.ceil(total_count / page_size))
	page = min(page, total_pages)

	sentiment_order = ['Positive', 'Neutral', 'Negative']
	sentiment_chart = []
	for label in sentiment_order:
		count = int(analytics.get('sentiment_counts', {}).get(label, 0))
		pct = round((count / total_count) * 100, 1) if total_count else 0
		sentiment_chart.append({'label': label, 'count': count, 'pct': pct})
	top_sentiment = max(sentiment_chart, key=lambda item: item['count']) if sentiment_chart else {'label': 'N/A', 'count': 0}

	rating_chart = []
	for label in ['1', '2', '3', '4', '5']:
		count = int(analytics.get('rating_buckets', {}).get(label, 0))
		pct = round((count / total_count) * 100, 1) if total_count else 0
		rating_chart.append({'label': label, 'count': count, 'pct': pct})

	location_chart = []
	for item in analytics.get('location_counts', [])[:5]:
		count = int(item.get('count', 0))
		pct = round((count / total_count) * 100, 1) if total_count else 0
		location_chart.append({'name': item.get('name', 'Unknown'), 'count': count, 'pct': pct})

	query_params = request.GET.copy()
	query_params.pop('page', None)

	context = {
		'query': selected['q'],
		'corrected_query': corrected_query,
		'results': results,
		'result_count': total_count,
		'analytics': analytics,
		'sarcasm_summary': sarcasm_summary,
		'sentiment_chart': sentiment_chart,
		'top_sentiment': top_sentiment,
		'rating_chart': rating_chart,
		'location_chart': location_chart,
		'selected': selected,
		'current_page': page,
		'total_pages': total_pages,
		'has_prev': page > 1,
		'has_next': page < total_pages,
		'prev_page': page - 1,
		'next_page': page + 1,
		'query_string': query_params.urlencode(),
		'map_points': map_points,
		'map_point_count': len(map_points),
		'spellcheck_suggestions': spellcheck_suggestions,
		'locations': ['Central', 'East', 'West', 'North', 'South'],
		'sentiments': ['Positive', 'Neutral', 'Negative'],
		'sarcasm_options': [
			{'value': '1', 'label': 'Sarcastic'},
			{'value': '0', 'label': 'Not Sarcastic'},
		],
	}
	return render(request, 'opinions/search_results.html', context)
