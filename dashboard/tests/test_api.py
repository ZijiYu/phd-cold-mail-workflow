"""Dashboard API tests. Run from the repo root:

    pip install -r dashboard/requirements.txt
    python -m unittest discover dashboard/tests
"""

import json
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

try:
    from fastapi.testclient import TestClient
    from dashboard.app.api import create_app
    from fake_google import ME, FakeGoogle
except ImportError as e:  # pragma: no cover
    raise unittest.SkipTest(f"dashboard dependencies not installed: {e}")

SAMPLE = ROOT / "dashboard" / "tests" / "fixtures" / "outreach"
TODAY = date(2026, 10, 28)
C = "/api/campaigns/fall-2027"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(SAMPLE, self.tmp / "data")
        self.google = FakeGoogle()
        self.app = create_app(self.tmp / "data", self.tmp / "state", gmail_transport=self.google, today=TODAY)
        self.c = TestClient(self.app, base_url="http://127.0.0.1:8765")
        self.c.headers["Authorization"] = f"Bearer {self.app.state.token}"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    CLIENT = {"installed": {"client_id": "123456789-abcdef.apps.googleusercontent.com", "client_secret": "secret",
                            "redirect_uris": ["http://localhost"]}}

    def connect_gmail(self):
        (self.tmp / "state" / "google_client.json").write_text(json.dumps(self.CLIENT))
        r = self.c.post("/api/gmail/connect").json()
        state = urllib.parse.parse_qs(urllib.parse.urlparse(r["auth_url"]).query)["state"][0]
        resp = self.c.get(f"/auth/google/callback?code=good-code&state={state}", follow_redirects=False)
        self.assertIn("gmail=connected", resp.headers["location"])


class SecurityTests(Base):
    def test_token_required(self):
        anon = TestClient(self.app, base_url="http://127.0.0.1:8765")
        self.assertEqual(anon.get("/api/campaigns").status_code, 401)
        self.assertEqual(anon.get("/api/campaigns", headers={"X-API-Token": "wrong"}).status_code, 401)
        self.assertEqual(anon.get("/api/campaigns", headers={"X-API-Token": self.app.state.token}).status_code, 200)

    def test_foreign_host_rejected(self):
        evil = TestClient(self.app, base_url="http://attacker.example")
        self.assertEqual(evil.get("/").status_code, 403)
        self.assertEqual(evil.get("/api/campaigns", headers={"Authorization": f"Bearer {self.app.state.token}"}).status_code, 403)

    def test_index_embeds_token_and_token_file_is_private(self):
        self.assertIn(self.app.state.token, self.c.get("/").text)
        self.assertEqual((self.tmp / "state" / "api_token").stat().st_mode & 0o777, 0o600)

    def test_path_traversal(self):
        self.assertIn(self.c.get("/api/campaigns/..%2F..%2Fetc/targets").status_code, (400, 404))
        r = self.c.patch(f"{C}/targets/harbor--tom-lindqvist", json={"draft_path": "../../../etc/passwd"})
        self.assertEqual(r.status_code, 200)  # stored as data...
        self.assertEqual(self.c.get(f"{C}/targets/harbor--tom-lindqvist/drafts").status_code, 400)  # ...but never read


class TrackerTests(Base):
    def test_summary(self):
        s = self.c.get(f"{C}/summary").json()
        self.assertEqual(s["total"], 11)
        self.assertEqual(s["counts"]["sent"], 3)
        self.assertEqual([d["target_id"] for d in s["due"]], ["lakeview--marcus-hale", "pinecrest--omar-said"])
        self.assertEqual(s["schools"][0]["institution"], "Northfield Institute of Technology")  # earliest deadline

    def test_filters(self):
        self.assertEqual(len(self.c.get(f"{C}/targets?status=sent").json()), 3)
        self.assertEqual(len(self.c.get(f"{C}/targets?q=harbor").json()), 2)

    def test_status_rules(self):
        t = f"{C}/targets/harbor--priya-raman"
        self.assertEqual(self.c.patch(t, json={"status": "closed"}).status_code, 400)
        self.assertEqual(self.c.patch(t, json={"status": "nope"}).status_code, 400)
        row = self.c.patch(t, json={"status": "sent"}).json()
        self.assertEqual((row["sent_at"], row["follow_up_due"], row["follow_up_count"]), ("2026-10-28", "2026-11-07", "0"))
        # the CSV is still valid for the skill's checker
        from dashboard.app.checks import check_tracker
        cols, rows = check_tracker.load_csv(self.tmp / "data" / "fall-2027" / "targets.csv")
        self.assertIn("fit_components", cols)
        self.assertEqual(next(r for r in rows if r["target_id"] == "harbor--priya-raman")["status"], "sent")

    def test_approval_blocked_by_draft_errors(self):
        t = f"{C}/targets/harbor--tom-lindqvist"
        r = self.c.patch(t, json={"status": "approved"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("[Topic]", r.json()["detail"])
        body = (SAMPLE / "fall-2027" / "drafts" / "harbor--priya-raman.md").read_text().split("\n", 2)[2].split("\n---")[0]
        self.c.put(f"{t}/drafts/harbor--tom-lindqvist.md", json={"subject": "Fall 2027 PhD inquiry: replay-free online adaptation", "body": body})
        self.assertEqual(self.c.patch(t, json={"status": "approved"}).status_code, 200)

    def test_create_campaign(self):
        r = self.c.post("/api/campaigns", json={"id": "spring-2028"})
        self.assertEqual(r.status_code, 201)
        ids = [c["id"] for c in self.c.get("/api/campaigns").json()]
        self.assertIn("spring-2028", ids)
        self.assertEqual(self.c.get("/api/campaigns/spring-2028/summary").json()["total"], 0)
        added = self.c.post("/api/campaigns/spring-2028/targets",
                            json={"target_id": "x--prof", "professor": "Prof", "institution": "X"})
        self.assertEqual(added.status_code, 201)
        self.assertEqual(self.c.post("/api/campaigns", json={"id": "spring-2028"}).status_code, 409)
        self.assertEqual(self.c.post("/api/campaigns", json={"id": "../evil"}).status_code, 400)

    def test_create_target(self):
        r = self.c.post(f"{C}/targets", json={"target_id": "summit--new-prof", "professor": "New Prof", "institution": "Summit University"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["status"], "researching")
        self.assertEqual(self.c.post(f"{C}/targets", json={"target_id": "summit--new-prof", "professor": "x", "institution": "y"}).status_code, 409)
        self.assertEqual(self.c.post(f"{C}/targets", json={"target_id": "../bad", "professor": "x", "institution": "y"}).status_code, 400)


class DraftTests(Base):
    def test_roundtrip_preserves_notes(self):
        p = f"{C}/targets/harbor--priya-raman/drafts/harbor--priya-raman.md"
        d = self.c.get(p).json()
        self.c.put(p, json={"subject": d["subject"] + " (v2)", "body": d["body"] + "\nP.S. Thanks."})
        text = (self.tmp / "data" / "fall-2027" / "drafts" / "harbor--priya-raman.md").read_text()
        self.assertIn("(v2)", text)
        self.assertIn("## Evidence bridge", text)
        self.assertNotIn("Evidence bridge", self.c.get(p).json()["body"])

    def test_followup_naming_and_subject(self):
        r = self.c.post(f"{C}/targets/lakeview--marcus-hale/drafts", json={"kind": "followup"}).json()
        self.assertEqual(r["name"], "lakeview--marcus-hale--followup-1.md")
        self.assertTrue(r["subject"].startswith("Re: "))
        kinds = [d["kind"] for d in self.c.get(f"{C}/targets/lakeview--marcus-hale/drafts").json()]
        self.assertEqual(kinds, ["first", "followup"])

    def test_first_draft_sets_draft_path_and_status(self):
        t = f"{C}/targets/pinecrest--yuki-tanaka"
        d = self.c.post(f"{t}/drafts", json={"kind": "first"}).json()
        self.assertEqual(self.c.get(t).json()["target"]["draft_path"], f"drafts/{d['name']}")
        self.c.put(f"{t}/drafts/{d['name']}", json={"subject": "s", "body": "Dear Professor Tanaka,"})
        self.assertEqual(self.c.get(t).json()["target"]["status"], "drafted")

    def test_check_endpoint(self):
        r = self.c.post(f"{C}/targets/harbor--tom-lindqvist/drafts/harbor--tom-lindqvist.md/check").json()
        self.assertTrue(any("TODO" in e for e in r["errors"]))
        r = self.c.post(f"{C}/targets/northfield--ines-moreau/drafts/northfield--ines-moreau--followup-1.md/check").json()
        self.assertEqual(r["kind"], "followup")
        self.assertEqual(r["errors"], [])


class GmailTests(Base):
    def test_unconfigured(self):
        s = self.c.get("/api/gmail/status").json()
        self.assertFalse(s["configured"])
        self.assertEqual(self.c.post("/api/gmail/connect").status_code, 400)

    def test_oauth_flow_uses_pkce_and_state(self):
        (self.tmp / "state" / "google_client.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "s"}}))
        url = self.c.post("/api/gmail/connect").json()["auth_url"]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(q["redirect_uri"], ["http://127.0.0.1:8765/auth/google/callback"])
        self.assertIn("gmail.compose", q["scope"][0])
        self.assertNotIn("gmail.send", q["scope"][0])
        bad = self.c.get("/auth/google/callback?code=good-code&state=forged", follow_redirects=False)
        self.assertIn("gmail-error", bad.headers["location"])
        self.c.get(f"/auth/google/callback?code=good-code&state={q['state'][0]}", follow_redirects=False)
        self.assertEqual(self.google.token_requests[0]["code_verifier"] is not None, True)
        s = self.c.get("/api/gmail/status").json()
        self.assertTrue(s["connected"])
        self.assertEqual(s["email"], ME)
        self.assertEqual((self.tmp / "state" / "google_token.json").stat().st_mode & 0o777, 0o600)

    def test_sync_suggestions(self):
        self.connect_gmail()
        r = self.c.post(f"{C}/gmail/sync", json={}).json()
        sug = {s["target_id"]: s["suggestion"] for s in r["suggestions"]}
        self.assertEqual(sug["harbor--priya-raman"]["kind"], "sent")
        self.assertEqual(sug["harbor--priya-raman"]["fields"]["sent_at"], "2026-10-26")
        self.assertEqual(sug["lakeview--marcus-hale"]["kind"], "replied")
        self.assertEqual(sug["pinecrest--omar-said"]["kind"], "auto_reply")
        self.assertNotIn("northfield--ines-moreau", sug)  # follow-up count already recorded
        # nothing is applied automatically
        self.assertEqual(self.c.get(f"{C}/targets/lakeview--marcus-hale").json()["target"]["status"], "sent")
        # applying clears the suggestion
        self.c.patch(f"{C}/targets/lakeview--marcus-hale", json=sug["lakeview--marcus-hale"]["fields"])
        d = self.c.get(f"{C}/targets/lakeview--marcus-hale").json()
        self.assertEqual(d["target"]["status"], "replied")
        self.assertIsNone(d["gmail"]["suggestion"])
        # dismissing works too
        self.assertEqual(self.c.delete(f"{C}/targets/pinecrest--omar-said/suggestion").status_code, 204)
        self.assertIsNone(self.c.get(f"{C}/targets/pinecrest--omar-said").json()["gmail"]["suggestion"])

    def test_thread(self):
        self.connect_gmail()
        self.c.post(f"{C}/gmail/sync", json={"target_ids": ["lakeview--marcus-hale"]})
        msgs = self.c.get(f"{C}/targets/lakeview--marcus-hale/thread").json()["messages"]
        self.assertEqual(len(msgs), 2)
        self.assertIn("one student this cycle", msgs[-1]["body"])

    def test_push_draft_rules_and_update(self):
        self.connect_gmail()
        # first-contact draft needs approved status
        self.assertEqual(self.c.post(f"{C}/targets/harbor--tom-lindqvist/drafts/harbor--tom-lindqvist.md/gmail").status_code, 409)
        p = f"{C}/targets/harbor--priya-raman/drafts/harbor--priya-raman.md/gmail"
        r1 = self.c.post(p).json()
        r2 = self.c.post(p).json()
        self.assertEqual((r1["draft_id"], r1["updated"]), ("d1", False))
        self.assertEqual((r2["draft_id"], r2["updated"]), ("d1", True))
        self.assertEqual(len(self.google.drafts), 1)
        self.assertFalse(any("send" in url for _, url in self.google.calls))

    def test_followup_draft_is_threaded(self):
        self.connect_gmail()
        self.c.post(f"{C}/gmail/sync", json={"target_ids": ["northfield--ines-moreau"]})
        r = self.c.post(f"{C}/targets/northfield--ines-moreau/drafts/northfield--ines-moreau--followup-1.md/gmail").json()
        self.assertTrue(r["threaded"])
        sent = self.google.drafts[r["draft_id"]]["message"]
        self.assertEqual(sent["threadId"], "t4")
        import base64
        raw = base64.urlsafe_b64decode(sent["raw"] + "==").decode()
        self.assertIn("In-Reply-To: <m7@mail.example.com>", raw)
        self.assertIn("To: imoreau@example.edu", raw)

    def test_save_client_returns_auth_url(self):
        r = self.c.put("/api/gmail/client", json={"json": self.CLIENT})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body["status"]["configured"])
        q = urllib.parse.parse_qs(urllib.parse.urlparse(body["auth_url"]).query)
        self.assertEqual(q["client_id"], ["123456789-abcdef.apps.googleusercontent.com"])
        self.assertEqual((self.tmp / "state" / "google_client.json").stat().st_mode & 0o777, 0o600)
        # pasted values work too
        r = self.c.put("/api/gmail/client", json={"client_id": "987654321-zzz.apps.googleusercontent.com", "client_secret": "s2"})
        self.assertEqual(r.status_code, 200)

    def test_save_client_rejects_bad_input(self):
        web = {"web": {"client_id": "123456789-abc.apps.googleusercontent.com", "client_secret": "s"}}
        r = self.c.put("/api/gmail/client", json={"json": web})
        self.assertEqual((r.status_code, r.json()["code"]), (400, "client_type"))
        r = self.c.put("/api/gmail/client", json={"client_id": "not-an-id", "client_secret": "s"})
        self.assertEqual(r.json()["code"], "client_id")
        r = self.c.put("/api/gmail/client", json={"client_id": "123456789-abc.apps.googleusercontent.com"})
        self.assertEqual(r.json()["code"], "client_secret")
        self.assertFalse(self.c.get("/api/gmail/status").json()["configured"])

    def test_expired_token_asks_for_reauth_with_login_hint(self):
        self.connect_gmail()
        tok = json.loads((self.tmp / "state" / "google_token.json").read_text())
        tok["expires_at"] = 0  # force a refresh
        (self.tmp / "state" / "google_token.json").write_text(json.dumps(tok))
        self.google.refresh_error = "invalid_grant"
        r = self.c.post(f"{C}/gmail/sync", json={})
        self.assertEqual((r.status_code, r.json()["code"]), (401, "gmail_reauth"))
        s = self.c.get("/api/gmail/status").json()
        self.assertEqual((s["connected"], s["reauth"], s["reauth_email"]), (False, True, ME))
        url = self.c.post("/api/gmail/connect").json()["auth_url"]
        self.assertIn("login_hint=" + urllib.parse.quote(ME), url)
        self.google.refresh_error = ""
        self.connect_gmail()
        self.assertFalse(self.c.get("/api/gmail/status").json()["reauth"])

    def test_missing_scopes(self):
        self.google.granted_scopes = "https://www.googleapis.com/auth/gmail.compose"
        (self.tmp / "state" / "google_client.json").write_text(json.dumps(self.CLIENT))
        url = self.c.post("/api/gmail/connect").json()["auth_url"]
        state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
        loc = self.c.get(f"/auth/google/callback?code=good-code&state={state}", follow_redirects=False).headers["location"]
        self.assertIn("gmail-error=", loc)
        self.assertFalse(self.c.get("/api/gmail/status").json()["connected"])
        # read-only grant connects but cannot push drafts
        self.google.granted_scopes = "https://www.googleapis.com/auth/gmail.readonly"
        self.connect_gmail()
        s = self.c.get("/api/gmail/status").json()
        self.assertEqual((s["can_read"], s["can_draft"]), (True, False))
        r = self.c.post(f"{C}/targets/harbor--priya-raman/drafts/harbor--priya-raman.md/gmail")
        self.assertEqual(r.json()["code"], "missing_scope")

    def test_access_denied_is_friendly(self):
        loc = self.c.get("/auth/google/callback?error=access_denied", follow_redirects=False).headers["location"]
        self.assertIn(urllib.parse.quote("测试用户"), loc)

    def test_remove_client(self):
        self.connect_gmail()
        s = self.c.delete("/api/gmail/client").json()
        self.assertEqual((s["configured"], s["connected"]), (False, False))
        self.assertTrue(self.google.revoked)

    def test_disconnect(self):
        self.connect_gmail()
        self.assertFalse(self.c.post("/api/gmail/disconnect").json()["connected"])
        self.assertTrue(self.google.revoked)
        self.assertFalse((self.tmp / "state" / "google_token.json").exists())


if __name__ == "__main__":
    unittest.main()
