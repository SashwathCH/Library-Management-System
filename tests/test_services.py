import unittest
from datetime import date, timedelta

from library.seed import load_sample_data
from library.services import LibraryError, LibraryService


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.svc = LibraryService(":memory:")
        self.book = self.svc.add_book("Clean Code", "Robert Martin", "111", 1, "Technology")
        self.member = self.svc.add_member("Asha", "asha@example.com")

    def test_issue_reduces_availability(self):
        self.svc.issue_book(self.book, self.member)
        self.assertEqual(self.svc.list_books()[0]["available"], 0)

    def test_cannot_issue_without_copies(self):
        self.svc.issue_book(self.book, self.member)
        with self.assertRaises(LibraryError):
            self.svc.issue_book(self.book, self.member)

    def test_late_return_fine(self):
        start = date(2026, 1, 1)
        _, loan = self.svc.issue_book(self.book, self.member, today=start)
        self.assertEqual(self.svc.return_book(loan, today=start + timedelta(days=19)), 10.0)

    def test_duplicate_isbn_rejected(self):
        with self.assertRaises(LibraryError):
            self.svc.add_book("Other", "Someone", "111")

    def test_book_with_history_cannot_be_removed(self):
        _, loan = self.svc.issue_book(self.book, self.member)
        self.svc.return_book(loan)
        with self.assertRaises(LibraryError):
            self.svc.remove_book(self.book)


class EbookAndCreationTests(unittest.TestCase):
    def setUp(self):
        self.svc = LibraryService(":memory:")
        self.member = self.svc.add_member("Karthik", "k@example.com")
        self.author = self.svc.add_member("Meena", "m@example.com", "author")

    def test_ebook_cannot_be_issued(self):
        eb = self.svc.add_ebook("Logic", "S. Kumar", "AND OR NOT", "Technology")
        with self.assertRaises(LibraryError):
            self.svc.issue_book(eb, self.member)

    def test_reading_logs_history(self):
        eb = self.svc.add_ebook("Logic", "S. Kumar", "AND OR NOT", "Technology")
        self.assertEqual(self.svc.read_ebook(self.member, eb)["title"], "Logic")
        self.svc.rate_book(self.member, eb, 5)
        self.assertEqual(self.svc.average_rating(eb), 5.0)

    def test_member_submission_needs_approval(self):
        book_id, status = self.svc.create_book(self.member, "My Diary", "Day one...", "Fiction")
        self.assertEqual(status, "pending")
        self.assertEqual(self.svc.list_books(), [])          # hidden from catalogue
        self.svc.approve_book(book_id)
        self.assertEqual(len(self.svc.list_books()), 1)

    def test_author_publishes_immediately(self):
        _, status = self.svc.create_book(self.author, "Python 101", "print('hi')", "Technology")
        self.assertEqual(status, "published")

    def test_cannot_rate_unread_book(self):
        eb = self.svc.add_ebook("Logic", "S. Kumar", "text", "Technology")
        with self.assertRaises(LibraryError):
            self.svc.rate_book(self.member, eb, 5)

    def test_reject_removes_submission(self):
        book_id, _ = self.svc.create_book(self.member, "Draft", "text", "Fiction")
        self.svc.reject_book(book_id)
        self.assertEqual(self.svc.pending_books(), [])


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.svc = LibraryService(":memory:")
        load_sample_data(self.svc)

    def test_recommendations_exclude_history_and_pending(self):
        recs = self.svc.recommend(2)  # Asha
        titles = [r["title"] for r in recs]
        self.assertNotIn("Clean Code", titles)
        self.assertNotIn("My Campus Diary", titles)  # still pending

    def test_similar_reader_pushes_algorithms_to_top(self):
        recs = self.svc.recommend(2)
        self.assertEqual(recs[0]["title"], "Introduction to Algorithms")
        self.assertIn("similar taste", recs[0]["reason"])

    def test_new_member_gets_popular_books(self):
        newbie = self.svc.add_member("Newbie", "n@example.com")
        recs = self.svc.recommend(newbie)
        self.assertTrue(recs)
        self.assertEqual(recs[0]["title"], "Clean Code")


if __name__ == "__main__":
    unittest.main()
