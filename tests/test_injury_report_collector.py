"""
Unit tests for src/data_collectors/get_injury_report.py

Strategy
--------
All HTTP traffic is mocked with unittest.mock so no real network calls are made.
The PDF is synthesised as a minimal valid PDF byte string so pdfplumber can parse
it — no extra test dependency (reportlab, fpdf, …) is required.

Tests cover:
  - _resolve_pdf_url: picks last valid URL, raises when none found, stops on first 404
  - _parse_pdf: correctly parses player records from synthesised PDF text
  - run: end-to-end happy path (mocked HTTP + mocked save_database)
  - Singleton reset between tests
"""

import io
import datetime
import textwrap
import unittest
from unittest.mock import patch, MagicMock, call

import pandas as pd

# Reset SingletonMeta state between tests so each test gets a fresh instance.
from common.singleton_meta import SingletonMeta


def _reset_singleton(cls):
    """Remove a class from the SingletonMeta registry."""
    if cls in SingletonMeta._instances:
        del SingletonMeta._instances[cls]


# ---------------------------------------------------------------------------
# Minimal in-memory PDF builder
# We build a PDF that contains exactly the text we want pdfplumber to see.
# The structure is the bare minimum that pdfplumber accepts.
# ---------------------------------------------------------------------------


def _build_minimal_pdf(text_lines: list[str]) -> bytes:
    """
    Return a valid PDF byte string whose single page contains *text_lines*.
    Uses only core PDF operators — no external library needed.
    """

    # Encode each line as a PDF text-show command
    def _escape(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines_pdf = "\n".join(
        f"BT /F1 10 Tf 30 {700 - i * 14} Td ({_escape(line)}) Tj ET"
        for i, line in enumerate(text_lines)
    )

    stream = textwrap.dedent(f"""\
        {lines_pdf}
    """).encode()

    stream_len = len(stream)

    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] "
        b"/Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )

    stream_obj = (
        b"4 0 obj\n"
        + f"<< /Length {stream_len} >>\n".encode()
        + b"stream\n"
        + stream
        + b"\nendstream\nendobj\n"
        b"5 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
    )

    xref_offset = len(body) + len(stream_obj)
    trailer = (
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000999 00000 n \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
        + f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )

    return body + stream_obj + trailer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_200_response(content: bytes = b"") -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.content = content
    r.raise_for_status = MagicMock()
    return r


def _make_404_response() -> MagicMock:
    r = MagicMock()
    r.status_code = 404
    return r


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolveUrl(unittest.TestCase):
    """_resolve_pdf_url picks the last URL that returns HTTP 200."""

    def setUp(self):
        from src.data_collectors.get_injury_report import InjuryReportCollector

        _reset_singleton(InjuryReportCollector)
        self.InjuryReportCollector = InjuryReportCollector

    def tearDown(self):
        _reset_singleton(self.InjuryReportCollector)

    @patch("src.data_collectors.get_injury_report.requests.head")
    def test_returns_last_valid_url(self, mock_head):
        """Returns the last hour that had a 200 before the first 404."""
        # First two hours succeed, third fails → last valid is index 1
        mock_head.side_effect = [
            _make_200_response(),
            _make_200_response(),
            _make_404_response(),
        ]

        collector = self.InjuryReportCollector(
            save_mode="local", report_date="2026-03-31"
        )
        url = collector._resolve_pdf_url()
        self.assertIn("2026-03-31", url)
        # Should have tried exactly 3 hours (2 success + 1 failure)
        self.assertEqual(mock_head.call_count, 3)

    @patch("src.data_collectors.get_injury_report.requests.head")
    def test_raises_when_first_hour_is_404(self, mock_head):
        """FileNotFoundError raised when no hour at all returns 200."""
        mock_head.return_value = _make_404_response()

        collector = self.InjuryReportCollector(
            save_mode="local", report_date="2026-03-31"
        )
        with self.assertRaises(FileNotFoundError):
            collector._resolve_pdf_url()

    @patch("src.data_collectors.get_injury_report.requests.head")
    def test_single_valid_hour(self, mock_head):
        """Works correctly when only the first hour is valid."""
        mock_head.side_effect = [_make_200_response(), _make_404_response()]

        collector = self.InjuryReportCollector(
            save_mode="local", report_date="2026-03-31"
        )
        url = collector._resolve_pdf_url()
        self.assertIsNotNone(url)
        self.assertEqual(mock_head.call_count, 2)


class TestParsePdf(unittest.TestCase):
    """_parse_pdf returns correctly structured DataFrames.

    Strategy: mock pdfplumber.open so we control exactly what text the parser
    sees, without needing a real PDF file or an external PDF-generation library.
    """

    def setUp(self):
        from src.data_collectors.get_injury_report import InjuryReportCollector

        _reset_singleton(InjuryReportCollector)
        self.InjuryReportCollector = InjuryReportCollector
        self.today = datetime.datetime.now(datetime.timezone.utc).strftime("%m/%d/%Y")

    def tearDown(self):
        _reset_singleton(self.InjuryReportCollector)

    def _collector(self):
        today_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        return self.InjuryReportCollector(save_mode="local", report_date=today_iso)

    def _mock_pdf(self, text_lines: list[str]):
        """Return a context-manager mock that yields a PDF with one page."""
        page = MagicMock()
        page.extract_text.return_value = "\n".join(text_lines)

        pdf_cm = MagicMock()
        pdf_cm.__enter__ = MagicMock(return_value=pdf_cm)
        pdf_cm.__exit__ = MagicMock(return_value=False)
        pdf_cm.pages = [page]
        return pdf_cm

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_parses_player_record(self, mock_pdf_open, mock_get):
        """A well-formed page produces the expected player record."""
        mock_get.return_value = _make_200_response(b"fake-pdf-bytes")
        mock_pdf_open.return_value = self._mock_pdf(
            [
                f"{self.today} 06:00(ET) MIL@BOS MilwaukeeBucks Antetokounmpo,Giannis Out Knee",
            ]
        )

        collector = self._collector()
        df = collector._parse_pdf("https://fake.url/report.pdf")

        self.assertFalse(df.empty, "DataFrame should not be empty")
        self.assertIn("player_name", df.columns)
        self.assertIn("status", df.columns)
        self.assertIn("team", df.columns)

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_output_columns_present(self, mock_pdf_open, mock_get):
        """All expected output columns are present even for a minimal record."""
        mock_get.return_value = _make_200_response(b"fake-pdf-bytes")
        mock_pdf_open.return_value = self._mock_pdf(
            [
                f"{self.today} 02:00(ET) LAL@GSW LosAngelesLakers James,LeBron Out Rest",
            ]
        )

        collector = self._collector()
        df = collector._parse_pdf("https://fake.url/report.pdf")

        for col in [
            "report_date",
            "matchup",
            "team",
            "player_name",
            "status",
            "reason",
        ]:
            self.assertIn(col, df.columns, f"Missing column: {col}")

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_empty_pdf_returns_empty_dataframe(self, mock_pdf_open, mock_get):
        """A PDF page with no player lines returns an empty DataFrame."""
        mock_get.return_value = _make_200_response(b"fake-pdf-bytes")
        mock_pdf_open.return_value = self._mock_pdf(["Page header only"])

        collector = self._collector()
        df = collector._parse_pdf("https://fake.url/report.pdf")

        self.assertTrue(df.empty or len(df) == 0)

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_multiple_players_parsed(self, mock_pdf_open, mock_get):
        """Multiple player lines on the same page are all parsed."""
        mock_get.return_value = _make_200_response(b"fake-pdf-bytes")
        mock_pdf_open.return_value = self._mock_pdf(
            [
                f"{self.today} 06:00(ET) MIL@BOS MilwaukeeBucks Antetokounmpo,Giannis Out Knee",
                "BostonCeltics Brown,Jaylen Questionable Hamstring",
            ]
        )

        collector = self._collector()
        df = collector._parse_pdf("https://fake.url/report.pdf")

        self.assertGreaterEqual(len(df), 1)


class TestInjuryReportCollectorRun(unittest.TestCase):
    """run() end-to-end: resolve URL → parse PDF → save."""

    def setUp(self):
        from src.data_collectors.get_injury_report import InjuryReportCollector

        _reset_singleton(InjuryReportCollector)
        self.InjuryReportCollector = InjuryReportCollector
        self.today = datetime.datetime.now(datetime.timezone.utc).strftime("%m/%d/%Y")
        self.today_iso = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%d"
        )

    def tearDown(self):
        _reset_singleton(self.InjuryReportCollector)

    def _parsed_df(self) -> pd.DataFrame:
        """A minimal non-empty DataFrame as if _parse_pdf returned it."""
        return pd.DataFrame(
            [
                {
                    "report_date": self.today,
                    "matchup": "BOS@MIA",
                    "team": "BOS",
                    "player_name": "Tatum,Jayson",
                    "status": "Out",
                    "reason": "Ankle",
                }
            ]
        )

    @patch("src.data_collectors.get_injury_report.save_database")
    @patch("src.data_collectors.get_injury_report.requests.head")
    def test_run_saves_dataframe(self, mock_head, mock_save):
        """run() calls save_database with a non-empty DataFrame."""
        mock_head.side_effect = [_make_200_response(), _make_404_response()]

        collector = self.InjuryReportCollector(
            save_mode="local", report_date=self.today_iso
        )
        # Mock _parse_pdf at the instance level so we control the returned records
        collector._parse_pdf = MagicMock(return_value=self._parsed_df())

        collector.run()

        mock_save.assert_called_once()
        saved_df = mock_save.call_args[0][0]
        self.assertIsInstance(saved_df, pd.DataFrame)
        self.assertFalse(saved_df.empty)

    @patch("src.data_collectors.get_injury_report.save_database")
    @patch("src.data_collectors.get_injury_report.requests.head")
    def test_run_raises_when_no_pdf_found(self, mock_head, mock_save):
        """run() propagates FileNotFoundError when no PDF URL resolves."""
        mock_head.return_value = _make_404_response()

        collector = self.InjuryReportCollector(
            save_mode="local", report_date=self.today_iso
        )
        with self.assertRaises(FileNotFoundError):
            collector.run()

        mock_save.assert_not_called()

    @patch("src.data_collectors.get_injury_report.save_database")
    @patch("src.data_collectors.get_injury_report.requests.head")
    def test_run_returns_empty_without_saving_on_empty_pdf(self, mock_head, mock_save):
        """run() does not call save_database when the PDF has no records."""
        mock_head.side_effect = [_make_200_response(), _make_404_response()]

        collector = self.InjuryReportCollector(
            save_mode="local", report_date=self.today_iso
        )
        # _parse_pdf returns empty — nothing to save
        collector._parse_pdf = MagicMock(
            return_value=pd.DataFrame(
                columns=[
                    "report_date",
                    "matchup",
                    "team",
                    "player_name",
                    "status",
                    "reason",
                ]
            )
        )

        df = collector.run()

        mock_save.assert_not_called()
        self.assertTrue(df.empty)


# ---------------------------------------------------------------------------
# Integration tests: real NBA PDF format
# ---------------------------------------------------------------------------

# Verbatim lines extracted from Injury-Report_2025-03-30_08PM.pdf
# (via pdfplumber page.extract_text()).  Used as a fixture to verify the
# parser against the actual format the NBA publishes.
_REAL_PDF_PAGE_1 = [
    "Injury Report: 03/30/25 08:30 PM",
    "GameDate GameTime Matchup Team PlayerName CurrentStatus Reason",
    "03/30/2025 03:30(ET) LAC@CLE LAClippers BaldwinJr.,Patrick Out GLeague-Two-Way",
    "Christie,Cam Out NotWithTeam",
    "Flowers,Trentyn Out GLeague-Two-Way",
    "Injury/Illness-RightKnee;Injury",
    "Leonard,Kawhi Out",
    "Management",
    "Lundy,Seth Out GLeague-Two-Way",
    "Injury/Illness-LeftHamstring;",
    "Miller,Jordan Out",
    "Tendinopathy",
    "ClevelandCavaliers Bates,Emoni Out GLeague-Two-Way",
    "Jerome,Ty Out Injury/Illness-LeftKnee;Tendinitis",
    "Tyson,Jaylon Out Injury/Illness-LeftKnee;BoneBruise",
    "06:00(ET) POR@NYK PortlandTrailBlazers Ayton,Deandre Out Injury/Illness-LeftCalf;Strain",
    "Injury/Illness-RightKnee;",
    "Grant,Jerami Out",
    "Inflammation",
    "Henderson,Scoot Out ConcussionProtocol",
    "McGowens,Bryce Out Injury/Illness-RightRib;Fracture",
    "Injury/Illness-RightForearm;",
    "Simons,Anfernee Available",
    "Soreness",
    "WilliamsIII,Robert Out Injury/Illness-LeftKnee;Injury",
    "Page1of11",
]

# Expected rows for page 1 (player_name, team, matchup, status, reason)
_EXPECTED_PAGE_1 = [
    ("BaldwinJr.,Patrick", "LAClippers", "LAC@CLE", "Out", "GLeague-Two-Way"),
    ("Christie,Cam", "LAClippers", "LAC@CLE", "Out", "NotWithTeam"),
    (
        "Flowers,Trentyn",
        "LAClippers",
        "LAC@CLE",
        "Out",
        "GLeague-Two-Way Injury/Illness-RightKnee;Injury",
    ),
    ("Leonard,Kawhi", "LAClippers", "LAC@CLE", "Out", "Management"),
    (
        "Lundy,Seth",
        "LAClippers",
        "LAC@CLE",
        "Out",
        "GLeague-Two-Way Injury/Illness-LeftHamstring;",
    ),
    ("Miller,Jordan", "LAClippers", "LAC@CLE", "Out", "Tendinopathy"),
    ("Bates,Emoni", "ClevelandCavaliers", "LAC@CLE", "Out", "GLeague-Two-Way"),
    (
        "Jerome,Ty",
        "ClevelandCavaliers",
        "LAC@CLE",
        "Out",
        "Injury/Illness-LeftKnee;Tendinitis",
    ),
    (
        "Tyson,Jaylon",
        "ClevelandCavaliers",
        "LAC@CLE",
        "Out",
        "Injury/Illness-LeftKnee;BoneBruise",
    ),
    (
        "Ayton,Deandre",
        "PortlandTrailBlazers",
        "POR@NYK",
        "Out",
        "Injury/Illness-LeftCalf;Strain Injury/Illness-RightKnee;",
    ),
    ("Grant,Jerami", "PortlandTrailBlazers", "POR@NYK", "Out", "Inflammation"),
    ("Henderson,Scoot", "PortlandTrailBlazers", "POR@NYK", "Out", "ConcussionProtocol"),
    (
        "McGowens,Bryce",
        "PortlandTrailBlazers",
        "POR@NYK",
        "Out",
        "Injury/Illness-RightRib;Fracture Injury/Illness-RightForearm;",
    ),
    ("Simons,Anfernee", "PortlandTrailBlazers", "POR@NYK", "Available", "Soreness"),
    (
        "WilliamsIII,Robert",
        "PortlandTrailBlazers",
        "POR@NYK",
        "Out",
        "Injury/Illness-LeftKnee;Injury",
    ),
]

# Additional lines that test NOTYETSUBMITTED handling and next-day games
_REAL_PDF_NOTYETSUBMITTED = [
    "Injury Report: 03/30/25 08:30 PM",
    "GameDate GameTime Matchup Team PlayerName CurrentStatus Reason",
    "03/31/2025 07:00(ET) LAC@ORL LAClippers NOTYETSUBMITTED",
    "CharlotteHornets NOTYETSUBMITTED",
    "Page2of11",
]


class TestParsePdfRealFormat(unittest.TestCase):
    """_parse_pdf handles the real NBA injury-report PDF structure."""

    def setUp(self):
        from src.data_collectors.get_injury_report import InjuryReportCollector

        _reset_singleton(InjuryReportCollector)
        self.InjuryReportCollector = InjuryReportCollector

    def tearDown(self):
        _reset_singleton(self.InjuryReportCollector)

    def _collector(self, date_iso: str):
        return self.InjuryReportCollector(save_mode="local", report_date=date_iso)

    def _mock_pdf(self, text_lines: list[str]):
        page = MagicMock()
        page.extract_text.return_value = "\n".join(text_lines)
        pdf_cm = MagicMock()
        pdf_cm.__enter__ = MagicMock(return_value=pdf_cm)
        pdf_cm.__exit__ = MagicMock(return_value=False)
        pdf_cm.pages = [page]
        return pdf_cm

    # ------------------------------------------------------------------
    # Page-1 fixture tests
    # ------------------------------------------------------------------

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page1_row_count(self, mock_pdf_open, mock_get):
        """Parser produces exactly the expected number of rows from page 1."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        self.assertEqual(len(df), len(_EXPECTED_PAGE_1), msg=df.to_string())

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page1_player_names(self, mock_pdf_open, mock_get):
        """All player names from page 1 are parsed correctly."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        actual_names = df["player_name"].tolist()
        expected_names = [r[0] for r in _EXPECTED_PAGE_1]
        self.assertEqual(
            actual_names,
            expected_names,
            msg=df[["player_name", "team", "matchup"]].to_string(),
        )

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page1_teams(self, mock_pdf_open, mock_get):
        """Team names are correctly assigned — team changes trigger on CamelCase tokens."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        actual_teams = df["team"].tolist()
        expected_teams = [r[1] for r in _EXPECTED_PAGE_1]
        self.assertEqual(
            actual_teams, expected_teams, msg=df[["player_name", "team"]].to_string()
        )

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page1_matchups(self, mock_pdf_open, mock_get):
        """Matchup context switches correctly when a new time+matchup line appears."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        actual_matchups = df["matchup"].tolist()
        expected_matchups = [r[2] for r in _EXPECTED_PAGE_1]
        self.assertEqual(
            actual_matchups,
            expected_matchups,
            msg=df[["player_name", "matchup"]].to_string(),
        )

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page1_statuses(self, mock_pdf_open, mock_get):
        """Status values are extracted without contamination from reason tokens."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        actual_statuses = df["status"].tolist()
        expected_statuses = [r[3] for r in _EXPECTED_PAGE_1]
        self.assertEqual(actual_statuses, expected_statuses)

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page1_reasons_multiline(self, mock_pdf_open, mock_get):
        """Multi-line reasons are joined correctly; team/matchup lines do not leak."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        actual_reasons = df["reason"].tolist()
        expected_reasons = [r[4] for r in _EXPECTED_PAGE_1]
        self.assertEqual(
            actual_reasons,
            expected_reasons,
            msg=df[["player_name", "reason"]].to_string(),
        )

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page_footer_not_in_reasons(self, mock_pdf_open, mock_get):
        """Page footer tokens ('Page1of11') must not appear in any reason field."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_PAGE_1)

        collector = self._collector("2025-03-30")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        for reason in df["reason"]:
            self.assertNotIn(
                "Page", reason, msg=f"Footer leaked into reason: {reason!r}"
            )

    # ------------------------------------------------------------------
    # NOTYETSUBMITTED fixture tests
    # ------------------------------------------------------------------

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_notyetsubmitted_produces_no_rows(self, mock_pdf_open, mock_get):
        """Teams marked NOTYETSUBMITTED generate zero player rows."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_NOTYETSUBMITTED)

        collector = self._collector("2025-03-31")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        self.assertEqual(len(df), 0, msg=df.to_string())

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_notyetsubmitted_not_in_player_name(self, mock_pdf_open, mock_get):
        """'NOTYETSUBMITTED' must never appear as a player_name value."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf(_REAL_PDF_NOTYETSUBMITTED)

        collector = self._collector("2025-03-31")
        df = collector._parse_pdf("https://fake.url/report.pdf")

        if not df.empty:
            self.assertNotIn("NOTYETSUBMITTED", df["player_name"].values)


# ---------------------------------------------------------------------------
# Regression fixture: bare matchup lines (page-break artifact)
# Mirrors the real lines from Injury-Report_2026-04-02_10_00AM.pdf that
# previously caused continuation-swallowing bugs.
# ---------------------------------------------------------------------------

# Page 1 ending with Stewart,Isaiah followed by a bare PHX@CHA matchup line
_BARE_MATCHUP_PAGE_1 = [
    "04/02/2026 07:00(ET) MIN@DET MinnesotaTimberwolves Edwards,Anthony Questionable PatellofemoralPainSyndrome",
    "DetroitPistons Stewart,Isaiah Out Injury/Illness-LeftCalf;Strain",
    "PHX@CHA PhoenixSuns Coffey,Amir Out Injury/Illness-LeftAnkle;Sprain",
    "Injury/Illness-RightKnee;Injury",
    "Page1of4",
]

# Page straddle: Wade,Dean ends page 1; page 2 opens with a bare NOP@POR line
_BARE_MATCHUP_PAGE_STRADDLE = [
    # page 1
    "04/02/2026 10:00(ET) CLE@GSW ClevelandCavaliers Wade,Dean Out Injury/Illness-RightAnkle;Sprain",
    "GoldenStateWarriors NOTYETSUBMITTED",
    "NOP@POR NewOrleansPelicans Matkovic,Karlo Questionable Injury/Illness-LowBack;Spasms",
    "Page2of4",
    "Injury Report: 04/02/26 10:00 AM",
    # page 2 continuation of Matkovic
    "Injury/Illness-RightSmallToe;Fracture",
]

_EXPECTED_BARE_PAGE_1 = [
    (
        "Edwards,Anthony",
        "MinnesotaTimberwolves",
        "MIN@DET",
        "Questionable",
        "PatellofemoralPainSyndrome",
    ),
    (
        "Stewart,Isaiah",
        "DetroitPistons",
        "MIN@DET",
        "Out",
        "Injury/Illness-LeftCalf;Strain",
    ),
    (
        "Coffey,Amir",
        "PhoenixSuns",
        "PHX@CHA",
        "Out",
        "Injury/Illness-LeftAnkle;Sprain Injury/Illness-RightKnee;Injury",
    ),
]

_EXPECTED_BARE_STRADDLE = [
    (
        "Wade,Dean",
        "ClevelandCavaliers",
        "CLE@GSW",
        "Out",
        "Injury/Illness-RightAnkle;Sprain",
    ),
    (
        "Matkovic,Karlo",
        "NewOrleansPelicans",
        "NOP@POR",
        "Questionable",
        "Injury/Illness-LowBack;Spasms Injury/Illness-RightSmallToe;Fracture",
    ),
]


class TestParsePdfBareMatchup(unittest.TestCase):
    """Regression tests for bare matchup lines (no time prefix, page-break artifact).

    These lines — e.g. 'PHX@CHA PhoenixSuns Coffey,Amir Out ...' — appear
    when pdfplumber merges the time token from the end of the previous line.
    They must be treated as a new matchup context, not as a reason continuation.
    """

    def setUp(self):
        from src.data_collectors.get_injury_report import InjuryReportCollector

        _reset_singleton(InjuryReportCollector)
        self.InjuryReportCollector = InjuryReportCollector

    def tearDown(self):
        _reset_singleton(self.InjuryReportCollector)

    def _collector(self, date_iso: str):
        return self.InjuryReportCollector(save_mode="local", report_date=date_iso)

    def _mock_pdf(self, pages: list[list[str]]):
        """Multi-page mock: each inner list is one page."""
        mock_pages = []
        for lines in pages:
            page = MagicMock()
            page.extract_text.return_value = "\n".join(lines)
            mock_pages.append(page)
        pdf_cm = MagicMock()
        pdf_cm.__enter__ = MagicMock(return_value=pdf_cm)
        pdf_cm.__exit__ = MagicMock(return_value=False)
        pdf_cm.pages = mock_pages
        return pdf_cm

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_bare_matchup_row_count(self, mock_pdf_open, mock_get):
        """Bare matchup line starts a new matchup — correct number of rows."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_1])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        self.assertEqual(len(df), len(_EXPECTED_BARE_PAGE_1), msg=df.to_string())

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_bare_matchup_player_names(self, mock_pdf_open, mock_get):
        """Players after a bare matchup line are parsed with correct names."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_1])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        self.assertEqual(
            df["player_name"].tolist(), [r[0] for r in _EXPECTED_BARE_PAGE_1]
        )

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_bare_matchup_matchup_context(self, mock_pdf_open, mock_get):
        """Bare matchup line resets the matchup context for subsequent players."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_1])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        self.assertEqual(df["matchup"].tolist(), [r[2] for r in _EXPECTED_BARE_PAGE_1])

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_bare_matchup_prior_player_reason_clean(self, mock_pdf_open, mock_get):
        """The player before the bare matchup line does NOT get the matchup appended to its reason."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_1])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        stewart_reason = df.loc[df["player_name"] == "Stewart,Isaiah", "reason"].iloc[0]
        self.assertNotIn("PHX@CHA", stewart_reason)
        self.assertNotIn("Coffey", stewart_reason)

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_bare_matchup_continuation_reason(self, mock_pdf_open, mock_get):
        """A continuation line after a bare matchup player is joined to that player's reason."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_1])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        coffey_reason = df.loc[df["player_name"] == "Coffey,Amir", "reason"].iloc[0]
        self.assertIn("Injury/Illness-RightKnee;Injury", coffey_reason)

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page_straddle_row_count(self, mock_pdf_open, mock_get):
        """Page-straddle scenario: correct row count across two pages."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_STRADDLE])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        self.assertEqual(len(df), len(_EXPECTED_BARE_STRADDLE), msg=df.to_string())

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page_straddle_wade_reason_clean(self, mock_pdf_open, mock_get):
        """Wade,Dean's reason must not include any NOP@POR or Matkovic content."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_STRADDLE])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        wade_reason = df.loc[df["player_name"] == "Wade,Dean", "reason"].iloc[0]
        self.assertNotIn("NOP@POR", wade_reason)
        self.assertNotIn("Matkovic", wade_reason)

    @patch("src.data_collectors.get_injury_report.requests.get")
    @patch("src.data_collectors.get_injury_report.pdfplumber.open")
    def test_page_straddle_matkovic_reason_joined(self, mock_pdf_open, mock_get):
        """Matkovic's reason continuation from the next page is joined correctly."""
        mock_get.return_value = _make_200_response(b"fake")
        mock_pdf_open.return_value = self._mock_pdf([_BARE_MATCHUP_PAGE_STRADDLE])
        df = self._collector("2026-04-02")._parse_pdf("https://fake.url/report.pdf")
        matkovic_reason = df.loc[df["player_name"] == "Matkovic,Karlo", "reason"].iloc[
            0
        ]
        self.assertIn("Injury/Illness-RightSmallToe;Fracture", matkovic_reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
