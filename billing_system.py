#!/usr/bin/env python3
"""
Billing System - command-line app (Python 3.8+, standard library only).

Workflow: Select/Create Customer -> Select Products -> Enter Quantity ->
Calculate Bill -> Apply Discount/Tax -> Payment Method -> Generate Invoice ->
Update Stock -> Save Transaction

Roles:
  admin - products, categories, customers, users, transactions, reports, inventory
  staff - search products, create bills, record payments, print invoices, own history

First run creates a default admin:  username: admin   password: admin123
(change it from Admin > Manage users)
"""
import getpass
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

DB_FILE = "billing.db"
INVOICE_DIR = Path("invoices")
CURRENCY = "Rs."
TAX_RATE = Decimal("18")          # percent, applied after discount
STAFF_MAX_DISCOUNT = Decimal("10")  # percent a billing staff member may apply
LOW_STOCK = 5
PAYMENT_METHODS = ["Cash", "Card", "UPI"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
    salt TEXT NOT NULL, pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','staff')), active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS categories(
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS products(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, category_id INTEGER REFERENCES categories(id),
    price REAL NOT NULL CHECK(price >= 0), stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0));
CREATE TABLE IF NOT EXISTS customers(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT, email TEXT, address TEXT);
CREATE TABLE IF NOT EXISTS invoices(
    id INTEGER PRIMARY KEY, number TEXT UNIQUE, customer_id INTEGER REFERENCES customers(id),
    created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL,
    subtotal REAL, discount_pct REAL, discount_amt REAL, tax_pct REAL, tax_amt REAL,
    total REAL, payment_method TEXT, status TEXT NOT NULL DEFAULT 'PAID');
CREATE TABLE IF NOT EXISTS invoice_items(
    id INTEGER PRIMARY KEY, invoice_id INTEGER REFERENCES invoices(id),
    product_id INTEGER REFERENCES products(id), name TEXT, unit_price REAL, qty INTEGER, line_total REAL);
"""

# ----------------------------------------------------------------- helpers
db = None


def D(x):
    return Decimal(str(x))


def money(x):
    return D(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q(sql, args=()):
    return db.execute(sql, args).fetchall()


def hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def ask(prompt, default=None, required=True):
    while True:
        val = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
        if val:
            return val
        if default is not None:
            return str(default)
        if not required:
            return ""
        print("  A value is required.")


def ask_num(prompt, cast=int, default=None, minimum=0):
    while True:
        try:
            val = cast(ask(prompt, default))
            if val < minimum:
                raise ValueError
            return val
        except (ValueError, ArithmeticError):
            print(f"  Enter a valid number (>= {minimum}).")


def choose(title, options):
    print(f"\n== {title} ==")
    for i, o in enumerate(options, 1):
        print(f"  {i}. {o}")
    return ask_num("Choice", int, minimum=0)


def table(rows, headers):
    rows = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line + "\n" + "-" * len(line))
    for r in rows:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    if not rows:
        print("(none)")


# ----------------------------------------------------------------- auth
def init_db():
    global db
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    if not q("SELECT 1 FROM users"):
        add_user("admin", "admin123", "admin")
        db.commit()
        print("Default admin created -> admin / admin123 (please change it).")


def add_user(username, password, role):
    salt = secrets.token_hex(16)
    db.execute("INSERT INTO users(username,salt,pw_hash,role) VALUES(?,?,?,?)",
               (username, salt, hash_pw(password, salt), role))


def login():
    for _ in range(3):
        u = ask("Username")
        p = getpass.getpass("Password: ")
        row = q("SELECT * FROM users WHERE username=? AND active=1", (u,))
        if row and secrets.compare_digest(row[0]["pw_hash"], hash_pw(p, row[0]["salt"])):
            return row[0]
        print("  Invalid credentials.")
    return None


# ----------------------------------------------------------------- admin: catalogue
def manage_categories():
    while True:
        c = choose("Categories", ["List", "Add", "Rename", "Delete"]) 
        if c == 0:
            return
        if c == 1:
            table([(r["id"], r["name"]) for r in q("SELECT * FROM categories")], ["ID", "Name"])
        elif c == 2:
            try:
                db.execute("INSERT INTO categories(name) VALUES(?)", (ask("Name"),))
                db.commit()
            except sqlite3.IntegrityError:
                print("  Category already exists.")
        elif c == 3:
            db.execute("UPDATE categories SET name=? WHERE id=?",
                       (ask("New name"), ask_num("Category ID")))
            db.commit()
        elif c == 4:
            cid = ask_num("Category ID")
            if q("SELECT 1 FROM products WHERE category_id=?", (cid,)):
                print("  Category still has products.")
            else:
                db.execute("DELETE FROM categories WHERE id=?", (cid,))
                db.commit()


def list_products(term="", only_low=False):
    sql = ("SELECT p.id,p.name,COALESCE(c.name,'-') cat,p.price,p.stock FROM products p "
           "LEFT JOIN categories c ON c.id=p.category_id WHERE (p.name LIKE ? OR cat LIKE ?)")
    args = [f"%{term}%", f"%{term}%"]
    if only_low:
        sql += " AND p.stock<=?"
        args.append(LOW_STOCK)
    rows = q(sql + " ORDER BY p.name", args)
    table([(r["id"], r["name"], r["cat"], f"{r['price']:.2f}", r["stock"]) for r in rows],
          ["ID", "Product", "Category", "Price", "Stock"])
    return rows


def manage_products():
    while True:
        c = choose("Products & inventory", ["List/search", "Add product", "Update price",
                                           "Update stock (set)", "Add stock (+)", "Delete product",
                                           "Low-stock alert"])
        if c == 0:
            return
        if c == 1:
            list_products(ask("Search (blank = all)", required=False))
        elif c == 2:
            cats = q("SELECT * FROM categories")
            table([(r["id"], r["name"]) for r in cats], ["ID", "Category"])
            cid = ask("Category ID (blank = none)", required=False)
            db.execute("INSERT INTO products(name,category_id,price,stock) VALUES(?,?,?,?)",
                       (ask("Product name"), int(cid) if cid.isdigit() else None,
                        float(ask_num("Price", Decimal)), ask_num("Opening stock")))
            db.commit()
        elif c == 3:
            db.execute("UPDATE products SET price=? WHERE id=?",
                       (float(ask_num("New price", Decimal)), ask_num("Product ID")))
            db.commit()
        elif c == 4:
            db.execute("UPDATE products SET stock=? WHERE id=?",
                       (ask_num("New stock"), ask_num("Product ID")))
            db.commit()
        elif c == 5:
            db.execute("UPDATE products SET stock=stock+? WHERE id=?",
                       (ask_num("Quantity to add"), ask_num("Product ID")))
            db.commit()
        elif c == 6:
            try:
                db.execute("DELETE FROM products WHERE id=?", (ask_num("Product ID"),))
                db.commit()
            except sqlite3.IntegrityError:
                print("  Product is used in invoices; set stock to 0 instead.")
        elif c == 7:
            list_products(only_low=True)


# ----------------------------------------------------------------- customers & users
def manage_customers():
    while True:
        c = choose("Customers", ["List/search", "Add", "Edit", "Delete"])
        if c == 0:
            return
        if c == 1:
            find_customers(ask("Search name/phone (blank = all)", required=False))
        elif c == 2:
            create_customer()
        elif c == 3:
            cid = ask_num("Customer ID")
            db.execute("UPDATE customers SET name=?,phone=?,email=?,address=? WHERE id=?",
                       (ask("Name"), ask("Phone", required=False), ask("Email", required=False),
                        ask("Address", required=False), cid))
            db.commit()
        elif c == 4:
            try:
                db.execute("DELETE FROM customers WHERE id=?", (ask_num("Customer ID"),))
                db.commit()
            except sqlite3.IntegrityError:
                print("  Customer has invoices and cannot be deleted.")


def find_customers(term=""):
    rows = q("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
             (f"%{term}%", f"%{term}%"))
    table([(r["id"], r["name"], r["phone"], r["email"]) for r in rows], ["ID", "Name", "Phone", "Email"])
    return rows


def create_customer():
    cur = db.execute("INSERT INTO customers(name,phone,email,address) VALUES(?,?,?,?)",
                     (ask("Name"), ask("Phone", required=False), ask("Email", required=False),
                      ask("Address", required=False)))
    db.commit()
    return cur.lastrowid


def manage_users():
    while True:
        c = choose("Employees/users", ["List", "Add", "Activate/deactivate", "Reset password"])
        if c == 0:
            return
        if c == 1:
            table([(r["id"], r["username"], r["role"], "yes" if r["active"] else "no")
                   for r in q("SELECT * FROM users")], ["ID", "Username", "Role", "Active"])
        elif c == 2:
            role = "admin" if ask("Role (admin/staff)", "staff") == "admin" else "staff"
            try:
                add_user(ask("Username"), getpass.getpass("Password: "), role)
                db.commit()
            except sqlite3.IntegrityError:
                print("  Username already exists.")
        elif c == 3:
            db.execute("UPDATE users SET active=1-active WHERE id=?", (ask_num("User ID"),))
            db.commit()
        elif c == 4:
            salt = secrets.token_hex(16)
            db.execute("UPDATE users SET salt=?,pw_hash=? WHERE id=?",
                       (salt, hash_pw(getpass.getpass("New password: "), salt), ask_num("User ID")))
            db.commit()


# ----------------------------------------------------------------- billing
def new_bill(user):
    # 1. customer
    print("\n-- Customer --")
    term = ask("Search customer by name/phone (blank = create new)", required=False)
    if term:
        rows = find_customers(term)
        cid = ask_num("Customer ID (0 = create new)") if rows else 0
    else:
        cid = 0
    if cid == 0:
        cid = create_customer()
    customer = q("SELECT * FROM customers WHERE id=?", (cid,))
    if not customer:
        print("  Customer not found.")
        return
    customer = customer[0]

    # 2-3. products + quantities
    cart = {}  # product_id -> [name, price, qty]
    while True:
        term = ask("\nSearch product (blank = finish)", required=False)
        if not term:
            break
        rows = list_products(term)
        if not rows:
            continue
        pid = ask_num("Product ID (0 = cancel)")
        prod = q("SELECT * FROM products WHERE id=?", (pid,))
        if not prod:
            continue
        prod = prod[0]
        already = cart.get(pid, [0, 0, 0])[2]
        qty = ask_num(f"Quantity (in stock: {prod['stock'] - already})", int, minimum=1)
        if qty + already > prod["stock"]:
            print("  Not enough stock.")
            continue
        cart[pid] = [prod["name"], D(prod["price"]), already + qty]
        print(f"  Added. Items in cart: {len(cart)}")
    if not cart:
        print("  Cart is empty - bill cancelled.")
        return

    # 4-5. totals, discount, tax
    subtotal = sum(p * n for _, p, n in cart.values())
    limit = Decimal("100") if user["role"] == "admin" else STAFF_MAX_DISCOUNT
    while True:
        disc_pct = ask_num(f"Discount % (max {limit})", Decimal, default=0)
        if disc_pct <= limit:
            break
        print("  Not authorised for that discount.")
    disc_amt = money(subtotal * disc_pct / 100)
    tax_amt = money((subtotal - disc_amt) * TAX_RATE / 100)
    total = money(subtotal - disc_amt + tax_amt)
    print(f"\nSubtotal {money(subtotal)} | Discount {disc_amt} | Tax {tax_amt} | TOTAL {total}")

    # 6. payment
    method = PAYMENT_METHODS[choose("Payment method", PAYMENT_METHODS) - 1]
    if method == "Cash":
        paid = ask_num("Cash received", Decimal, default=total, minimum=total)
        print(f"  Change due: {money(paid - total)}")

    # 7-9. save invoice, update stock, store transaction (atomic)
    try:
        cur = db.execute(
            "INSERT INTO invoices(customer_id,created_by,created_at,subtotal,discount_pct,discount_amt,"
            "tax_pct,tax_amt,total,payment_method) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (cid, user["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), float(money(subtotal)),
             float(disc_pct), float(disc_amt), float(TAX_RATE), float(tax_amt), float(total), method))
        inv_id = cur.lastrowid
        number = f"INV-{inv_id:05d}"
        db.execute("UPDATE invoices SET number=? WHERE id=?", (number, inv_id))
        for pid, (name, price, qty) in cart.items():
            upd = db.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (qty, pid, qty))
            if upd.rowcount == 0:
                raise RuntimeError(f"Insufficient stock for {name}")
            db.execute("INSERT INTO invoice_items(invoice_id,product_id,name,unit_price,qty,line_total)"
                       " VALUES(?,?,?,?,?,?)", (inv_id, pid, name, float(price), qty, float(money(price * qty))))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  Bill failed and was rolled back: {e}")
        return
    path = write_invoice(inv_id)
    print(f"\nInvoice {number} saved -> {path}")
    print(path.read_text())


def render_invoice(inv_id):
    inv = q("SELECT i.*, c.name cname, c.phone, c.address, u.username FROM invoices i "
            "JOIN customers c ON c.id=i.customer_id JOIN users u ON u.id=i.created_by WHERE i.id=?", (inv_id,))[0]
    items = q("SELECT * FROM invoice_items WHERE invoice_id=?", (inv_id,))
    w = 62
    out = ["=" * w, "INVOICE".center(w), "=" * w,
           f"Invoice No : {inv['number']}   Status: {inv['status']}",
           f"Date       : {inv['created_at']}",
           f"Billed by  : {inv['username']}",
           f"Customer   : {inv['cname']}  {inv['phone'] or ''}", "-" * w,
           f"{'Item':<28}{'Qty':>5}{'Price':>13}{'Total':>16}", "-" * w]
    for it in items:
        out.append(f"{it['name'][:27]:<28}{it['qty']:>5}{it['unit_price']:>13.2f}{it['line_total']:>16.2f}")
    out += ["-" * w,
            f"{'Subtotal':<46}{inv['subtotal']:>16.2f}",
            f"{'Discount (' + str(inv['discount_pct']) + '%)':<46}{-inv['discount_amt']:>16.2f}",
            f"{'Tax (' + str(inv['tax_pct']) + '%)':<46}{inv['tax_amt']:>16.2f}",
            f"{'TOTAL (' + CURRENCY + ')':<46}{inv['total']:>16.2f}",
            f"Payment    : {inv['payment_method']}", "=" * w, "Thank you for your business!".center(w)]
    return "\n".join(out) + "\n"


def write_invoice(inv_id):
    INVOICE_DIR.mkdir(exist_ok=True)
    number = q("SELECT number FROM invoices WHERE id=?", (inv_id,))[0]["number"]
    path = INVOICE_DIR / f"{number}.txt"
    path.write_text(render_invoice(inv_id))
    return path


# ----------------------------------------------------------------- transactions
def view_transactions(user):
    sql = ("SELECT i.id,i.number,i.created_at,c.name cname,i.total,i.payment_method,i.status FROM invoices i "
           "JOIN customers c ON c.id=i.customer_id")
    args = []
    if user["role"] != "admin":      # staff only see their own history
        sql += " WHERE i.created_by=?"
        args.append(user["id"])
    rows = q(sql + " ORDER BY i.id DESC LIMIT 50", args)
    table([(r["number"], r["created_at"], r["cname"], f"{r['total']:.2f}", r["payment_method"], r["status"])
           for r in rows], ["Invoice", "Date", "Customer", "Total", "Payment", "Status"])
    return rows


def transactions_menu(user):
    while True:
        opts = ["View recent", "Print/re-download invoice"]
        if user["role"] == "admin":
            opts += ["Cancel transaction (restores stock)", "Change payment method"]
        c = choose("Transactions", opts)
        if c == 0:
            return
        if c == 1:
            view_transactions(user)
        elif c == 2:
            rows = view_transactions(user)
            num = ask("Invoice number (e.g. INV-00001)").upper()
            if any(r["number"] == num for r in rows):
                inv_id = [r["id"] for r in rows if r["number"] == num][0]
                print(write_invoice(inv_id).read_text())
            else:
                print("  Not found in your visible history.")
        elif c == 3 and user["role"] == "admin":
            num = ask("Invoice number to cancel").upper()
            inv = q("SELECT * FROM invoices WHERE number=? AND status='PAID'", (num,))
            if inv and ask("Type YES to confirm").upper() == "YES":
                for it in q("SELECT * FROM invoice_items WHERE invoice_id=?", (inv[0]["id"],)):
                    db.execute("UPDATE products SET stock=stock+? WHERE id=?", (it["qty"], it["product_id"]))
                db.execute("UPDATE invoices SET status='CANCELLED' WHERE id=?", (inv[0]["id"],))
                db.commit()
                write_invoice(inv[0]["id"])
                print("  Cancelled and stock restored.")
            else:
                print("  Nothing cancelled.")
        elif c == 4 and user["role"] == "admin":
            num = ask("Invoice number").upper()
            m = PAYMENT_METHODS[choose("New payment method", PAYMENT_METHODS) - 1]
            db.execute("UPDATE invoices SET payment_method=? WHERE number=? AND status='PAID'", (m, num))
            db.commit()


# ----------------------------------------------------------------- reports
def sales_report():
    c = choose("Sales report", ["Daily (today)", "Weekly (last 7 days)", "Monthly (last 30 days)"])
    if c == 0:
        return
    days = {1: 0, 2: 6, 3: 29}[c]
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    s = q("SELECT COUNT(*) n, COALESCE(SUM(subtotal),0) sub, COALESCE(SUM(discount_amt),0) disc, "
          "COALESCE(SUM(tax_amt),0) tax, COALESCE(SUM(total),0) tot FROM invoices "
          "WHERE status='PAID' AND created_at>=?", (start,))[0]
    print(f"\nSince {start[:10]}: {s['n']} invoices | Subtotal {s['sub']:.2f} | Discounts {s['disc']:.2f} "
          f"| Tax {s['tax']:.2f} | Revenue {s['tot']:.2f}")
    top = q("SELECT it.name, SUM(it.qty) qty, SUM(it.line_total) amt FROM invoice_items it "
            "JOIN invoices i ON i.id=it.invoice_id WHERE i.status='PAID' AND i.created_at>=? "
            "GROUP BY it.name ORDER BY qty DESC LIMIT 5", (start,))
    print("\nTop products:")
    table([(r["name"], r["qty"], f"{r['amt']:.2f}") for r in top], ["Product", "Qty sold", "Amount"])
    by_pay = q("SELECT payment_method, COUNT(*) n, SUM(total) t FROM invoices WHERE status='PAID' "
               "AND created_at>=? GROUP BY payment_method", (start,))
    print("\nBy payment method:")
    table([(r["payment_method"], r["n"], f"{r['t']:.2f}") for r in by_pay], ["Method", "Invoices", "Amount"])


# ----------------------------------------------------------------- menus
def admin_menu(user):
    actions = [("Create bill", lambda: new_bill(user)), ("Products & inventory", manage_products),
               ("Categories", manage_categories), ("Customers", manage_customers),
               ("Employees/users", manage_users), ("Transactions", lambda: transactions_menu(user)),
               ("Sales reports", sales_report)]
    run_menu(f"ADMIN MENU ({user['username']})", actions)


def staff_menu(user):
    actions = [("Create bill", lambda: new_bill(user)),
               ("Search products", lambda: list_products(ask("Search", required=False))),
               ("My transactions / print invoice", lambda: transactions_menu(user))]
    run_menu(f"BILLING MENU ({user['username']})", actions)


def run_menu(title, actions):
    while True:
        c = choose(title, [a[0] for a in actions])
        if c == 0:
            print("Logged out.")
            return
        if 1 <= c <= len(actions):
            actions[c - 1][1]()
        else:
            print("  Invalid choice.")


def main():
    init_db()
    print("=== Billing System === (0 = back/logout in menus)")
    user = login()
    if not user:
        return
    (admin_menu if user["role"] == "admin" else staff_menu)(user)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nBye.")
