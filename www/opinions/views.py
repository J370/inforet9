from __future__ import annotations

import math

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .solr_client import search_opinions

SAMPLE_OPINIONS = [
	{
		'dish': 'Hainanese Chicken Rice',
		'stall': 'Tian Tian Hainanese Chicken Rice',
		'hawker_centre': 'Maxwell Food Centre',
		'location': 'Central',
		'rating': 4.5,
		'sentiment': 'Positive',
		'price_range': '$',
		'review': 'The chicken is tender and the rice is fragrant with garlic and ginger. Queue moves fast.',
		'author': 'FoodieJohn',
		'created_at': '2 days ago',
		'likes': 234,
		'comments': 45,
	},
	{
		'dish': 'Char Kway Teow',
		'stall': 'Outram Park Fried Kway Teow Mee',
		'hawker_centre': 'Hong Lim Market & Food Centre',
		'location': 'Central',
		'rating': 4.8,
		'sentiment': 'Positive',
		'price_range': '$$',
		'review': 'Excellent wok hei and generous lap cheong. Slightly oily but worth it.',
		'author': 'HawkerFan88',
		'created_at': '1 week ago',
		'likes': 456,
		'comments': 78,
	},
	{
		'dish': 'Laksa',
		'stall': '328 Katong Laksa',
		'hawker_centre': 'East Coast Road',
		'location': 'East',
		'rating': 4.2,
		'sentiment': 'Neutral',
		'price_range': '$$',
		'review': 'Rich broth with decent spice, but can feel heavy from the coconut.',
		'author': 'MaryTan',
		'created_at': '3 days ago',
		'likes': 189,
		'comments': 34,
	},
	{
		'dish': 'Bak Chor Mee',
		'stall': 'Tai Hwa Pork Noodle',
		'hawker_centre': 'Crawford Lane',
		'location': 'Central',
		'rating': 4.6,
		'sentiment': 'Positive',
		'price_range': '$$$',
		'review': 'Flavorful minced pork and a balanced vinegar-chili mix. Premium but solid.',
		'author': 'NoodleLover',
		'created_at': '5 days ago',
		'likes': 312,
		'comments': 56,
	},
	{
		'dish': 'Satay',
		'stall': 'Lau Pa Sat Satay Street',
		'hawker_centre': 'Lau Pa Sat',
		'location': 'Central',
		'rating': 3.5,
		'sentiment': 'Negative',
		'price_range': '$$$',
		'review': 'Touristy pricing and sauce is overly sweet. There are better neighborhood stalls.',
		'author': 'LocalEats',
		'created_at': '1 day ago',
		'likes': 89,
		'comments': 23,
	},
	{
		'dish': 'Hokkien Mee',
		'stall': 'Fried Hokkien Prawn Mee',
		'hawker_centre': 'Tiong Bahru Market',
		'location': 'South',
		'rating': 4.7,
		'sentiment': 'Positive',
		'price_range': '$$',
		'review': 'Great prawn stock depth and sambal on the side ties everything together.',
		'author': 'PrawnMeeFanatic',
		'created_at': '4 days ago',
		'likes': 401,
		'comments': 67,
	},
]

TRENDING = [
	('Best Hainanese chicken rice in Toa Payoh', '3.2k opinions'),
	('Char kway teow: wok hei vs health concerns', '2.8k opinions'),
	('Is Lau Pa Sat overrated for tourists?', '2.1k opinions'),
	('Maxwell Food Centre vs Chinatown Complex', '1.9k opinions'),
]


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

	if selected['price_ranges']:
		filtered = [row for row in filtered if row['price_range'] in selected['price_ranges']]

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
			'trending': TRENDING,
			'quick_queries': [
				'Where to find the best laksa?',
				'Is Tian Tian chicken rice worth the queue?',
				'Halal options at Bedok hawker centre',
			],
			'dish_types': ['Chicken Rice', 'Noodles', 'Seafood', 'BBQ & Satay', 'Drinks & Desserts', 'Local Favorites'],
			'stats': [
				('10K+', 'Reviews & Opinions'),
				('120+', 'Hawker Centres'),
				('500+', 'Signature Dishes'),
			],
		},
	)


def search_results(request: HttpRequest) -> HttpResponse:
	page = max(1, int(request.GET.get('page', '1') or '1'))
	page_size = 30

	selected = {
		'q': request.GET.get('q', '').strip(),
		'locations': request.GET.getlist('location'),
		'sentiments': request.GET.getlist('sentiment'),
		'price_ranges': request.GET.getlist('price'),
		'min_rating': int(request.GET.get('rating', '0')),
	}

	search_payload = search_opinions(
		query=selected['q'],
		locations=selected['locations'],
		sentiments=selected['sentiments'],
		price_ranges=selected['price_ranges'],
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
		spellcheck_suggestions = []
		corrected_query = ''
	else:
		results = search_payload['docs']
		total_count = search_payload['total']
		spellcheck_suggestions = search_payload.get('spellcheck_suggestions', [])
		corrected_query = ''

		if not results and selected['q'] and spellcheck_suggestions:
			corrected_query = spellcheck_suggestions[0]
			corrected_payload = search_opinions(
				query=corrected_query,
				locations=selected['locations'],
				sentiments=selected['sentiments'],
				price_ranges=selected['price_ranges'],
				min_rating=selected['min_rating'],
				page=page,
				page_size=page_size,
			)
			if corrected_payload:
				results = corrected_payload['docs']
				total_count = corrected_payload['total']
				spellcheck_suggestions = corrected_payload.get('spellcheck_suggestions', spellcheck_suggestions)

	total_pages = max(1, math.ceil(total_count / page_size))
	page = min(page, total_pages)

	query_params = request.GET.copy()
	query_params.pop('page', None)

	context = {
		'query': selected['q'],
		'corrected_query': corrected_query,
		'results': results,
		'result_count': total_count,
		'selected': selected,
		'current_page': page,
		'total_pages': total_pages,
		'has_prev': page > 1,
		'has_next': page < total_pages,
		'prev_page': page - 1,
		'next_page': page + 1,
		'query_string': query_params.urlencode(),
		'spellcheck_suggestions': spellcheck_suggestions,
		'locations': ['Central', 'East', 'West', 'North', 'South', 'Unknown'],
		'sentiments': ['Positive', 'Neutral', 'Negative'],
		'price_ranges': ['$', '$$', '$$$', '$$$$'],
	}
	return render(request, 'opinions/search_results.html', context)
