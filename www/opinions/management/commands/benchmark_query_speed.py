from __future__ import annotations

import statistics
import time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

from django.core.management.base import BaseCommand, CommandError
from django.test import RequestFactory

from opinions.views import search_results


DEFAULT_QUERIES = [
	'laksa',
	'chicken rice',
	'satay',
	'fish soup',
	'prawn noodle',
	'fried rice',
	'wanton noodle',
	'mutton soup',
	'char kway teow',
	'dessert',
	'beef noodle',
	'rojak',
	'curry puff',
	'bee hoon',
	'kway teow',
	'sugarcane',
	'coffee',
	'mee rebus',
	'mee soto',
	'hor fun',
	'otah',
	'kangkong',
	'bak chor mee',
	'fish ball',
	'noodles',
	'lontong',
	'beehoon',
	'teh tarik',
	'ayam penyet',
	'broth',
]


class Command(BaseCommand):
	help = 'Benchmark 30 search queries and plot their response times.'

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			'--output',
			default='benchmark_query_speed.png',
			help='Path to the PNG file that will contain the latency plot.',
		)
		parser.add_argument(
			'--queries',
			default='',
			help='Optional comma-separated list of queries. Defaults to 30 built-in search terms.',
		)

	def handle(self, *args, **options) -> None:
		output_path = Path(options['output']).expanduser().resolve()
		queries = [query.strip() for query in str(options['queries']).split(',') if query.strip()]
		if not queries:
			queries = DEFAULT_QUERIES

		if len(queries) < 30:
			repeats = (30 + len(queries) - 1) // len(queries)
			queries = (queries * repeats)[:30]
		else:
			queries = queries[:30]

		factory = RequestFactory()
		elapsed_ms: list[float] = []
		labels: list[str] = []

		self.stdout.write(self.style.NOTICE(f'Running {len(queries)} search queries...'))
		for index, query in enumerate(queries, start=1):
			request = factory.get('/search/', {'q': query})
			started_at = time.perf_counter()
			response = search_results(request)
			elapsed = round((time.perf_counter() - started_at) * 1000, 1)
			if response.status_code != 200:
				raise CommandError(f'Query {index} returned HTTP {response.status_code}: {query}')
			elapsed_ms.append(elapsed)
			labels.append(query)
			self.stdout.write(f'{index:02d}. {query:<18} {elapsed:>7.1f} ms')

		avg_ms = round(statistics.mean(elapsed_ms), 1)
		min_ms = round(min(elapsed_ms), 1)
		max_ms = round(max(elapsed_ms), 1)
		median_ms = round(statistics.median(elapsed_ms), 1)

		output_path.parent.mkdir(parents=True, exist_ok=True)
		plt.figure(figsize=(14, 6))
		positions = list(range(1, len(elapsed_ms) + 1))
		bars = plt.bar(positions, elapsed_ms, color='#f25a07', alpha=0.85)
		plt.plot(positions, elapsed_ms, color='#2d3a49', linewidth=1.5, marker='o', markersize=4)
		plt.xticks(positions, [str(i) for i in positions], fontsize=9)
		plt.ylabel('Response time (ms)')
		plt.xlabel('Query #')
		plt.title('MakanMetrics query speed across 30 searches')
		plt.grid(axis='y', linestyle='--', alpha=0.25)
		for bar, value in zip(bars, elapsed_ms):
			plt.text(bar.get_x() + bar.get_width() / 2, value + 0.5, f'{value:.1f}', ha='center', va='bottom', fontsize=8)
		plt.figtext(
			0.01,
			0.01,
			f'avg {avg_ms} ms | median {median_ms} ms | min {min_ms} ms | max {max_ms} ms',
			ha='left',
			fontsize=10,
			color='#4b5c70',
		)
		plt.tight_layout(rect=[0, 0.05, 1, 1])
		plt.savefig(output_path, dpi=160, bbox_inches='tight')
		plt.close()

		self.stdout.write(self.style.SUCCESS(f'Saved plot to {output_path}'))
		self.stdout.write(
			self.style.SUCCESS(
				f'Average {avg_ms} ms | Median {median_ms} ms | Min {min_ms} ms | Max {max_ms} ms'
			)
		)