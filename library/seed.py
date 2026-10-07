"""Demo data so you can try recommendations straight away."""
from .services import LibraryError

BASICS = (
    "Python is a readable, general-purpose language. A program is a list of statements. "
    "Variables hold values, functions package logic, and loops repeat work.\n\n"
    "Start small: print a message, read some input, then combine both in a function."
)
DESIGN = (
    "Design thinking has five stages: empathise, define, ideate, prototype and test. "
    "Begin by talking to the people who will use your product.\n\n"
    "Turn what you learn into a clear problem statement, sketch many ideas, build a "
    "cheap prototype, and let real users try it."
)
LOGIC = (
    "Logic gates are the building blocks of digital circuits. AND outputs 1 only when "
    "both inputs are 1. OR outputs 1 when at least one input is 1. NOT flips its input.\n\n"
    "Combining gates gives adders, multiplexers and memory elements."
)
DIARY = (
    "Day one at college: new faces, a huge campus and a canteen that never has enough "
    "chairs. By the end of the week the place already felt like home."
)


def load_sample_data(svc):
    if svc.list_books() or svc.list_members():
        raise LibraryError("The library already has data, so sample data was skipped.")

    admin = svc.add_member("Admin Librarian", "admin@library.local", "librarian")
    asha = svc.add_member("Asha", "asha@example.com")
    ravi = svc.add_member("Ravi", "ravi@example.com")
    karthik = svc.add_member("Karthik", "karthik@example.com")
    meena = svc.add_member("Meena", "meena@example.com", "author")

    clean = svc.add_book("Clean Code", "Robert C. Martin", "9780132350884", 2, "Technology")
    prag = svc.add_book("The Pragmatic Programmer", "Andrew Hunt", "9780135957059", 1, "Technology")
    algo = svc.add_book("Introduction to Algorithms", "Thomas Cormen", "9780262046305", 1, "Technology")
    svc.add_book("Computer Organization", "Carl Hamacher", "9780073380650", 1, "Technology")
    alch = svc.add_book("The Alchemist", "Paulo Coelho", "9780062315007", 1, "Fiction")
    svc.add_book("Malgudi Days", "R. K. Narayan", "9780143039655", 1, "Fiction")
    svc.add_book("Wings of Fire", "A. P. J. Abdul Kalam", "9788173711466", 1, "Biography")
    svc.add_book("The Design of Everyday Things", "Don Norman", "9780465050659", 1, "Design")

    py, _ = svc.create_book(meena, "Python Basics for Beginners", BASICS, "Technology",
                            "A gentle first look at Python.")
    dt, _ = svc.create_book(meena, "Design Thinking Handbook", DESIGN, "Design",
                            "The five stages in plain language.")
    logic = svc.add_ebook("Intro to Logic Gates", "S. Kumar", LOGIC, "Technology",
                          "Digital logic for first-year students.")
    svc.create_book(karthik, "My Campus Diary", DIARY, "Fiction", "Notes from week one.")

    # Borrowing and reading history
    _, l1 = svc.issue_book(clean, asha)
    svc.return_book(l1)
    _, l2 = svc.issue_book(prag, asha)
    svc.return_book(l2)
    svc.read_ebook(asha, py)
    _, l3 = svc.issue_book(clean, ravi)
    svc.return_book(l3)
    _, l4 = svc.issue_book(algo, ravi)
    svc.return_book(l4)
    svc.read_ebook(ravi, logic)
    _, l5 = svc.issue_book(alch, karthik)
    svc.return_book(l5)
    svc.read_ebook(karthik, dt)

    for member, book, stars in [(asha, clean, 5), (asha, prag, 4), (ravi, clean, 4),
                                (ravi, algo, 5), (karthik, alch, 5), (asha, py, 5)]:
        svc.rate_book(member, book, stars)
    return admin
