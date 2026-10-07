import os
import tempfile
import unittest

from app import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.client = create_app(self.path).test_client()
        self.client.post("/api/setup", json={"sample": True})
        members = {m["name"]: m["id"] for m in self.client.get("/api/members").get_json()}
        self.admin, self.asha, self.karthik = (members["Admin Librarian"], members["Asha"],
                                               members["Karthik"])

    def tearDown(self):
        os.remove(self.path)

    def as_(self, member_id):
        return {"X-Member-Id": str(member_id)}

    def test_setup_only_runs_once(self):
        self.assertEqual(self.client.post("/api/setup", json={"sample": True}).status_code, 400)

    def test_book_list_never_contains_ebook_text(self):
        for book in self.client.get("/api/books").get_json():
            self.assertNotIn("content", book)

    def test_pending_book_is_hidden_until_approved(self):
        titles = [b["title"] for b in self.client.get("/api/books").get_json()]
        self.assertNotIn("My Campus Diary", titles)
        pending = self.client.get("/api/pending", headers=self.as_(self.admin)).get_json()
        book_id = pending[0]["id"]
        self.assertEqual(self.client.post(f"/api/pending/{book_id}/approve",
                                          headers=self.as_(self.karthik)).status_code, 403)
        self.assertEqual(self.client.post(f"/api/pending/{book_id}/approve",
                                          headers=self.as_(self.admin)).status_code, 200)
        titles = [b["title"] for b in self.client.get("/api/books").get_json()]
        self.assertIn("My Campus Diary", titles)

    def test_borrow_and_return_flow(self):
        book = next(b for b in self.client.get("/api/books?q=Pragmatic").get_json())
        self.assertEqual(self.client.post(f"/api/books/{book['id']}/borrow").status_code, 401)
        res = self.client.post(f"/api/books/{book['id']}/borrow", headers=self.as_(self.karthik))
        self.assertEqual(res.status_code, 201)
        loan_id = res.get_json()["loan_id"]
        again = self.client.post(f"/api/books/{book['id']}/borrow", headers=self.as_(self.asha))
        self.assertEqual(again.status_code, 400)  # only one copy
        stranger = self.client.post(f"/api/loans/{loan_id}/return", headers=self.as_(self.asha))
        self.assertEqual(stranger.status_code, 403)
        done = self.client.post(f"/api/loans/{loan_id}/return", headers=self.as_(self.karthik))
        self.assertEqual(done.get_json()["fine"], 0)

    def test_reading_and_recommendations(self):
        recs = self.client.get("/api/recommendations", headers=self.as_(self.asha)).get_json()
        self.assertEqual(recs[0]["title"], "Introduction to Algorithms")
        ebook = next(b for b in self.client.get("/api/books?format=ebook").get_json())
        res = self.client.get(f"/api/ebooks/{ebook['id']}/read", headers=self.as_(self.asha))
        self.assertIn("content", res.get_json())

    def test_member_submission_flow(self):
        res = self.client.post("/api/my/books", headers=self.as_(self.asha),
                               json={"title": "Notes", "content": "hello", "genre": "Technology"})
        self.assertEqual(res.get_json()["status"], "pending")


if __name__ == "__main__":
    unittest.main()
