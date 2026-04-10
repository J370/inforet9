# HawkerOpinions Django + Solr (CSV Wired)

This project is wired to index and search opinions from:

- ../Q5 Sarcasm detection/final_dataset_with_sarcasm_merged.csv

## 1) Start Solr and Create Core

If Solr is installed locally:

```bash
solr start
solr create -c opinions
```

If `solr` CLI is not available, use Docker:

```bash
docker run --name hawker-solr -p 8983:8983 -d solr:9
# wait a few seconds for startup
curl "http://localhost:8983/solr/admin/cores?action=CREATE&name=opinions&configSet=_default"
```

## 2) Import CSV into Solr

From this `www` directory:

```bash
python3 manage.py solr_import_csv --core opinions
```

Notes:

- The command automatically adds required schema fields.
- Existing docs are replaced by default.
- Use `--append` to keep existing docs and add more.

## 3) Run Django with Solr Enabled

```bash
ENABLE_SOLR=true SOLR_BASE_URL=http://localhost:8983/solr SOLR_CORE=opinions python3 manage.py runserver
```

Open: http://127.0.0.1:8000

## 4) Optional Solr Smoke Test

```bash
curl "http://localhost:8983/solr/opinions/select?q=*:*&rows=3&wt=json"
```

## 5) Reindex Anytime

```bash
python3 manage.py solr_import_csv --core opinions
```
