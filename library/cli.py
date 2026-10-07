from pathlib import Path

from .seed import load_sample_data
from .services import LibraryError, LibraryService


# ---------- input / output helpers ----------
def ask_int(prompt):
    try:
        return int(input(prompt).strip())
    except ValueError:
        raise LibraryError("Please enter a valid number.")


def ask_text():
    path = input("Path to a .txt file (or press Enter to type it here): ").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as e:
            raise LibraryError(f"Could not read that file: {e}")
    print("Type your text. Finish with a line containing only END.")
    lines = []
    while (line := input()) != "END":
        lines.append(line)
    return "\n".join(lines)


def show(rows, cols):
    if not rows:
        print("  (nothing to show)")
        return
    print("  " + " | ".join(c.upper() for c in cols))
    print("  " + "-" * 70)
    for r in rows:
        print("  " + " | ".join(str(r[c]) for c in cols))


def submenu(title, options):
    """options: {key: (label, function)}. Loops until 0."""
    while True:
        print(f"\n--- {title} ---")
        for key, (label, _) in options.items():
            print(f" {key}. {label}")
        print(" 0. Back")
        choice = input("Choose: ").strip()
        if choice == "0":
            return
        if choice not in options:
            print("Invalid option.")
            continue
        try:
            options[choice][1]()
        except LibraryError as e:
            print(f"Error: {e}")


# ---------- menus ----------
def books_menu(svc):
    def add():
        bid = svc.add_book(input("Title: "), input("Author: "), input("ISBN (optional): "),
                           ask_int("Copies: "), input("Genre: "), input("Short description: "))
        print(f"Book added with ID {bid}.")

    def remove():
        svc.remove_book(ask_int("Book ID: "))
        print("Book removed.")

    cols = ["id", "title", "author", "genre", "format", "available"]
    submenu("Books", {
        "1": ("Add physical book", add),
        "2": ("List all books", lambda: show(svc.list_books(), cols)),
        "3": ("Search (title, author, ISBN, genre)",
              lambda: show(svc.search_books(input("Search term: ")), cols)),
        "4": ("Remove book", remove),
    })


def members_menu(svc):
    def add():
        role = input("Role (member/author/librarian) [member]: ").strip() or "member"
        mid = svc.add_member(input("Name: "), input("Email (optional): "), role)
        print(f"Member added with ID {mid}.")

    def promote():
        svc.set_role(ask_int("Member ID: "), input("New role (member/author/librarian): ").strip())
        print("Role updated.")

    submenu("Members", {
        "1": ("Add member", add),
        "2": ("List members", lambda: show(svc.list_members(), ["id", "name", "email", "role"])),
        "3": ("Change a member's role (e.g. make an author)", promote),
    })


def loans_menu(svc):
    def issue():
        due, loan_id = svc.issue_book(ask_int("Book ID: "), ask_int("Member ID: "))
        print(f"Book issued (loan ID {loan_id}). Due on {due}.")

    def give_back():
        fine = svc.return_book(ask_int("Loan ID: "))
        print(f"Book returned. Fine: Rs {fine:.2f}")

    submenu("Loans", {
        "1": ("Issue book", issue),
        "2": ("Return book", give_back),
        "3": ("Active loans", lambda: show(svc.active_loans(),
                                           ["id", "title", "member", "issue_date", "due_date"])),
        "4": ("Overdue report", lambda: show(svc.overdue_loans(),
                                             ["id", "title", "member", "due_date"])),
    })


def ebooks_menu(svc):
    def read():
        book = svc.read_ebook(ask_int("Member ID: "), ask_int("E-book ID: "))
        print(f"\n===== {book['title']} - {book['author']} =====\n")
        print(book["content"])
        print("\n===== end =====")

    def add():
        title, author = input("Title: "), input("Author: ")
        genre, desc = input("Genre: "), input("Short description: ")
        bid = svc.add_ebook(title, author, ask_text(), genre, desc)
        print(f"E-book added with ID {bid}.")

    def rate():
        svc.rate_book(ask_int("Member ID: "), ask_int("Book ID: "), ask_int("Rating (1-5): "))
        print("Thanks for rating!")

    submenu("E-books", {
        "1": ("Browse e-books", lambda: show(svc.list_books("ebook"),
                                             ["id", "title", "author", "genre"])),
        "2": ("Read an e-book", read),
        "3": ("Add an e-book (librarian)", add),
        "4": ("Rate a book you borrowed or read", rate),
    })


def author_studio_menu(svc):
    def create():
        member_id = ask_int("Your member ID: ")
        title, genre = input("Title: "), input("Genre: ")
        desc = input("Short description: ")
        book_id, status = svc.create_book(member_id, title, ask_text(), genre, desc)
        if status == "published":
            print(f"Published! Your e-book has ID {book_id}.")
        else:
            print(f"Submitted (ID {book_id}). A librarian must approve it before it goes live.")

    submenu("Author Studio", {
        "1": ("Write a new e-book", create),
        "2": ("My creations", lambda: show(svc.my_creations(ask_int("Your member ID: ")),
                                           ["id", "title", "genre", "status"])),
        "3": ("Pending submissions (librarian)", lambda: show(svc.pending_books(),
                                                              ["id", "title", "author", "genre"])),
        "4": ("Approve a submission (librarian)",
              lambda: (svc.approve_book(ask_int("Book ID: ")), print("Approved and published."))),
        "5": ("Reject a submission (librarian)",
              lambda: (svc.reject_book(ask_int("Book ID: ")), print("Submission rejected."))),
    })


def recommend_menu(svc):
    def for_member():
        rows = svc.recommend(ask_int("Member ID: "))
        show(rows, ["id", "title", "author", "format", "reason"])

    submenu("Recommendations", {"1": ("Recommend books for a member", for_member)})


def load_sample(svc):
    load_sample_data(svc)
    print("Sample data loaded: 5 members (IDs 1-5), physical books, e-books and history.")
    print("Try Recommendations for member 2 (Asha) or 3 (Ravi).")


def run():
    svc = LibraryService()
    while True:
        print("""
========== LIBRARY MANAGEMENT SYSTEM ==========
 1. Books            5. Author Studio
 2. Members          6. Recommendations
 3. Loans            7. Load sample data
 4. E-books          0. Exit
===============================================""")
        choice = input("Choose: ").strip()
        try:
            if choice == "1":
                books_menu(svc)
            elif choice == "2":
                members_menu(svc)
            elif choice == "3":
                loans_menu(svc)
            elif choice == "4":
                ebooks_menu(svc)
            elif choice == "5":
                author_studio_menu(svc)
            elif choice == "6":
                recommend_menu(svc)
            elif choice == "7":
                load_sample(svc)
            elif choice == "0":
                print("Goodbye!")
                break
            else:
                print("Invalid option.")
        except LibraryError as e:
            print(f"Error: {e}")
