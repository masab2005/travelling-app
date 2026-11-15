# Latest NDMA advisory workflow

On Windows, run `run_latest.cmd` from this folder, or run `python run_latest.py`.
The runner takes the first PDF listed on the official NDMA advisories page,
downloads it directly into `AdvisoryPDFs` without overwriting a filename
collision, then runs `extract_segments.py` for that PDF only. The extractor
appends to `all_segments.csv`, `run_report.csv`, and `labeling_canonical.csv`
without reprocessing older PDFs or removing annotations. A processing manifest
records pending and successful PDFs so failed processing can be retried safely.
The retired `remainingPDFs` folder is no longer read or written by the runner.
Move any legacy PDFs from it into `AdvisoryPDFs` once before deleting that
folder.

Install the extractor's PyMuPDF dependency once:

```powershell
python -m pip install -r requirements.txt
```

The downloader uses Python's standard library. It checks the NDMA HTTPS host,
validates the downloaded PDF signature, and saves downloads atomically.
