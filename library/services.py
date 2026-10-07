import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from .database import get_connection

LOAN_DAYS = 14
FINE_PER_DAY = 2.0  # rupees
ROLES = ("member", "author", "librarian")
PUBLISH_DIRECTLY = ("author", "librarian")


class LibraryError(Exception):
    """Raised for any business-rule violation."""


class LibraryService:
    def __init__(self, db_path=None, init=True):
        self.conn = get_connection(db_path, init) if db_path else get_connection(init=init)

    # ---------- helpers ----------
    def _member(self, member_id):
        row = self.conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
        if not row:
            raise LibraryError("Member not found.")
        return row

    def _book(self, book_id, published_only=True):
        row = self.conn.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not row or (published_only and row["status"] != "published"):
            raise LibraryError("Book not found.")
        return row

    # ---------- Books (physical) ----------
    def add_book(self, title, author, isbn=None, copies=1, genre="General", description=""):
        if not title.strip() or not author.strip():
            raise LibraryError("Title and author are required.")
        if copies < 1:
            raise LibraryError("Copies must be at least 1.")
        return self._insert(title, author, isbn, copies, genre, description, "physical", None,
                            "published", None)

    def _insert(self, title, author, isbn, copies, genre, description, fmt, content, status,
                created_by):
        try:
            cur = self.conn.execute(
                """INSERT INTO books (title, author, isbn, copies, available, genre, description,
                                      format, content, status, created_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (title.strip(), author.strip(), isbn or None, copies, copies,
                 genre.strip() or "General", description.strip(), fmt, content, status,
                 created_by),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise LibraryError("A book with this ISBN already exists.")
        return cur.lastrowid

    def list_books(self, fmt=None):
        sql = "SELECT * FROM books WHERE status='published'"
        args = ()
        if fmt:
            sql += " AND format=?"
            args = (fmt,)
        return self.conn.execute(sql + " ORDER BY title", args).fetchall()

    def search_books(self, term):
        like = f"%{term}%"
        return self.conn.execute(
            """SELECT * FROM books WHERE status='published'
               AND (title LIKE ? OR author LIKE ? OR isbn LIKE ? OR genre LIKE ?)
               ORDER BY title""",
            (like, like, like, like),
        ).fetchall()

    def remove_book(self, book_id):
        self._book(book_id, published_only=False)
        if self.conn.execute("SELECT 1 FROM loans WHERE book_id=?", (book_id,)).fetchone():
            raise LibraryError("This book has loan history and cannot be removed.")
        self.conn.execute("DELETE FROM ratings WHERE book_id=?", (book_id,))
        self.conn.execute("DELETE FROM ebook_reads WHERE book_id=?", (book_id,))
        self.conn.execute("DELETE FROM books WHERE id=?", (book_id,))
        self.conn.commit()

    # ---------- Members ----------
    def add_member(self, name, email=None, role="member"):
        if not name.strip():
            raise LibraryError("Member name is required.")
        if role not in ROLES:
            raise LibraryError(f"Role must be one of: {', '.join(ROLES)}.")
        try:
            cur = self.conn.execute(
                "INSERT INTO members (name, email, role) VALUES (?,?,?)",
                (name.strip(), email or None, role),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise LibraryError("A member with this email already exists.")
        return cur.lastrowid

    def list_members(self):
        return self.conn.execute("SELECT * FROM members ORDER BY name").fetchall()

    def set_role(self, member_id, role):
        self._member(member_id)
        if role not in ROLES:
            raise LibraryError(f"Role must be one of: {', '.join(ROLES)}.")
        self.conn.execute("UPDATE members SET role=? WHERE id=?", (role, member_id))
        self.conn.commit()

    # ---------- Loans (physical books) ----------
    def issue_book(self, book_id, member_id, today=None):
        today = today or date.today()
        book = self._book(book_id)
        self._member(member_id)
        if book["format"] == "ebook":
            raise LibraryError("E-books are read online, not issued. Use 'Read e-book'.")
        if book["available"] < 1:
            raise LibraryError("No copies available.")
        due = today + timedelta(days=LOAN_DAYS)
        cur = self.conn.execute(
            "INSERT INTO loans (book_id, member_id, issue_date, due_date) VALUES (?,?,?,?)",
            (book_id, member_id, today.isoformat(), due.isoformat()),
        )
        self.conn.execute("UPDATE books SET available = available - 1 WHERE id=?", (book_id,))
        self.conn.commit()
        return due, cur.lastrowid

    def return_book(self, loan_id, today=None):
        today = today or date.today()
        loan = self.conn.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
        if not loan:
            raise LibraryError("Loan not found.")
        if loan["return_date"]:
            raise LibraryError("This book was already returned.")
        overdue_days = max(0, (today - date.fromisoformat(loan["due_date"])).days)
        fine = overdue_days * FINE_PER_DAY
        self.conn.execute(
            "UPDATE loans SET return_date=?, fine=? WHERE id=?", (today.isoformat(), fine, loan_id)
        )
        self.conn.execute("UPDATE books SET available = available + 1 WHERE id=?", (loan["book_id"],))
        self.conn.commit()
        return fine

    def active_loans(self):
        return self.conn.execute(
            """SELECT l.id, b.title, m.name AS member, l.issue_date, l.due_date
               FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id
               WHERE l.return_date IS NULL ORDER BY l.due_date"""
        ).fetchall()

    def overdue_loans(self, today=None):
        today = (today or date.today()).isoformat()
        return self.conn.execute(
            """SELECT l.id, b.title, m.name AS member, l.due_date
               FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id
               WHERE l.return_date IS NULL AND l.due_date < ? ORDER BY l.due_date""",
            (today,),
        ).fetchall()

    # ---------- E-books ----------
    def add_ebook(self, title, author, content, genre="General", description="", isbn=None):
        """Librarian import: any author name, published immediately."""
        if not title.strip() or not author.strip():
            raise LibraryError("Title and author are required.")
        if not content.strip():
            raise LibraryError("E-book content cannot be empty.")
        return self._insert(title, author, isbn, 0, genre, description, "ebook", content,
                            "published", None)

    def read_ebook(self, member_id, book_id, now=None):
        self._member(member_id)
        book = self._book(book_id)
        if book["format"] != "ebook":
            raise LibraryError("That is a physical book. Ask the librarian to issue it.")
        stamp = (now or datetime.now()).isoformat(timespec="seconds")
        self.conn.execute(
            "INSERT INTO ebook_reads (member_id, book_id, read_at) VALUES (?,?,?)",
            (member_id, book_id, stamp),
        )
        self.conn.commit()
        return book

    # ---------- Book creation by members / authors ----------
    def create_book(self, member_id, title, content, genre="General", description=""):
        """A member or author writes an e-book. Authors/librarians publish at once;
        regular members' work waits for librarian approval. Returns (book_id, status)."""
        member = self._member(member_id)
        if not title.strip():
            raise LibraryError("Title is required.")
        if not content.strip():
            raise LibraryError("Your book needs some content.")
        status = "published" if member["role"] in PUBLISH_DIRECTLY else "pending"
        book_id = self._insert(title, member["name"], None, 0, genre, description, "ebook",
                               content, status, member_id)
        return book_id, status

    def my_creations(self, member_id):
        self._member(member_id)
        return self.conn.execute(
            "SELECT id, title, genre, status FROM books WHERE created_by=? ORDER BY id",
            (member_id,),
        ).fetchall()

    def pending_books(self):
        return self.conn.execute(
            "SELECT id, title, author, genre FROM books WHERE status='pending' ORDER BY id"
        ).fetchall()

    def approve_book(self, book_id):
        book = self._book(book_id, published_only=False)
        if book["status"] != "pending":
            raise LibraryError("That book is not waiting for approval.")
        self.conn.execute("UPDATE books SET status='published' WHERE id=?", (book_id,))
        self.conn.commit()

    def reject_book(self, book_id):
        book = self._book(book_id, published_only=False)
        if book["status"] != "pending":
            raise LibraryError("That book is not waiting for approval.")
        self.remove_book(book_id)

    # ---------- Ratings ----------
    def rate_book(self, member_id, book_id, rating):
        self._member(member_id)
        self._book(book_id)
        if not 1 <= rating <= 5:
            raise LibraryError("Rating must be between 1 and 5.")
        if book_id not in self._history(member_id):
            raise LibraryError("You can only rate books you have borrowed or read.")
        self.conn.execute(
            """INSERT INTO ratings (member_id, book_id, rating) VALUES (?,?,?)
               ON CONFLICT(member_id, book_id) DO UPDATE SET rating=excluded.rating""",
            (member_id, book_id, rating),
        )
        self.conn.commit()

    def average_rating(self, book_id):
        row = self.conn.execute(
            "SELECT AVG(rating) FROM ratings WHERE book_id=?", (book_id,)
        ).fetchone()
        return round(row[0], 1) if row[0] is not None else None

    # ---------- Recommendations ----------
    def _pairs(self):
        return self.conn.execute(
            "SELECT member_id, book_id FROM loans UNION SELECT member_id, book_id FROM ebook_reads"
        ).fetchall()

    def _history(self, member_id):
        return {b for m, b in self._pairs() if m == member_id}

    def recommend(self, member_id, limit=5):
        """Hybrid recommender: genre/author match + readers with similar taste
        + average rating + popularity. Returns a list of dicts with a 'reason'."""
        self._member(member_id)
        pairs = self._pairs()
        mine = {b for m, b in pairs if m == member_id}
        books = {b["id"]: b for b in self.list_books()}

        # What the member likes (ratings of 1-2 don't count as interest)
        disliked = {r[0] for r in self.conn.execute(
            "SELECT book_id FROM ratings WHERE member_id=? AND rating<=2", (member_id,))}
        genre_w, author_w = Counter(), Counter()
        for b in mine - disliked:
            if b in books:
                genre_w[books[b]["genre"]] += 1
                author_w[books[b]["author"]] += 1

        # Collaborative signal: books borrowed/read by members who share books with me
        others = defaultdict(set)
        for m, b in pairs:
            if m != member_id:
                others[m].add(b)
        co = Counter()
        for read in others.values():
            overlap = len(mine & read)
            if overlap:
                for b in read - mine:
                    co[b] += overlap

        popularity = Counter(b for _, b in pairs)
        ratings = {r[0]: r[1] for r in self.conn.execute(
            "SELECT book_id, AVG(rating) FROM ratings GROUP BY book_id")}
        max_genre = max(genre_w.values(), default=1)
        max_co = max(co.values(), default=1)
        max_pop = max(popularity.values(), default=1)

        results = []
        for book_id, book in books.items():
            if book_id in mine:
                continue
            score, reasons = 0.0, []
            if genre_w[book["genre"]]:
                score += 3 * genre_w[book["genre"]] / max_genre
                reasons.append(f"you enjoy {book['genre']}")
            if author_w[book["author"]]:
                score += 2
                reasons.append(f"more by {book['author']}")
            if co[book_id]:
                score += 3 * co[book_id] / max_co
                reasons.append("readers with similar taste liked it")
            if book_id in ratings:
                score += 2 * ratings[book_id] / 5
                if ratings[book_id] >= 4:
                    reasons.append(f"rated {ratings[book_id]:.1f}/5")
            if popularity[book_id]:
                score += popularity[book_id] / max_pop
                if not reasons:
                    reasons.append("popular in the library")
            if score > 0:
                results.append({
                    "id": book_id, "title": book["title"], "author": book["author"],
                    "genre": book["genre"], "format": book["format"],
                    "score": round(score, 2), "reason": (lambda t: t[0].upper() + t[1:])("; ".join(reasons)),
                })
        results.sort(key=lambda r: (-r["score"], r["title"]))
        return results[:limit]

    # ---------- Read helpers used by the web API ----------
    def get_member(self, member_id):
        return self._member(member_id)

    def get_book(self, book_id, published_only=True):
        return self._book(book_id, published_only)

    def get_loan(self, loan_id):
        row = self.conn.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
        if not row:
            raise LibraryError("Loan not found.")
        return row

    def rating_map(self):
        return {r[0]: {"avg": round(r[1], 1), "count": r[2]} for r in self.conn.execute(
            "SELECT book_id, AVG(rating), COUNT(*) FROM ratings GROUP BY book_id")}

    def my_rating(self, member_id, book_id):
        row = self.conn.execute(
            "SELECT rating FROM ratings WHERE member_id=? AND book_id=?", (member_id, book_id)
        ).fetchone()
        return row[0] if row else None

    def can_rate(self, member_id, book_id):
        return book_id in self._history(member_id)

    def active_loan_for(self, member_id, book_id):
        return self.conn.execute(
            "SELECT id, due_date FROM loans WHERE member_id=? AND book_id=? AND return_date IS NULL",
            (member_id, book_id),
        ).fetchone()

    def member_loans(self, member_id):
        return self.conn.execute(
            """SELECT l.id, l.book_id, b.title, b.author, l.issue_date, l.due_date,
                      l.return_date, l.fine
               FROM loans l JOIN books b ON b.id=l.book_id
               WHERE l.member_id=?
               ORDER BY l.return_date IS NOT NULL, l.due_date DESC""",
            (member_id,),
        ).fetchall()

    def member_reads(self, member_id):
        return self.conn.execute(
            """SELECT r.book_id, b.title, b.author, MAX(r.read_at) AS last_read, COUNT(*) AS times
               FROM ebook_reads r JOIN books b ON b.id=r.book_id
               WHERE r.member_id=? GROUP BY r.book_id ORDER BY last_read DESC""",
            (member_id,),
        ).fetchall()
