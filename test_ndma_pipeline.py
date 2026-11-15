import csv
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_module("run_latest_under_test", "run_latest.py")
extractor = load_module("extract_segments_under_test", "extract_segments.py")


def segment(filename, segment_id, text="New advisory text"):
    return {
        "segment_id": segment_id,
        "pdf_filename": filename,
        "advisory_issue_date": "12 November 2026",
        "hazard_date_range": "2026-11-12",
        "section": "Forecast",
        "section1_was_image": False,
        "source_method": "digital_text",
        "segment_text": text,
        "direct_locations": "Swat",
        "implied_locations": "",
        "matched_region": "",
        "location_match_type": "direct",
        "weak_label_hint": "2",
        "label": "",
        "annotator_1_label": "",
        "annotator_2_label": "",
        "label_notes": "",
    }


def report(filename):
    return {
        "pdf_filename": filename,
        "advisory_issue_date": "12 November 2026",
        "hazard_date_range": "2026-11-12",
        "section1_was_image": False,
        "total_pages": 1,
        "usable_segments_count": 1,
        "direct_locations_found": "Swat",
        "implied_locations_found": "",
        "status_and_issues": "Standard text advisory parsed cleanly",
    }


class NdmaPipelineTests(unittest.TestCase):
    def test_new_pdf_is_saved_and_incrementally_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            previous = os.getcwd()
            os.chdir(project)
            try:
                (project / "AdvisoryPDFs").mkdir()
                content = b"%PDF-new"
                with mock.patch.object(
                    runner, "find_existing_copy", return_value=None
                ):
                    path, digest = runner.save_latest_pdf(
                        project, "https://ndma.gov.pk/new.pdf", content
                    )
                self.assertEqual(path.parent.name, "AdvisoryPDFs")
                self.assertEqual(path.read_bytes(), content)
                self.assertEqual(digest, hashlib.sha256(content).hexdigest())

                with mock.patch.object(
                    extractor,
                    "process_single_pdf",
                    return_value=([segment(path.name, "new_01")], report(path.name)),
                ):
                    extractor.run_incremental(str(path))
                self.assertIn(path.name, (project / "run_report.csv").read_text(encoding="utf-8-sig"))
            finally:
                os.chdir(previous)

    def test_processed_duplicate_is_not_appended(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            advisory_dir = project / "AdvisoryPDFs"
            advisory_dir.mkdir()
            content = b"%PDF-duplicate"
            existing = advisory_dir / "old.pdf"
            existing.write_bytes(content)
            (project / "run_report.csv").write_text(
                "pdf_filename,advisory_issue_date,hazard_date_range,section1_was_image,total_pages,usable_segments_count,direct_locations_found,implied_locations_found,status_and_issues\n"
                "old.pdf,date,date,False,1,0,,,,\n",
                encoding="utf-8-sig",
            )
            path, digest = runner.save_latest_pdf(
                project, "https://ndma.gov.pk/latest.pdf", content
            )
            self.assertEqual(path, existing)
            self.assertTrue(runner.was_processed(project, path, digest))

    def test_filename_collision_gets_distinct_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            advisory_dir = project / "AdvisoryPDFs"
            advisory_dir.mkdir()
            existing = advisory_dir / "latest.pdf"
            existing.write_bytes(b"%PDF-old")
            path, _ = runner.save_latest_pdf(
                project, "https://ndma.gov.pk/latest.pdf", b"%PDF-new"
            )
            self.assertNotEqual(path, existing)
            self.assertEqual(existing.read_bytes(), b"%PDF-old")
            self.assertEqual(path.read_bytes(), b"%PDF-new")

    def test_failed_processing_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            os.chdir(directory)
            try:
                pdf = Path("AdvisoryPDFs/retry.pdf")
                pdf.parent.mkdir()
                pdf.write_bytes(b"%PDF-retry")
                with mock.patch.object(
                    extractor,
                    "process_single_pdf",
                    side_effect=RuntimeError("extract failed"),
                ):
                    with self.assertRaises(RuntimeError):
                        extractor.run_incremental(str(pdf))
                self.assertFalse(Path("run_report.csv").exists())
                with mock.patch.object(
                    extractor,
                    "process_single_pdf",
                    return_value=([segment("retry.pdf", "retry_01")], report("retry.pdf")),
                ):
                    extractor.run_incremental(str(pdf))
                self.assertTrue(Path("run_report.csv").exists())
            finally:
                os.chdir(previous)

    def test_annotations_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            os.chdir(directory)
            try:
                old = segment("old.pdf", "old_01", "Existing annotated text")
                old["label"] = "2"
                old["label_notes"] = "keep this"
                with open("all_segments.csv", "w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.DictWriter(file, fieldnames=extractor.SEGMENT_FIELDS)
                    writer.writeheader()
                    writer.writerow(old)
                canonical = {
                    "canonical_segment_id": "old_01",
                    "segment_text": old["segment_text"],
                    "occurrence_count": "1",
                    "appears_in_pdfs": "old.pdf",
                    "appears_in_segment_ids": "old_01",
                    "direct_locations": "Swat",
                    "implied_locations": "",
                    "matched_region": "",
                    "location_match_type": "direct",
                    "weak_label_hint": "2",
                    "is_in_kappa_sample": "True",
                    "label": "2",
                    "annotator_1_label": "2",
                    "annotator_2_label": "",
                    "label_notes": "canonical note",
                }
                with open("labeling_canonical.csv", "w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.DictWriter(file, fieldnames=canonical.keys())
                    writer.writeheader()
                    writer.writerow(canonical)
                with mock.patch.object(
                    extractor,
                    "process_single_pdf",
                    return_value=([segment("new.pdf", "new_01")], report("new.pdf")),
                ):
                    extractor.run_incremental("new.pdf")
                rows = extractor._read_csv_rows("all_segments.csv", extractor.SEGMENT_FIELDS)
                old_row = next(row for row in rows if row["segment_id"] == "old_01")
                self.assertEqual(old_row["label"], "2")
                canonical_text = Path("labeling_canonical.csv").read_text(encoding="utf-8-sig")
                self.assertIn("canonical note", canonical_text)
                self.assertIn(",True,2,2,", canonical_text)
            finally:
                os.chdir(previous)

    def test_remaining_pdf_is_not_part_of_new_download_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            remaining = project / "remainingPDFs"
            remaining.mkdir()
            content = b"%PDF-legacy"
            legacy = remaining / "legacy.pdf"
            legacy.write_bytes(content)
            path, digest = runner.save_latest_pdf(
                project, "https://ndma.gov.pk/new.pdf", b"%PDF-new"
            )
            self.assertEqual(path.name, "new.pdf")
            self.assertTrue(legacy.exists())
            self.assertFalse(runner.was_processed(project, path, digest))


if __name__ == "__main__":
    unittest.main()
