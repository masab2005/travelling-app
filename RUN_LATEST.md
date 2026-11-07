# Latest NDMA advisory workflow

On Windows, run `run_latest.cmd` from this folder, or run `python run_latest.py`.
The runner takes the first PDF listed on the official NDMA advisories page,
downloads it into `remainingPDFs` unless the identical PDF is already present,
then runs `extract_segments.py` across both `AdvisoryPDFs` and `remainingPDFs`.
The extractor updates `all_segments.csv`, `run_report.csv`, and
`labeling_canonical.csv` as it normally does.

Install the extractor's PyMuPDF dependency once:

```powershell
python -m pip install -r requirements.txt
```

The downloader uses Python's standard library. It checks the NDMA HTTPS host,
validates the downloaded PDF signature, and saves downloads atomically.
