# Library Management System

Python + SQLite library system with a **web app** (HTML/CSS/JavaScript frontend, Flask API)
and the original **command-line app**. Both share the same business logic and database.

## Features
- **Shelf:** the catalogue shown as book spines, coloured by genre; search and filter
- **Books and loans:** borrow for 14 days, return, Rs 2 per overdue day fine, overdue report
- **E-books:** read online in the browser; no copies or due dates
- **Write:** members and authors write e-books. Authors publish instantly; a member's
  e-book waits for librarian approval (librarians can preview, approve or reject)
- **Ratings:** 1-5 stars, only for books you borrowed or read
- **For you:** recommendations from genre and author match, readers with similar taste,
  average rating and popularity, each with a reason
- **Desk (librarians):** approvals, loans, lend a book, add to catalogue, manage member roles

## Run in VS Code
1. File > Open Folder > `library_management`
2. Install the **Python** extension
3. In the terminal: `pip install -r requirements.txt`
4. Press **F5** and choose **Run Web App**, then open http://127.0.0.1:5000
5. On the first visit choose **Load sample data** to try everything straight away

Command-line version: choose **Run Command-Line App**, or run `python main.py`.

## Sign-in
This is a demo: use the "Signed in as" menu to switch between members. There are no
passwords, so do not put it on a public server as it is. The API still checks the
selected member's role (for example, only librarians can approve e-books).

## API (JSON, prefix /api)
| Method | Path | Who |
|---|---|---|
| GET | /books, /books/<id> | everyone |
| POST | /books/<id>/borrow, /books/<id>/rate | member |
| POST | /loans/<id>/return | owner or librarian |
| GET | /ebooks/<id>/read, /recommendations, /loans/mine, /my/reads, /my/books | member |
| POST | /my/books | member (author publishes, member needs approval) |
| GET/POST | /pending, /pending/<id>/approve, /pending/<id>/reject | librarian |
| POST/DELETE | /books, /books/<id> | librarian |
| GET/POST/PATCH | /admin/members, /members, /members/<id>/role | librarian |

Requests send the chosen member in the `X-Member-Id` header.

## Tests
`python -m unittest discover -s tests -t .`  (20 tests: services, recommender, API)

## Structure
- `app.py` - Flask API and static file server
- `static/` - `index.html`, `css/styles.css`, `js/app.js`
- `library/` - database, services (all business rules), seed data, CLI
- `main.py` - command-line entry point
- `tests/` - unit and API tests
