"""Flask API + static web frontend for the Library Management System.

Run:  python app.py   then open http://127.0.0.1:5000
Sign-in is a demo member switcher (no passwords): the browser sends the chosen
member in the X-Member-Id header and the API checks that member's role.
"""
from flask import Flask, g, jsonify, request, send_from_directory

from library.database import DB_PATH, get_connection
from library.seed import load_sample_data
from library.services import LibraryError, LibraryService


class AuthError(Exception):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.message, self.status = message, status


def _number(data, key, default=None):
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise LibraryError(f"'{key}' must be a number.")


def _text(data, key):
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def create_app(db_path=None):
    db_path = str(db_path or DB_PATH)
    get_connection(db_path).close()  # create or upgrade the schema once, at startup
    app = Flask(__name__, static_folder="static", static_url_path="")

    # ---------- per-request plumbing ----------
    def svc():
        if "svc" not in g:
            g.svc = LibraryService(db_path, init=False)
        return g.svc

    @app.teardown_appcontext
    def close_service(_):
        service = g.pop("svc", None)
        if service:
            service.conn.close()

    def maybe_me():
        raw = request.headers.get("X-Member-Id", "")
        if not raw.isdigit():
            return None
        try:
            return svc().get_member(int(raw))
        except LibraryError:
            return None

    def me():
        member = maybe_me()
        if not member:
            raise AuthError("Choose who you are signed in as.")
        return member

    def librarian():
        member = me()
        if member["role"] != "librarian":
            raise AuthError("Only librarians can do that.", 403)
        return member

    @app.errorhandler(LibraryError)
    def library_error(e):
        message = str(e)
        return jsonify(error=message), (404 if message.endswith("not found.") else 400)

    @app.errorhandler(AuthError)
    def auth_error(e):
        return jsonify(error=e.message), e.status

    def book_json(row, ratings):
        data = {k: row[k] for k in row.keys() if k != "content"}  # never leak e-book text
        rating = ratings.get(row["id"])
        data["avg_rating"] = rating["avg"] if rating else None
        data["rating_count"] = rating["count"] if rating else 0
        return data

    def rows(result):
        return [dict(r) for r in result]

    # ---------- pages ----------
    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    # ---------- first-run setup ----------
    @app.post("/api/setup")
    def setup():
        s = svc()
        if s.list_members():
            raise LibraryError("The library is already set up.")
        data = request.get_json(silent=True) or {}
        if data.get("sample"):
            load_sample_data(s)
        else:
            s.add_member(_text(data, "name"), _text(data, "email"), "librarian")
        return jsonify(ok=True), 201

    # ---------- members ----------
    @app.get("/api/members")
    def members():
        return jsonify([{"id": m["id"], "name": m["name"], "role": m["role"]}
                        for m in svc().list_members()])

    @app.get("/api/admin/members")
    def admin_members():
        librarian()
        return jsonify(rows(svc().list_members()))

    @app.post("/api/members")
    def add_member():
        librarian()
        data = request.get_json(silent=True) or {}
        member_id = svc().add_member(_text(data, "name"), _text(data, "email"),
                                     _text(data, "role") or "member")
        return jsonify(id=member_id), 201

    @app.patch("/api/members/<int:member_id>/role")
    def change_role(member_id):
        librarian()
        svc().set_role(member_id, _text(request.get_json(silent=True) or {}, "role"))
        return jsonify(ok=True)

    # ---------- catalogue ----------
    @app.get("/api/books")
    def books():
        s = svc()
        term, fmt = request.args.get("q", "").strip(), request.args.get("format")
        found = s.search_books(term) if term else s.list_books()
        if fmt in ("physical", "ebook"):
            found = [b for b in found if b["format"] == fmt]
        ratings = s.rating_map()
        return jsonify([book_json(b, ratings) for b in found])

    @app.get("/api/books/<int:book_id>")
    def book_detail(book_id):
        s = svc()
        book = s.get_book(book_id)
        data = book_json(book, s.rating_map())
        member = maybe_me()
        data["my_rating"] = data["can_rate"] = data["my_loan"] = None
        if member:
            data["my_rating"] = s.my_rating(member["id"], book_id)
            data["can_rate"] = s.can_rate(member["id"], book_id)
            loan = s.active_loan_for(member["id"], book_id)
            data["my_loan"] = dict(loan) if loan else None
        return jsonify(data)

    @app.post("/api/books")
    def add_book():
        librarian()
        s, data = svc(), request.get_json(silent=True) or {}
        title, author = _text(data, "title"), _text(data, "author")
        genre, description = _text(data, "genre") or "General", _text(data, "description")
        if data.get("format") == "ebook":
            book_id = s.add_ebook(title, author, data.get("content") or "", genre, description,
                                  _text(data, "isbn"))
        else:
            book_id = s.add_book(title, author, _text(data, "isbn"), _number(data, "copies", 1),
                                 genre, description)
        return jsonify(id=book_id), 201

    @app.delete("/api/books/<int:book_id>")
    def remove_book(book_id):
        librarian()
        svc().remove_book(book_id)
        return jsonify(ok=True)

    @app.post("/api/books/<int:book_id>/rate")
    def rate(book_id):
        member = me()
        svc().rate_book(member["id"], book_id, _number(request.get_json(silent=True) or {}, "rating"))
        return jsonify(ok=True)

    # ---------- loans ----------
    @app.post("/api/books/<int:book_id>/borrow")
    def borrow(book_id):
        member = me()
        data = request.get_json(silent=True) or {}
        target = member["id"]
        if data.get("member_id") not in (None, member["id"]):
            librarian()
            target = _number(data, "member_id")
        due, loan_id = svc().issue_book(book_id, target)
        return jsonify(loan_id=loan_id, due_date=due.isoformat()), 201

    @app.post("/api/loans/<int:loan_id>/return")
    def return_loan(loan_id):
        member, s = me(), svc()
        loan = s.get_loan(loan_id)
        if loan["member_id"] != member["id"] and member["role"] != "librarian":
            raise AuthError("That loan belongs to another member.", 403)
        return jsonify(fine=s.return_book(loan_id))

    @app.get("/api/loans/mine")
    def my_loans():
        return jsonify(rows(svc().member_loans(me()["id"])))

    @app.get("/api/loans")
    def active_loans():
        librarian()
        return jsonify(rows(svc().active_loans()))

    @app.get("/api/loans/overdue")
    def overdue_loans():
        librarian()
        return jsonify(rows(svc().overdue_loans()))

    # ---------- e-books ----------
    @app.get("/api/ebooks/<int:book_id>/read")
    def read_ebook(book_id):
        member, s = me(), svc()
        book = s.read_ebook(member["id"], book_id)
        data = {k: book[k] for k in ("id", "title", "author", "genre", "content")}
        data["my_rating"] = s.my_rating(member["id"], book_id)
        return jsonify(data)

    @app.get("/api/my/reads")
    def my_reads():
        return jsonify(rows(svc().member_reads(me()["id"])))

    # ---------- author studio ----------
    @app.get("/api/my/books")
    def my_books():
        return jsonify(rows(svc().my_creations(me()["id"])))

    @app.post("/api/my/books")
    def create_book():
        member = me()
        data = request.get_json(silent=True) or {}
        book_id, status = svc().create_book(member["id"], _text(data, "title"),
                                            data.get("content") or "",
                                            _text(data, "genre") or "General",
                                            _text(data, "description"))
        return jsonify(id=book_id, status=status), 201

    @app.get("/api/pending")
    def pending():
        librarian()
        return jsonify(rows(svc().pending_books()))

    @app.get("/api/pending/<int:book_id>")
    def pending_preview(book_id):
        librarian()
        book = svc().get_book(book_id, published_only=False)
        return jsonify({k: book[k] for k in ("id", "title", "author", "genre", "content")})

    @app.post("/api/pending/<int:book_id>/approve")
    def approve(book_id):
        librarian()
        svc().approve_book(book_id)
        return jsonify(ok=True)

    @app.post("/api/pending/<int:book_id>/reject")
    def reject(book_id):
        librarian()
        svc().reject_book(book_id)
        return jsonify(ok=True)

    # ---------- recommendations ----------
    @app.get("/api/recommendations")
    def recommendations():
        limit = min(max(request.args.get("limit", 6, type=int), 1), 20)
        return jsonify(svc().recommend(me()["id"], limit))

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
