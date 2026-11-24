import os
import tempfile
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta

TAX_RATE = 18             
STAFF_MAX_DISCOUNT = 10   

db = sqlite3.connect("billing.db")
cur = db.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users(
username TEXT PRIMARY KEY, password TEXT, role TEXT)""")

cur.execute("""CREATE TABLE IF NOT EXISTS products(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT, category TEXT, price REAL, stock INTEGER)""")

cur.execute("""CREATE TABLE IF NOT EXISTS customers(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT, phone TEXT)""")

cur.execute("""CREATE TABLE IF NOT EXISTS sales(
id INTEGER PRIMARY KEY AUTOINCREMENT,
customer TEXT, subtotal REAL, discount REAL,
tax REAL, total REAL, payment TEXT,
date TEXT, status TEXT)""")

cur.execute("""CREATE TABLE IF NOT EXISTS sale_items(
id INTEGER PRIMARY KEY AUTOINCREMENT,
sale_id INTEGER, product TEXT, quantity INTEGER,
price REAL, amount REAL)""")

try:
    cur.execute("ALTER TABLE sales ADD COLUMN cashier TEXT")
except sqlite3.OperationalError:
    pass  
cur.execute("SELECT * FROM users WHERE username='admin'")
if not cur.fetchone():
    cur.execute("INSERT INTO users VALUES(?,?,?)",
                ("admin", "admin123", "Admin"))

db.commit()

content_frame = None
cart = []            
current_user = ""
current_role = ""

root = tk.Tk()
root.title("Billing Management System")
root.geometry("1100x700")


def login():
    global current_user, current_role

    username = user_entry.get()
    password = pass_entry.get()

    cur.execute("SELECT * FROM users WHERE username=? AND password=?",
                (username, password))
    result = cur.fetchone()

    if result:
        current_user = result[0]
        current_role = result[2]
        login_frame.destroy()
        main_screen()
    else:
        messagebox.showerror("Error", "Invalid username or password")


def logout():
    if messagebox.askyesno("Logout", "Do you want to logout?"):
        root.destroy()


def clear_entries(entries):
    for entry in entries:
        entry.delete(0, tk.END)


def clear_content():
    if content_frame is None:
        return
    for widget in content_frame.winfo_children():
        widget.destroy()


def build_invoice_text(sale_id):
    cur.execute("""SELECT customer,subtotal,discount,tax,total,payment,date,cashier
                   FROM sales WHERE id=?""", (sale_id,))
    customer, sub, d, t, total, method, date, cashier = cur.fetchone()
    cur.execute("""SELECT product,quantity,price,amount
                   FROM sale_items WHERE sale_id=?""", (sale_id,))
    items = cur.fetchall()

    disc_amt = sub * d / 100
    tax_amt = (sub - disc_amt) * t / 100

    text = f"""
==============================================
                BILLING SYSTEM
==============================================
Invoice Number : {sale_id}
Date           : {date}
Customer       : {customer}
Billed by      : {cashier or '-'}
----------------------------------------------
{'Product':<18}{'Qty':>5}{'Price':>11}{'Amount':>11}
----------------------------------------------
"""
    for name, qty, price, amount in items:
        text += f"{name[:17]:<18}{qty:>5}{price:>11.2f}{amount:>11.2f}\n"

    text += f"""----------------------------------------------
Subtotal       : Rs. {sub:.2f}
Discount ({d:g}%) : Rs. {disc_amt:.2f}
Tax ({t:g}%)      : Rs. {tax_amt:.2f}
TOTAL          : Rs. {total:.2f}
Payment        : {method}
----------------------------------------------
            THANK YOU! VISIT AGAIN
==============================================
"""
    return text


def export_invoice(sale_id):
    """Download (save as .txt) and optionally print an invoice."""
    text = build_invoice_text(sale_id)

    path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        initialfile=f"Invoice_{sale_id}.txt",
        filetypes=[("Text files", "*.txt")])
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    if messagebox.askyesno("Print", "Print this invoice?"):
        tmp = os.path.join(tempfile.gettempdir(), f"Invoice_{sale_id}.txt")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            os.startfile(tmp, "print")      
        except (AttributeError, OSError):
            messagebox.showinfo(
                "Print",
                "Could not print automatically. Open the saved file and print it.")



def product_screen():
    clear_content()

    tk.Label(content_frame, text="PRODUCT MANAGEMENT",
             font=("Arial", 18, "bold")).pack(pady=10)

    frame = tk.Frame(content_frame)
    frame.pack(pady=10)

    labels = ["Product Name", "Category", "Price", "Stock"]
    entries = []

    for i, label in enumerate(labels):
        tk.Label(frame, text=label).grid(row=i, column=0, padx=10, pady=7)
        e = tk.Entry(frame, width=30)
        e.grid(row=i, column=1, padx=10, pady=7)
        entries.append(e)

    name, category, price, stock = entries

    tree = ttk.Treeview(content_frame,
                        columns=("ID", "Name", "Category", "Price", "Stock"),
                        show="headings")
    for col in ("ID", "Name", "Category", "Price", "Stock"):
        tree.heading(col, text=col)
        tree.column(col, width=130)
    tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh():
        tree.delete(*tree.get_children())
        cur.execute("SELECT * FROM products")
        for row in cur.fetchall():
            tree.insert("", "end", values=row)

    def add_product():
        try:
            if not name.get().strip() or not category.get().strip():
                raise ValueError("Enter product name and category")

            p = float(price.get())
            s = int(stock.get())

            if p < 0 or s < 0:
                raise ValueError("Price and stock cannot be negative")

            cur.execute("""INSERT INTO products
                (name,category,price,stock) VALUES(?,?,?,?)""",
                        (name.get(), category.get(), p, s))
            db.commit()
            clear_entries(entries)
            refresh()
            messagebox.showinfo("Success", "Product added")

        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def select_product(event):
        selected = tree.selection()
        if selected:
            values = tree.item(selected[0])["values"]
            for e, v in zip(entries, values[1:]):
                e.delete(0, tk.END)
                e.insert(0, v)

    def update_product():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a product")
            return

        try:
            product_id = tree.item(selected[0])["values"][0]
            p = float(price.get())
            s = int(stock.get())

            if p < 0 or s < 0:
                raise ValueError("Price and stock cannot be negative")

            cur.execute("""UPDATE products SET name=?, category=?,
                price=?, stock=? WHERE id=?""",
                        (name.get(), category.get(), p, s, product_id))
            db.commit()
            refresh()
            messagebox.showinfo("Success", "Product updated")

        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def delete_product():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a product")
            return

        product_id = tree.item(selected[0])["values"][0]

        if messagebox.askyesno("Confirm", "Delete this product?"):
            cur.execute("DELETE FROM products WHERE id=?", (product_id,))
            db.commit()
            refresh()

    tree.bind("<<TreeviewSelect>>", select_product)

    buttons = tk.Frame(content_frame)
    buttons.pack(pady=10)

    tk.Button(buttons, text="Add Product",
              command=add_product, width=15).pack(side="left", padx=5)
    tk.Button(buttons, text="Update",
              command=update_product, width=15).pack(side="left", padx=5)
    tk.Button(buttons, text="Delete",
              command=delete_product, width=15).pack(side="left", padx=5)

    refresh()


def customer_screen():
    clear_content()

    tk.Label(content_frame, text="CUSTOMER MANAGEMENT",
             font=("Arial", 18, "bold")).pack(pady=15)

    frame = tk.Frame(content_frame)
    frame.pack()

    tk.Label(frame, text="Customer Name").grid(row=0, column=0, padx=10, pady=10)
    name = tk.Entry(frame, width=30)
    name.grid(row=0, column=1)

    tk.Label(frame, text="Phone Number").grid(row=1, column=0, padx=10, pady=10)
    phone = tk.Entry(frame, width=30)
    phone.grid(row=1, column=1)

    tree = ttk.Treeview(content_frame, columns=("ID", "Name", "Phone"),
                        show="headings")
    for col in ("ID", "Name", "Phone"):
        tree.heading(col, text=col)
        tree.column(col, width=180)
    tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh():
        tree.delete(*tree.get_children())
        cur.execute("SELECT * FROM customers")
        for row in cur.fetchall():
            tree.insert("", "end", values=row)

    def add():
        if not name.get().strip() or not phone.get().strip():
            messagebox.showerror("Error", "Enter customer details")
            return

        cur.execute("INSERT INTO customers(name,phone) VALUES(?,?)",
                    (name.get(), phone.get()))
        db.commit()
        name.delete(0, tk.END)
        phone.delete(0, tk.END)
        refresh()

    def delete():
        selected = tree.selection()
        if not selected:
            return

        customer_id = tree.item(selected[0])["values"][0]

        if messagebox.askyesno("Confirm", "Delete customer?"):
            cur.execute("DELETE FROM customers WHERE id=?", (customer_id,))
            db.commit()
            refresh()

    tk.Button(content_frame, text="Add Customer",
              command=add).pack(side="left", padx=150)
    tk.Button(content_frame, text="Delete Customer",
              command=delete).pack(side="left")

    refresh()


def user_screen():
    clear_content()

    tk.Label(content_frame, text="EMPLOYEE MANAGEMENT",
             font=("Arial", 18, "bold")).pack(pady=15)

    frame = tk.Frame(content_frame)
    frame.pack()

    tk.Label(frame, text="Username").grid(row=0, column=0, pady=8)
    username = tk.Entry(frame)
    username.grid(row=0, column=1)

    tk.Label(frame, text="Password").grid(row=1, column=0, pady=8)
    password = tk.Entry(frame, show="*")
    password.grid(row=1, column=1)

    tk.Label(frame, text="Role").grid(row=2, column=0, pady=8)
    role = ttk.Combobox(frame, values=["Admin", "Staff"], state="readonly")
    role.set("Staff")
    role.grid(row=2, column=1)

    tree = ttk.Treeview(content_frame, columns=("Username", "Role"),
                        show="headings")
    tree.heading("Username", text="Username")
    tree.heading("Role", text="Role")
    tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh():
        tree.delete(*tree.get_children())
        cur.execute("SELECT username,role FROM users")
        for row in cur.fetchall():
            tree.insert("", "end", values=row)

    def add():
        if not username.get().strip() or not password.get():
            messagebox.showerror("Error", "Fill all fields")
            return

        try:
            cur.execute("INSERT INTO users VALUES(?,?,?)",
                        (username.get(), password.get(), role.get()))
            db.commit()
            refresh()
            clear_entries([username, password])
            messagebox.showinfo("Success", "Employee added")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Username already exists")

    def delete():
        selected = tree.selection()
        if not selected:
            return

        selected_user = tree.item(selected[0])["values"][0]

        if selected_user == current_user:
            messagebox.showerror("Error", "Cannot delete your own account")
            return

        if selected_user == "admin":
            messagebox.showerror("Error", "Default admin cannot be deleted")
            return

        if messagebox.askyesno("Confirm", "Delete employee?"):
            cur.execute("DELETE FROM users WHERE username=?", (selected_user,))
            db.commit()
            refresh()

    tk.Button(content_frame, text="Add Employee",
              command=add).pack(side="left", padx=160)
    tk.Button(content_frame, text="Delete Employee",
              command=delete).pack(side="left")

    refresh()


def billing_screen():
    clear_content()

    state = {"customer": "", "names": []}
    max_discount = 100 if current_role == "Admin" else STAFF_MAX_DISCOUNT

    body = tk.Frame(content_frame)
    body.pack(fill="both", expand=True, padx=10, pady=5)
    body.columnconfigure(0, weight=1, uniform="cols")
    body.columnconfigure(1, weight=1, uniform="cols")
    body.rowconfigure(1, weight=1)

    tk.Label(body, text="1. Customer and products",
             font=("Arial", 11)).grid(row=0, column=0, sticky="w", pady=(0, 3))
    tk.Label(body, text="2. Bill",
             font=("Arial", 11)).grid(row=0, column=1, sticky="w", pady=(0, 3))

    left = tk.LabelFrame(body)
    left.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
    right = tk.LabelFrame(body)
    right.grid(row=1, column=1, sticky="nsew", padx=(6, 0))

    cust_row = tk.Frame(left)
    cust_row.pack(fill="x", padx=10, pady=(12, 4))

    tk.Label(cust_row, text="Find customer:").pack(side="left")
    find_var = tk.StringVar()
    find_entry = tk.Entry(cust_row, textvariable=find_var)
    find_entry.pack(side="left", fill="x", expand=True, padx=8)
    new_cust_btn = tk.Button(cust_row, text="New customer", padx=6)
    new_cust_btn.pack(side="left")

    customer_box = ttk.Combobox(left, state="readonly")
    customer_box.pack(fill="x", padx=10, pady=(4, 10))

    search_row = tk.Frame(left)
    search_row.pack(fill="x", padx=10, pady=(0, 6))
    tk.Label(search_row, text="Search product:").pack(side="left")
    search_var = tk.StringVar()
    search_entry = tk.Entry(search_row, textvariable=search_var)
    search_entry.pack(side="left", fill="x", expand=True, padx=8)

    ptree_frame = tk.Frame(left)
    ptree_frame.pack(fill="both", expand=True, padx=10)

    ptree = ttk.Treeview(ptree_frame,
                         columns=("ID", "Product", "Price", "Stock"),
                         show="headings")
    widths = {"ID": 60, "Product": 220, "Price": 100, "Stock": 80}
    for col in ("ID", "Product", "Price", "Stock"):
        ptree.heading(col, text=col)
        ptree.column(col, width=widths[col],
                     anchor="center" if col == "ID" else "w")
    pscroll = ttk.Scrollbar(ptree_frame, orient="vertical", command=ptree.yview)
    ptree.configure(yscrollcommand=pscroll.set)
    ptree.pack(side="left", fill="both", expand=True)
    pscroll.pack(side="right", fill="y")

    add_row = tk.Frame(left)
    add_row.pack(fill="x", padx=10, pady=10)
    tk.Label(add_row, text="Qty:").pack(side="left")
    qty_spin = tk.Spinbox(add_row, from_=1, to=10000, width=6)
    qty_spin.pack(side="left", padx=(5, 10))
    add_btn = tk.Button(add_row, text="Add to cart", padx=8)
    add_btn.pack(side="left")

    ctree_frame = tk.Frame(right)
    ctree_frame.pack(fill="both", expand=True, padx=10, pady=(12, 6))

    ctree = ttk.Treeview(ctree_frame,
                         columns=("Product", "Price", "Qty", "Total"),
                         show="headings", height=10)
    cwidths = {"Product": 220, "Price": 100, "Qty": 60, "Total": 110}
    for col in ("Product", "Price", "Qty", "Total"):
        ctree.heading(col, text=col)
        ctree.column(col, width=cwidths[col],
                     anchor="w" if col == "Product" else "center")
    cscroll = ttk.Scrollbar(ctree_frame, orient="vertical", command=ctree.yview)
    ctree.configure(yscrollcommand=cscroll.set)
    ctree.pack(side="left", fill="both", expand=True)
    cscroll.pack(side="right", fill="y")

    cart_btns = tk.Frame(right)
    cart_btns.pack(fill="x", padx=10)
    remove_btn = tk.Button(cart_btns, text="Remove selected", padx=6)
    remove_btn.pack(side="left")
    clear_btn = tk.Button(cart_btns, text="Clear cart", padx=6)
    clear_btn.pack(side="left", padx=6)

    totals = tk.Frame(right)
    totals.pack(fill="x", padx=10, pady=10)

    subtotal_var = tk.StringVar(value="0.00")
    discount_var = tk.StringVar(value="0.00")
    tax_var = tk.StringVar(value="0.00")
    total_var = tk.StringVar(value="0.00")

    tk.Label(totals, text=f"Discount % (max {max_discount}):").grid(
        row=0, column=0, sticky="w")
    discount_entry = tk.Entry(totals, width=10)
    discount_entry.insert(0, "0")
    discount_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)

    tk.Label(totals, text="Subtotal:").grid(row=1, column=0, sticky="w")
    tk.Label(totals, textvariable=subtotal_var,
             font=("Arial", 11)).grid(row=1, column=1, sticky="w", padx=5)

    tk.Label(totals, text="Discount:").grid(row=2, column=0, sticky="w")
    tk.Label(totals, textvariable=discount_var,
             font=("Arial", 11)).grid(row=2, column=1, sticky="w", padx=5)

    tk.Label(totals, text=f"Tax ({TAX_RATE}%):").grid(row=3, column=0, sticky="w")
    tk.Label(totals, textvariable=tax_var,
             font=("Arial", 11)).grid(row=3, column=1, sticky="w", padx=5)

    tk.Label(totals, text="TOTAL:").grid(row=4, column=0, sticky="w")
    tk.Label(totals, textvariable=total_var,
             font=("Arial", 12, "bold")).grid(row=4, column=1, sticky="w", padx=5)

    tk.Label(totals, text="Payment method:").grid(row=5, column=0, sticky="w",
                                                  pady=(10, 2))
    payment = ttk.Combobox(totals, values=["Cash", "UPI", "Card"],
                           state="readonly", width=8)
    payment.set("Cash")
    payment.grid(row=5, column=1, sticky="w", padx=5, pady=(10, 2))

    generate_btn = tk.Button(right, text="Generate invoice", height=3)
    generate_btn.pack(fill="x", padx=10, pady=(0, 12))

    def load_customers(*_):
        term = find_var.get().strip()
        cur.execute("""SELECT name, phone FROM customers
                       WHERE name LIKE ? OR phone LIKE ? ORDER BY name""",
                    (f"%{term}%", f"%{term}%"))
        rows = cur.fetchall()
        state["names"] = [r[0] for r in rows]
        state["customer"] = ""
        customer_box.set("")
        customer_box["values"] = [f"{n}  ({p})" for n, p in rows]

    def on_customer_select(event=None):
        i = customer_box.current()
        if i >= 0:
            state["customer"] = state["names"][i]

    def load_products(*_):
        term = search_var.get().strip()
        ptree.delete(*ptree.get_children())
        cur.execute("""SELECT id, name, price, stock FROM products
                       WHERE name LIKE ? OR category LIKE ? ORDER BY name""",
                    (f"%{term}%", f"%{term}%"))
        for pid, pname, price, stock in cur.fetchall():
            ptree.insert("", "end", values=(pid, pname, f"{price:.2f}", stock))

    def calc_totals():
        """Returns (subtotal, discount_pct, discount_amt, tax_amt, total) or None."""
        sub = sum(item[3] for item in cart)
        try:
            d = float(discount_entry.get() or 0)
            if not 0 <= d <= max_discount:
                raise ValueError
        except ValueError:
            return None
        disc_amt = sub * d / 100
        taxable = sub - disc_amt
        tax_amt = taxable * TAX_RATE / 100
        return sub, d, disc_amt, tax_amt, taxable + tax_amt

    def update_totals(*_):
        result = calc_totals()
        if result is None:
            total_var.set("--")
            return
        sub, d, disc_amt, tax_amt, total = result
        subtotal_var.set(f"{sub:.2f}")
        discount_var.set(f"{disc_amt:.2f}")
        tax_var.set(f"{tax_amt:.2f}")
        total_var.set(f"{total:.2f}")

    def refresh_cart():
        ctree.delete(*ctree.get_children())
        for item in cart:
            ctree.insert("", "end", values=(item[0], f"{item[2]:.2f}",
                                            item[1], f"{item[3]:.2f}"))
        update_totals()

    def add_to_cart(*_):
        selected = ptree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a product from the list")
            return
        try:
            qty = int(qty_spin.get())
            if qty <= 0:
                raise ValueError("Enter a valid quantity")

            pid = ptree.item(selected[0])["values"][0]
            cur.execute("SELECT name, price, stock FROM products WHERE id=?",
                        (pid,))
            row = cur.fetchone()
            if not row:
                raise ValueError("Product not found")

            pname, price, stock = row
            already = sum(i[1] for i in cart if i[0] == pname)
            if qty + already > stock:
                raise ValueError(f"Not enough stock (available: {stock})")

            for item in cart:
                if item[0] == pname:
                    item[1] += qty
                    item[3] = item[1] * item[2]
                    break
            else:
                cart.append([pname, qty, price, qty * price])

            refresh_cart()
            qty_spin.delete(0, tk.END)
            qty_spin.insert(0, "1")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def remove_selected():
        selected = ctree.selection()
        if not selected:
            return
        del cart[ctree.index(selected[0])]
        refresh_cart()

    def clear_cart():
        if cart and messagebox.askyesno("Clear cart", "Remove all items?"):
            cart.clear()
            refresh_cart()

    def new_customer():
        win = tk.Toplevel(root)
        win.title("New customer")
        win.resizable(False, False)
        win.transient(root)
        win.grab_set()

        tk.Label(win, text="Name").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        n_entry = tk.Entry(win, width=28)
        n_entry.grid(row=0, column=1, padx=10)
        tk.Label(win, text="Phone").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        p_entry = tk.Entry(win, width=28)
        p_entry.grid(row=1, column=1, padx=10)
        n_entry.focus()

        def save():
            n, p = n_entry.get().strip(), p_entry.get().strip()
            if not n or not p:
                messagebox.showerror("Error", "Enter name and phone", parent=win)
                return
            cur.execute("INSERT INTO customers(name,phone) VALUES(?,?)", (n, p))
            db.commit()
            win.destroy()
            find_var.set(n)
            load_customers()
            if customer_box["values"]:
                customer_box.current(0)
                on_customer_select()

        tk.Button(win, text="Save", width=12, command=save).grid(
            row=2, column=0, columnspan=2, pady=10)

    def generate_invoice():
        if not cart:
            messagebox.showerror("Error", "Add products to the cart first")
            return

        result = calc_totals()
        if result is None:
            messagebox.showerror(
                "Error", f"Discount must be a number between 0 and {max_discount}")
            return
        sub, d, disc_amt, tax_amt, final = result

        method = payment.get()
        if not method:
            messagebox.showerror("Error", "Select a payment method")
            return

        for item in cart:
            cur.execute("SELECT stock FROM products WHERE name=?", (item[0],))
            row = cur.fetchone()
            if not row or row[0] < item[1]:
                messagebox.showerror("Error", "Insufficient stock: " + item[0])
                return

        customer_name = state["customer"] or "Walk-in Customer"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            db.execute("BEGIN")
            cur.execute("""INSERT INTO sales
                (customer,subtotal,discount,tax,total,payment,date,status,cashier)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                        (customer_name, sub, d, TAX_RATE, final, method, now,
                         "Completed", current_user))
            sale_id = cur.lastrowid

            for item in cart:
                cur.execute("""INSERT INTO sale_items
                    (sale_id,product,quantity,price,amount)
                    VALUES(?,?,?,?,?)""",
                            (sale_id, item[0], item[1], item[2], item[3]))
                cur.execute("UPDATE products SET stock=stock-? WHERE name=?",
                            (item[1], item[0]))
            db.commit()
        except Exception as e:
            db.rollback()
            messagebox.showerror("Database Error", str(e))
            return

        export_invoice(sale_id)
        messagebox.showinfo("Success", f"Bill #{sale_id} saved successfully")

        cart.clear()
        refresh_cart()
        load_products()
        find_var.set("")
        load_customers()
        discount_entry.delete(0, tk.END)
        discount_entry.insert(0, "0")
        update_totals()

    find_var.trace_add("write", load_customers)
    search_var.trace_add("write", load_products)
    customer_box.bind("<<ComboboxSelected>>", on_customer_select)
    new_cust_btn.config(command=new_customer)
    add_btn.config(command=add_to_cart)
    ptree.bind("<Double-1>", add_to_cart)
    remove_btn.config(command=remove_selected)
    clear_btn.config(command=clear_cart)
    discount_entry.bind("<KeyRelease>", update_totals)
    generate_btn.config(command=generate_invoice)

    load_customers()
    load_products()
    refresh_cart()


def history_screen():
    clear_content()
    is_admin = current_role == "Admin"

    tk.Label(content_frame,
             text="SALES TRANSACTION HISTORY" if is_admin else "MY TRANSACTIONS",
             font=("Arial", 18, "bold")).pack(pady=15)

    cols = ("ID", "Customer", "Subtotal", "Discount %", "Tax %", "Total",
            "Payment", "Date", "Status", "Cashier")
    tree = ttk.Treeview(content_frame, columns=cols, show="headings")
    for col in cols:
        tree.heading(col, text=col)
        tree.column(col, width=100)
    tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh():
        tree.delete(*tree.get_children())
        query = """SELECT id,customer,subtotal,discount,tax,total,payment,
                          date,status,cashier FROM sales"""
        if is_admin:
            cur.execute(query + " ORDER BY id DESC")
        else:
            cur.execute(query + " WHERE cashier=? ORDER BY id DESC",
                        (current_user,))
        for row in cur.fetchall():
            tree.insert("", "end", values=row)

    def view_invoice():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a transaction")
            return
        export_invoice(tree.item(selected[0])["values"][0])

    def cancel_sale():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a transaction")
            return

        sale_id = tree.item(selected[0])["values"][0]
        cur.execute("SELECT status FROM sales WHERE id=?", (sale_id,))
        status = cur.fetchone()

        if not status or status[0] != "Completed":
            messagebox.showwarning("Warning", "Transaction already cancelled")
            return

        if messagebox.askyesno("Confirm", "Cancel this transaction?"):
            try:
                db.execute("BEGIN")
                cur.execute("SELECT product,quantity FROM sale_items WHERE sale_id=?",
                            (sale_id,))
                for pname, qty in cur.fetchall():
                    cur.execute("UPDATE products SET stock=stock+? WHERE name=?",
                                (qty, pname))
                cur.execute("UPDATE sales SET status='Cancelled' WHERE id=?",
                            (sale_id,))
                db.commit()
                refresh()
                messagebox.showinfo("Success", "Transaction cancelled")
            except Exception as e:
                db.rollback()
                messagebox.showerror("Error", str(e))

    btns = tk.Frame(content_frame)
    btns.pack(pady=10)
    tk.Button(btns, text="View / Print Invoice",
              command=view_invoice, width=20).pack(side="left", padx=5)
    if is_admin:
        tk.Button(btns, text="Cancel Transaction",
                  command=cancel_sale, width=20).pack(side="left", padx=5)

    refresh()


def report_screen():
    clear_content()

    tk.Label(content_frame, text="SALES REPORTS",
             font=("Arial", 20, "bold")).pack(pady=20)

    result = tk.Label(content_frame, text="", font=("Arial", 14),
                      justify="left")
    result.pack(pady=20)

    def report(period):
        today = datetime.now().date()

        if period == "Daily":
            start = today
        elif period == "Weekly":
            start = today - timedelta(days=6)
        else:
            start = today.replace(day=1)

        cur.execute("""SELECT COUNT(*), COALESCE(SUM(total),0)
            FROM sales WHERE status='Completed' AND date(date)>=date(?)""",
                    (start.isoformat(),))

        count, total = cur.fetchone()

        result.config(text=f"""
        Report Type: {period}

        Start Date: {start}

        Number of Sales: {count}

        Total Revenue: Rs. {total:.2f}
        """)

    buttons = tk.Frame(content_frame)
    buttons.pack()

    for period in ("Daily", "Weekly", "Monthly"):
        tk.Button(buttons, text=period, width=15,
                  command=lambda p=period: report(p)).pack(side="left", padx=10)


def main_screen():
    global content_frame

    root.title("Billing Management System - Dashboard")

    tk.Label(root, text="BILLING MANAGEMENT SYSTEM",
             font=("Arial", 22, "bold")).pack(fill="x", pady=10)

    tk.Label(root, text=f"Welcome {current_user} ({current_role})",
             font=("Arial", 12)).pack()

    main_frame = tk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    menu_frame = tk.Frame(main_frame, bg="lightgray", width=220)
    menu_frame.pack(side="left", fill="y")

    content_frame = tk.Frame(main_frame)
    content_frame.pack(side="right", fill="both", expand=True)

    def make_btn(text, command):
        tk.Button(menu_frame, text=text, width=22, height=2,
                  command=command).pack(pady=5)

    make_btn("Create Bill", billing_screen)
    make_btn("Sales History", history_screen)

    if current_role == "Admin":
        make_btn("Product Management", product_screen)
        make_btn("Customer Management", customer_screen)
        make_btn("Employee Management", user_screen)
        make_btn("Sales Reports", report_screen)

    make_btn("Logout", logout)

    billing_screen()   

login_frame = tk.Frame(root)
login_frame.pack(expand=True)

tk.Label(login_frame, text="BILLING MANAGEMENT SYSTEM",
         font=("Arial", 25, "bold")).pack(pady=20)

tk.Label(login_frame, text="Username").pack()
user_entry = tk.Entry(login_frame, width=30, font=("Arial", 12))
user_entry.pack(pady=5)

tk.Label(login_frame, text="Password").pack()
pass_entry = tk.Entry(login_frame, width=30, show="*", font=("Arial", 12))
pass_entry.pack(pady=5)

tk.Button(login_frame, text="LOGIN", command=login,
          width=20, height=2).pack(pady=15)

tk.Label(login_frame,
         text="Admin Username: admin\nAdmin Password: admin123").pack(pady=10)

root.mainloop()
