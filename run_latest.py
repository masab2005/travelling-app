"""Download the newest NDMA advisory PDF, then run the existing extractor."""

from __future__ import annotations

import hashlib
import html.parser
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SITE_URL = "https://ndma.gov.pk/advisories"
MAX_PDF_BYTES = 40 * 1024 * 1024
USER_AGENT = "TravellingAppAdvisoryFetcher/1.0 (official NDMA advisories page)"


class AdvisoryLinks(html.parser.HTMLParser):
    """Collect PDF links in the order they appear on the advisories page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pdf_urls: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._anchor_href = href.strip()
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._anchor_href is None:
            return
        link_text = " ".join(" ".join(self._anchor_text).split())
        target = urllib.parse.urlparse(self._anchor_href)
        if target.path.lower().endswith(".pdf") and ("view" in link_text.lower() or not link_text):
            self.pdf_urls.append(self._anchor_href)
        self._anchor_href = None
        self._anchor_text = []


def fetch_latest_pdf_url() -> str:
    request = urllib.request.Request(SITE_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        page_url = response.geturl()
        page_host = (urllib.parse.urlparse(page_url).hostname or "").lower()
        if page_host != "ndma.gov.pk" and not page_host.endswith(".ndma.gov.pk"):
            raise RuntimeError(f"Unexpected redirect away from NDMA: {page_url}")
        page = response.read(8 * 1024 * 1024 + 1)
    if len(page) > 8 * 1024 * 1024:
        raise RuntimeError("NDMA advisories page exceeded the 8 MiB safety limit.")

    parser = AdvisoryLinks()
    parser.feed(page.decode("utf-8", errors="replace"))
    if not parser.pdf_urls:
        raise RuntimeError("No PDF advisory links were found on the NDMA page.")

    latest_url = urllib.parse.urljoin(page_url, parser.pdf_urls[0])
    parsed = urllib.parse.urlparse(latest_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or (host != "ndma.gov.pk" and not host.endswith(".ndma.gov.pk")):
        raise RuntimeError(f"The newest advisory link is not a trusted NDMA HTTPS URL: {latest_url}")
    return latest_url


def download_pdf(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        final_url = response.geturl()
        host = (urllib.parse.urlparse(final_url).hostname or "").lower()
        if host != "ndma.gov.pk" and not host.endswith(".ndma.gov.pk"):
            raise RuntimeError(f"PDF download redirected away from NDMA: {final_url}")
        content = response.read(MAX_PDF_BYTES + 1)
    if len(content) > MAX_PDF_BYTES:
        raise RuntimeError("The advisory PDF exceeded the 40 MiB safety limit.")
    if not content.startswith(b"%PDF-"):
        raise RuntimeError("NDMA's latest advisory link did not return a valid PDF file.")
    return content, final_url


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_existing_copy(project_dir: Path, digest: str) -> Path | None:
    for folder_name in ("AdvisoryPDFs", "remainingPDFs"):
        folder = project_dir / folder_name
        if not folder.is_dir():
            continue
        for path in folder.glob("*.pdf"):
            try:
                file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            if file_hash == digest:
                return path
    return None


def save_latest_pdf(project_dir: Path, url: str, content: bytes) -> Path:
    digest = sha256(content)
    existing = find_existing_copy(project_dir, digest)
    if existing:
        print(f"Latest advisory is already present: {existing.relative_to(project_dir)}")
        return existing

    output_dir = project_dir / "remainingPDFs"
    output_dir.mkdir(parents=True, exist_ok=True)
    url_name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", url_name).strip("._")
    if not safe_name.lower().endswith(".pdf"):
        safe_name = "latest_ndma_advisory.pdf"

    destination = output_dir / safe_name
    if destination.exists():
        destination = output_dir / f"{Path(safe_name).stem}_{digest[:10]}.pdf"
    temporary = destination.with_suffix(destination.suffix + ".part")
    try:
        with temporary.open("wb") as pdf_file:
            pdf_file.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Downloaded latest advisory: {destination.relative_to(project_dir)}")
    return destination


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    extractor = project_dir / "extract_segments.py"
    if not extractor.is_file():
        print(f"Extractor was not found: {extractor}", file=sys.stderr)
        return 1

    try:
        pdf_url = fetch_latest_pdf_url()
        print(f"Latest advisory PDF: {pdf_url}")
        pdf_content, final_url = download_pdf(pdf_url)
        if final_url != pdf_url:
            print(f"PDF redirected to: {final_url}")
        save_latest_pdf(project_dir, final_url, pdf_content)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError) as error:
        print(f"Could not fetch the latest NDMA advisory: {error}", file=sys.stderr)
        return 1

    print("Running extract_segments.py over the existing and downloaded PDF folders...")
    try:
        result = subprocess.run(
            [sys.executable, str(extractor), "--dirs", "AdvisoryPDFs", "remainingPDFs"],
            cwd=project_dir,
            check=False,
        )
    except OSError as error:
        print(f"Could not start extract_segments.py: {error}", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
