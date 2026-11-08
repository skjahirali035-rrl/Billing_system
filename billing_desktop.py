#!/usr/bin/env python3
"""
Billing System - desktop application (Tkinter, standard library only).

Keep this file in the same folder as billing_system.py (it reuses its database
schema, invoice rendering and settings such as TAX_RATE).

Run:      python billing_desktop.py
Default:  admin / admin123   (change it in the Users tab)
Data:     ~/BillingSystem/billing.db  and  ~/BillingSystem/invoices/
"""
import os
import sqlite3
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import billing_system as core
from billing_system import D, money, q

DATA_DIR = Path.home() / "BillingSystem"
DATA_DIR.mkdir(exist_ok=True)
core.DB_FILE = str(DATA_DIR / "billing.db")
core.INVOICE_DIR = DATA_DIR / "invoices"


# ------------------------------------------------------------------ UI helpers
def make_tree(parent, cols, widths, height=12):
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=cols, show="headings", height=height, selectmode="browse")
    for c, w in zip(cols, widths):
        tree.heading(c, text=c)
        tree.column(c, width=w, anchor="w")
    sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, tree


def fill(tree, rows):
    """rows: iterable of (iid, values, tags)."""
    tree.delete(*tree.get_children())
    for iid, values, tags in rows:
        tree.insert("", "end", iid=str(iid), values=values, tags=tags)


def selected(tree, warn=True):
    sel = tree.selection()
    if not sel and warn:
        messagebox.showwarning("Select a row", "Please select a row first.")
    return sel[0] if sel else None


def form_dialog(root, title, fields, initial=None):
    """fields: (key, label[, 'password' | list_of_choices]). Returns dict or None."""
    win = tk.Toplevel(root)
    win.title(title)
    win.transient(root)
    win.grab_set()
    win.resizable(False, False)
    vars_ = {}
    for i, (key, label, *kind) in enumerate(fields):
        ttk.Label(win, text=label).grid(row=i, column=0, sticky="e", padx=8, pady=4)
        v = tk.StringVar(value=str((initial or {}).get(key) or ""))
        vars_[key] = v
        if kind and kind[0] == "password":
            w = ttk.Entry(win, textvariable=v, show="*", width=28)
        elif kind and isinstance(kind[0], list):
            w = ttk.Combobox(win, textvariable=v, values=kind[0], state="readonly", width=26)
        else:
            w = ttk.Entry(win, textvariable=v, width=28)
        w.grid(row=i, column=1, padx=8, pady=4)
    result = {}

    def ok(*_):
        result.update({k: v.get().strip() for k, v in vars_.items()})
        win.destroy()

    bar = ttk.Frame(win)
    bar.grid(row=len(fields), column=0, columnspan=2, pady=8)
    ttk.Button(bar, text="OK", command=ok).pack(side="left", padx=6)
    ttk.Button(bar, text="Cancel", command=win.destroy).pack(side="left", padx=6)
    win.bind("<Return>", ok)
    root.wait_window(win)
    return result or None


def print_file(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path), "print")  # type: ignore[attr-defined]
        else:
            subprocess.run(["lp", str(path)], check=True)
    except Exception as e:
        messagebox.showinfo("Print", f"Couldn't send to a printer ({e}).\nInvoice file: {path}")


# ------------------------------------------------------------------ main app
class App:
    def __init__(self, root, user, on_logout):
        self.root, self.user, self.on_logout = root, user, on_logout
        self.is_admin = user["role"] == "admin"
        self.refreshers = []
        self.cart = {}  # product_id -> [name, price(Decimal), qty]
        root.title("Billing System")
        root.geometry("1150x700")
        top = ttk.Frame(root)
        top.pack(fill="x", padx=8, pady=4)
        ttk.Label(top, text=f"Logged in as {user['username']} ({user['role']})").pack(side="left")
        ttk.Button(top, text="Logout", command=on_logout).pack(side="right")
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        self.build_billing()
        self.build_products()
        if self.is_admin:
            self.build_categories()
            self.build_customers()
            self.build_users()
        self.build_transactions()
        if self.is_admin:
            self.build_reports()
        self.refresh_all()

    def refresh_all(self):
        for fn in self.refreshers:
            fn()

    # ---------------------------------------------------------- billing tab
    def build_billing(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Billing")
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)
        f.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(f, text="1. Customer and products", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Label(left, text="Find customer:").grid(row=0, column=0, sticky="w")
        self.c_search = tk.StringVar()
        e = ttk.Entry(left, textvariable=self.c_search)
        e.grid(row=0, column=1, sticky="ew", padx=4)
        e.bind("<KeyRelease>", lambda _e: self.refresh_customer_box())
        ttk.Button(left, text="New customer", command=self.new_customer).grid(row=0, column=2)
        self.cust_var = tk.StringVar()
        self.cust_box = ttk.Combobox(left, textvariable=self.cust_var, state="readonly")
        self.cust_box.grid(row=1, column=0, columnspan=3, sticky="ew", pady=4)

        ttk.Label(left, text="Search product:").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.bp_search = tk.StringVar()
        e = ttk.Entry(left, textvariable=self.bp_search)
        e.grid(row=2, column=1, columnspan=2, sticky="ew", padx=4, pady=(10, 0))
        e.bind("<KeyRelease>", lambda _e: self.refresh_billing_products())
        tf, self.bp_tree = make_tree(left, ("ID", "Product", "Price", "Stock"), (45, 220, 80, 60), 14)
        tf.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=4)
        self.bp_tree.tag_configure("low", foreground="#c0392b")
        self.bp_tree.bind("<Double-1>", lambda _e: self.add_to_cart())
        bar = ttk.Frame(left)
        bar.grid(row=4, column=0, columnspan=3, sticky="w")
        ttk.Label(bar, text="Qty:").pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        ttk.Spinbox(bar, from_=1, to=9999, textvariable=self.qty_var, width=6).pack(side="left", padx=4)
        ttk.Button(bar, text="Add to cart", command=self.add_to_cart).pack(side="left", padx=4)
        left.columnconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)

        right = ttk.LabelFrame(f, text="2. Bill", padding=8)
        right.grid(row=0, column=1, sticky="nsew")
        tf, self.cart_tree = make_tree(right, ("Product", "Price", "Qty", "Total"), (200, 80, 60, 90), 10)
        tf.pack(fill="both", expand=True)
        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=4)
        ttk.Button(bar, text="Remove selected", command=self.remove_from_cart).pack(side="left")
        ttk.Button(bar, text="Clear cart", command=self.clear_cart).pack(side="left", padx=6)

        grid = ttk.Frame(right)
        grid.pack(fill="x", pady=6)
        limit = "100" if self.is_admin else str(core.STAFF_MAX_DISCOUNT)
        ttk.Label(grid, text=f"Discount % (max {limit}):").grid(row=0, column=0, sticky="w")
        self.disc_var = tk.StringVar(value="0")
        self.disc_var.trace_add("write", lambda *_: self.update_totals())
        ttk.Entry(grid, textvariable=self.disc_var, width=8).grid(row=0, column=1, sticky="w", padx=6)
        self.lbl = {}
        for i, (key, text) in enumerate([("sub", "Subtotal"), ("disc", "Discount"),
                                         ("tax", f"Tax ({core.TAX_RATE}%)"), ("total", "TOTAL")], 1):
            ttk.Label(grid, text=text + ":").grid(row=i, column=0, sticky="w")
            self.lbl[key] = ttk.Label(grid, text="0.00", font=("TkDefaultFont", 11, "bold" if key == "total" else "normal"))
            self.lbl[key].grid(row=i, column=1, sticky="w", padx=6)
        ttk.Label(grid, text="Payment method:").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.pay_var = tk.StringVar(value=core.PAYMENT_METHODS[0])
        ttk.Combobox(grid, textvariable=self.pay_var, values=core.PAYMENT_METHODS, state="readonly",
                     width=10).grid(row=5, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(grid, text="Cash received:").grid(row=6, column=0, sticky="w")
        self.cash_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.cash_var, width=10).grid(row=6, column=1, sticky="w", padx=6)
        ttk.Button(right, text="Generate invoice", command=self.generate_invoice).pack(fill="x", ipady=6, pady=4)

        self.refreshers += [self.refresh_customer_box, self.refresh_billing_products]

    def refresh_customer_box(self):
        term = f"%{self.c_search.get().strip()}%"
        rows = q("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name", (term, term))
        vals = [f"{r['id']}: {r['name']} {r['phone'] or ''}".strip() for r in rows]
        self.cust_box["values"] = vals
        if len(vals) == 1 or (vals and self.cust_var.get() not in vals):
            self.cust_var.set(vals[0] if len(vals) == 1 else "")
        elif not vals:
            self.cust_var.set("")

    def new_customer(self):
        d = form_dialog(self.root, "New customer", [("name", "Name"), ("phone", "Phone"),
                                                     ("email", "Email"), ("address", "Address")])
        if not d or not d["name"]:
            return
        cur = core.db.execute("INSERT INTO customers(name,phone,email,address) VALUES(?,?,?,?)",
                              (d["name"], d["phone"], d["email"], d["address"]))
        core.db.commit()
        self.c_search.set("")
        self.refresh_all()
        for v in self.cust_box["values"]:
            if v.startswith(f"{cur.lastrowid}:"):
                self.cust_var.set(v)

    def refresh_billing_products(self):
        term = f"%{self.bp_search.get().strip()}%"
        rows = q("SELECT id,name,price,stock FROM products WHERE name LIKE ? ORDER BY name", (term,))
        fill(self.bp_tree, [(r["id"], (r["id"], r["name"], f"{r['price']:.2f}", r["stock"]),
                             ("low",) if r["stock"] <= core.LOW_STOCK else ()) for r in rows])

    def add_to_cart(self):
        pid = selected(self.bp_tree)
        if pid is None:
            return
        try:
            qty = int(self.qty_var.get())
            assert qty > 0
        except (ValueError, AssertionError):
            messagebox.showerror("Quantity", "Enter a whole number greater than 0.")
            return
        p = q("SELECT * FROM products WHERE id=?", (pid,))[0]
        already = self.cart.get(int(pid), [0, 0, 0])[2]
        if qty + already > p["stock"]:
            messagebox.showwarning("Stock", f"Only {p['stock'] - already} more of '{p['name']}' available.")
            return
        self.cart[int(pid)] = [p["name"], D(p["price"]), already + qty]
        self.redraw_cart()

    def remove_from_cart(self):
        pid = selected(self.cart_tree)
        if pid is not None:
            self.cart.pop(int(pid), None)
            self.redraw_cart()

    def clear_cart(self):
        self.cart.clear()
        self.redraw_cart()

    def redraw_cart(self):
        fill(self.cart_tree, [(pid, (n, f"{p:.2f}", qty, f"{money(p * qty):.2f}"), ())
                              for pid, (n, p, qty) in self.cart.items()])
        self.update_totals()

    def totals(self):
        sub = sum((p * n for _, p, n in self.cart.values()), Decimal(0))
        try:
            pct = D(self.disc_var.get().strip() or 0)
        except Exception:
            return None
        if pct < 0 or pct > 100:
            return None
        disc = money(sub * pct / 100)
        tax = money((sub - disc) * core.TAX_RATE / 100)
        return money(sub), pct, disc, tax, money(sub - disc + tax)

    def update_totals(self):
        t = self.totals()
        for key, val in zip(("sub", "disc", "tax", "total"), (t[0], t[2], t[3], t[4]) if t else ("-",) * 4):
            self.lbl[key].config(text=str(val))

    def generate_invoice(self):
        m = self.cust_var.get()
        if not m:
            return messagebox.showwarning("Customer", "Select or create a customer first.")
        cid = int(m.split(":")[0])
        if not self.cart:
            return messagebox.showwarning("Cart", "The cart is empty.")
        t = self.totals()
        if t is None:
            return messagebox.showerror("Discount", "Enter a valid discount between 0 and 100.")
        sub, pct, disc, tax, total = t
        limit = Decimal(100) if self.is_admin else core.STAFF_MAX_DISCOUNT
        if pct > limit:
            return messagebox.showerror("Discount", f"You are only authorised to give up to {limit}% discount.")
        method, change = self.pay_var.get(), None
        if method == "Cash":
            try:
                paid = D(self.cash_var.get().strip() or total)
            except Exception:
                return messagebox.showerror("Cash", "Enter a valid cash amount.")
            if paid < total:
                return messagebox.showerror("Cash", "Cash received is less than the total.")
            change = money(paid - total)
        try:
            cur = core.db.execute(
                "INSERT INTO invoices(customer_id,created_by,created_at,subtotal,discount_pct,discount_amt,"
                "tax_pct,tax_amt,total,payment_method) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (cid, self.user["id"], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), float(sub), float(pct),
                 float(disc), float(core.TAX_RATE), float(tax), float(total), method))
            inv_id = cur.lastrowid
            core.db.execute("UPDATE invoices SET number=? WHERE id=?", (f"INV-{inv_id:05d}", inv_id))
            for pid, (name, price, qty) in self.cart.items():
                upd = core.db.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?", (qty, pid, qty))
                if upd.rowcount == 0:
                    raise RuntimeError(f"Insufficient stock for {name}")
                core.db.execute("INSERT INTO invoice_items(invoice_id,product_id,name,unit_price,qty,line_total)"
                                " VALUES(?,?,?,?,?,?)", (inv_id, pid, name, float(price), qty, float(money(price * qty))))
            core.db.commit()
        except Exception as e:
            core.db.rollback()
            return messagebox.showerror("Billing failed", f"Nothing was saved.\n\n{e}")
        path = core.write_invoice(inv_id)
        self.cart.clear()
        self.redraw_cart()
        self.cash_var.set("")
        self.disc_var.set("0")
        self.refresh_all()
        if change is not None:
            messagebox.showinfo("Cash payment", f"Change to return: {change}")
        self.show_invoice(inv_id, path)

    def show_invoice(self, inv_id, path):
        win = tk.Toplevel(self.root)
        win.title("Invoice")
        txt = tk.Text(win, font=("Courier", 10), width=66, height=28)
        txt.insert("1.0", core.render_invoice(inv_id))
        txt.config(state="disabled")
        txt.pack(padx=8, pady=8)
        bar = ttk.Frame(win)
        bar.pack(pady=(0, 8))

        def save_copy():
            dest = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=Path(path).name)
            if dest:
                Path(dest).write_text(core.render_invoice(inv_id))

        ttk.Button(bar, text="Print", command=lambda: print_file(path)).pack(side="left", padx=6)
        ttk.Button(bar, text="Save a copy...", command=save_copy).pack(side="left", padx=6)
        ttk.Button(bar, text="Close", command=win.destroy).pack(side="left", padx=6)

    # ---------------------------------------------------------- products tab
    def cat_values(self):
        return [""] + [f"{r['id']}: {r['name']}" for r in q("SELECT * FROM categories ORDER BY name")]

    def build_products(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Products & Inventory")
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.p_search, self.p_low = tk.StringVar(), tk.BooleanVar()
        ttk.Label(top, text="Search:").pack(side="left")
        e = ttk.Entry(top, textvariable=self.p_search, width=30)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda _e: self.refresh_products())
        ttk.Checkbutton(top, text="Low stock only", variable=self.p_low,
                        command=self.refresh_products).pack(side="left", padx=10)
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, pady=6)
        tf, self.p_tree = make_tree(body, ("ID", "Product", "Category", "Price", "Stock"), (50, 260, 140, 90, 70), 18)
        tf.pack(side="left", fill="both", expand=True)
        self.p_tree.tag_configure("low", foreground="#c0392b")
        self.p_cat_box = None
        if self.is_admin:
            form = ttk.LabelFrame(body, text="Product details", padding=8)
            form.pack(side="left", fill="y", padx=(8, 0))
            self.p_name, self.p_cat, self.p_price, self.p_stock = (tk.StringVar() for _ in range(4))
            for i, (label, var) in enumerate([("Name", self.p_name), ("Category", self.p_cat),
                                              ("Price", self.p_price), ("Stock", self.p_stock)]):
                ttk.Label(form, text=label).grid(row=i, column=0, sticky="e", pady=3)
                if label == "Category":
                    self.p_cat_box = ttk.Combobox(form, textvariable=var, state="readonly", width=22)
                    self.p_cat_box.grid(row=i, column=1, padx=6)
                else:
                    ttk.Entry(form, textvariable=var, width=24).grid(row=i, column=1, padx=6)
            for text, cmd in [("Add as new", lambda: self.save_product(False)),
                              ("Update selected", lambda: self.save_product(True)),
                              ("Add stock (+)", self.add_stock), ("Delete selected", self.delete_product),
                              ("Clear form", self.clear_product_form)]:
                ttk.Button(form, text=text, command=cmd).grid(
                    columnspan=2, sticky="ew", pady=2, padx=6)
            self.p_tree.bind("<<TreeviewSelect>>", self.load_product)
        self.refreshers.append(self.refresh_products)

    def refresh_products(self):
        term = f"%{self.p_search.get().strip()}%"
        sql = ("SELECT p.id,p.name,COALESCE(c.name,'-') cat,p.price,p.stock FROM products p "
               "LEFT JOIN categories c ON c.id=p.category_id WHERE (p.name LIKE ? OR cat LIKE ?)")
        args = [term, term]
        if self.p_low.get():
            sql += " AND p.stock<=?"
            args.append(core.LOW_STOCK)
        rows = q(sql + " ORDER BY p.name", args)
        fill(self.p_tree, [(r["id"], (r["id"], r["name"], r["cat"], f"{r['price']:.2f}", r["stock"]),
                            ("low",) if r["stock"] <= core.LOW_STOCK else ()) for r in rows])
        if self.p_cat_box is not None:
            self.p_cat_box["values"] = self.cat_values()

    def clear_product_form(self):
        for v in (self.p_name, self.p_cat, self.p_price, self.p_stock):
            v.set("")

    def load_product(self, _e=None):
        pid = selected(self.p_tree, warn=False)
        if pid is None:
            return
        p = q("SELECT * FROM products WHERE id=?", (pid,))[0]
        self.p_name.set(p["name"])
        self.p_price.set(f"{p['price']:.2f}")
        self.p_stock.set(p["stock"])
        self.p_cat.set(next((v for v in self.cat_values() if v.startswith(f"{p['category_id']}:")), ""))

    def save_product(self, update):
        try:
            name = self.p_name.get().strip()
            price, stock = float(D(self.p_price.get())), int(self.p_stock.get() or 0)
            assert name
        except Exception:
            return messagebox.showerror("Product", "Enter a name, a valid price and a whole-number stock.")
        cat = self.p_cat.get().split(":")[0].strip()
        cid = int(cat) if cat.isdigit() else None
        try:
            if update:
                pid = selected(self.p_tree)
                if pid is None:
                    return
                core.db.execute("UPDATE products SET name=?,category_id=?,price=?,stock=? WHERE id=?",
                                (name, cid, price, stock, pid))
            else:
                core.db.execute("INSERT INTO products(name,category_id,price,stock) VALUES(?,?,?,?)",
                                (name, cid, price, stock))
            core.db.commit()
        except sqlite3.Error as e:
            core.db.rollback()
            return messagebox.showerror("Product", f"Could not save: {e}")
        self.refresh_all()

    def add_stock(self):
        pid = selected(self.p_tree)
        if pid is None:
            return
        n = simpledialog.askinteger("Add stock", "Quantity to add:", parent=self.root, minvalue=1)
        if n:
            core.db.execute("UPDATE products SET stock=stock+? WHERE id=?", (n, pid))
            core.db.commit()
            self.refresh_all()

    def delete_product(self):
        pid = selected(self.p_tree)
        if pid is None or not messagebox.askyesno("Delete", "Delete this product?"):
            return
        try:
            core.db.execute("DELETE FROM products WHERE id=?", (pid,))
            core.db.commit()
        except sqlite3.IntegrityError:
            return messagebox.showinfo("In use", "This product appears on invoices. Set its stock to 0 instead.")
        self.refresh_all()

    # ---------------------------------------------------------- categories
    def build_categories(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Categories")
        tf, self.cat_tree = make_tree(f, ("ID", "Name"), (60, 300), 18)
        tf.pack(side="left", fill="both", expand=True)
        bar = ttk.Frame(f)
        bar.pack(side="left", fill="y", padx=8)
        for text, cmd in [("Add", self.add_category), ("Rename", self.rename_category),
                          ("Delete", self.delete_category)]:
            ttk.Button(bar, text=text, command=cmd).pack(fill="x", pady=2)
        self.refreshers.append(lambda: fill(self.cat_tree, [
            (r["id"], (r["id"], r["name"]), ()) for r in q("SELECT * FROM categories ORDER BY name")]))

    def add_category(self):
        name = simpledialog.askstring("Category", "Category name:", parent=self.root)
        if name and name.strip():
            try:
                core.db.execute("INSERT INTO categories(name) VALUES(?)", (name.strip(),))
                core.db.commit()
            except sqlite3.IntegrityError:
                messagebox.showinfo("Category", "That category already exists.")
            self.refresh_all()

    def rename_category(self):
        cid = selected(self.cat_tree)
        name = cid and simpledialog.askstring("Rename", "New name:", parent=self.root)
        if name and name.strip():
            try:
                core.db.execute("UPDATE categories SET name=? WHERE id=?", (name.strip(), cid))
                core.db.commit()
            except sqlite3.IntegrityError:
                messagebox.showinfo("Category", "That name is already used.")
            self.refresh_all()

    def delete_category(self):
        cid = selected(self.cat_tree)
        if cid is None:
            return
        if q("SELECT 1 FROM products WHERE category_id=?", (cid,)):
            return messagebox.showinfo("Category", "This category still has products.")
        core.db.execute("DELETE FROM categories WHERE id=?", (cid,))
        core.db.commit()
        self.refresh_all()

    # ---------------------------------------------------------- customers
    CUST_FIELDS = [("name", "Name"), ("phone", "Phone"), ("email", "Email"), ("address", "Address")]

    def build_customers(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Customers")
        top = ttk.Frame(f)
        top.pack(fill="x")
        self.cm_search = tk.StringVar()
        ttk.Label(top, text="Search:").pack(side="left")
        e = ttk.Entry(top, textvariable=self.cm_search, width=30)
        e.pack(side="left", padx=4)
        e.bind("<KeyRelease>", lambda _e: self.refresh_customers())
        for text, cmd in [("Add", self.add_customer), ("Edit", self.edit_customer), ("Delete", self.delete_customer)]:
            ttk.Button(top, text=text, command=cmd).pack(side="left", padx=3)
        tf, self.cm_tree = make_tree(f, ("ID", "Name", "Phone", "Email", "Address"), (50, 200, 120, 200, 300), 20)
        tf.pack(fill="both", expand=True, pady=6)
        self.refreshers.append(self.refresh_customers)

    def refresh_customers(self):
        term = f"%{self.cm_search.get().strip()}%"
        rows = q("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name", (term, term))
        fill(self.cm_tree, [(r["id"], (r["id"], r["name"], r["phone"] or "", r["email"] or "", r["address"] or ""), ())
                            for r in rows])

    def add_customer(self):
        self.new_customer()

    def edit_customer(self):
        cid = selected(self.cm_tree)
        if cid is None:
            return
        row = dict(q("SELECT * FROM customers WHERE id=?", (cid,))[0])
        d = form_dialog(self.root, "Edit customer", self.CUST_FIELDS, row)
        if d and d["name"]:
            core.db.execute("UPDATE customers SET name=?,phone=?,email=?,address=? WHERE id=?",
                            (d["name"], d["phone"], d["email"], d["address"], cid))
            core.db.commit()
            self.refresh_all()

    def delete_customer(self):
        cid = selected(self.cm_tree)
        if cid is None or not messagebox.askyesno("Delete", "Delete this customer?"):
            return
        try:
            core.db.execute("DELETE FROM customers WHERE id=?", (cid,))
            core.db.commit()
        except sqlite3.IntegrityError:
            messagebox.showinfo("In use", "This customer has invoices and can't be deleted.")
        self.refresh_all()

    # ---------------------------------------------------------- users
    def build_users(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Users")
        tf, self.u_tree = make_tree(f, ("ID", "Username", "Role", "Active"), (60, 220, 100, 80), 18)
        tf.pack(side="left", fill="both", expand=True)
        bar = ttk.Frame(f)
        bar.pack(side="left", fill="y", padx=8)
        for text, cmd in [("Add user", self.add_user), ("Activate / deactivate", self.toggle_user),
                          ("Reset password", self.reset_password)]:
            ttk.Button(bar, text=text, command=cmd).pack(fill="x", pady=2)
        self.refreshers.append(lambda: fill(self.u_tree, [
            (r["id"], (r["id"], r["username"], r["role"], "yes" if r["active"] else "no"), ())
            for r in q("SELECT * FROM users ORDER BY id")]))

    def add_user(self):
        d = form_dialog(self.root, "New user", [("username", "Username"), ("password", "Password", "password"),
                                                 ("role", "Role", ["staff", "admin"])], {"role": "staff"})
        if not d or not d["username"] or not d["password"]:
            return
        try:
            core.add_user(d["username"], d["password"], d["role"] or "staff")
            core.db.commit()
        except sqlite3.IntegrityError:
            messagebox.showinfo("User", "That username already exists.")
        self.refresh_all()

    def toggle_user(self):
        uid = selected(self.u_tree)
        if uid is None:
            return
        if int(uid) == self.user["id"]:
            return messagebox.showinfo("User", "You can't deactivate your own account.")
        core.db.execute("UPDATE users SET active=1-active WHERE id=?", (uid,))
        core.db.commit()
        self.refresh_all()

    def reset_password(self):
        uid = selected(self.u_tree)
        pw = uid and simpledialog.askstring("Password", "New password:", show="*", parent=self.root)
        if pw:
            salt = core.secrets.token_hex(16)
            core.db.execute("UPDATE users SET salt=?,pw_hash=? WHERE id=?", (salt, core.hash_pw(pw, salt), uid))
            core.db.commit()
            messagebox.showinfo("Password", "Password updated.")

    # ---------------------------------------------------------- transactions
    def build_transactions(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Transactions")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Button(bar, text="View / print invoice", command=self.open_invoice).pack(side="left", padx=3)
        if self.is_admin:
            ttk.Button(bar, text="Cancel transaction", command=self.cancel_tx).pack(side="left", padx=3)
            ttk.Button(bar, text="Change payment method", command=self.change_payment).pack(side="left", padx=3)
        tf, self.t_tree = make_tree(f, ("Invoice", "Date", "Customer", "Total", "Payment", "Status"),
                                    (100, 160, 220, 100, 100, 100), 22)
        tf.pack(fill="both", expand=True, pady=6)
        self.t_tree.tag_configure("cancelled", foreground="#888888")
        self.refreshers.append(self.refresh_transactions)

    def refresh_transactions(self):
        sql = ("SELECT i.id,i.number,i.created_at,c.name cname,i.total,i.payment_method,i.status FROM invoices i "
               "JOIN customers c ON c.id=i.customer_id")
        args = []
        if not self.is_admin:  # staff only see their own history
            sql += " WHERE i.created_by=?"
            args.append(self.user["id"])
        rows = q(sql + " ORDER BY i.id DESC LIMIT 300", args)
        fill(self.t_tree, [(r["id"], (r["number"], r["created_at"], r["cname"], f"{r['total']:.2f}",
                                      r["payment_method"], r["status"]),
                            ("cancelled",) if r["status"] != "PAID" else ()) for r in rows])

    def open_invoice(self):
        iid = selected(self.t_tree)
        if iid is not None:
            self.show_invoice(int(iid), core.write_invoice(int(iid)))

    def cancel_tx(self):
        iid = selected(self.t_tree)
        if iid is None:
            return
        inv = q("SELECT * FROM invoices WHERE id=? AND status='PAID'", (iid,))
        if not inv:
            return messagebox.showinfo("Cancel", "This invoice is already cancelled.")
        if not messagebox.askyesno("Cancel", f"Cancel {inv[0]['number']} and return items to stock?"):
            return
        for it in q("SELECT * FROM invoice_items WHERE invoice_id=?", (iid,)):
            core.db.execute("UPDATE products SET stock=stock+? WHERE id=?", (it["qty"], it["product_id"]))
        core.db.execute("UPDATE invoices SET status='CANCELLED' WHERE id=?", (iid,))
        core.db.commit()
        core.write_invoice(int(iid))
        self.refresh_all()

    def change_payment(self):
        iid = selected(self.t_tree)
        if iid is None:
            return
        d = form_dialog(self.root, "Payment method", [("m", "Method", core.PAYMENT_METHODS)])
        if d and d["m"]:
            core.db.execute("UPDATE invoices SET payment_method=? WHERE id=? AND status='PAID'", (d["m"], iid))
            core.db.commit()
            self.refresh_all()

    # ---------------------------------------------------------- reports
    def build_reports(self):
        f = ttk.Frame(self.nb, padding=8)
        self.nb.add(f, text="Reports")
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        self.r_period = tk.StringVar(value="Daily (today)")
        ttk.Combobox(bar, textvariable=self.r_period, state="readonly", width=24,
                     values=["Daily (today)", "Weekly (last 7 days)", "Monthly (last 30 days)"]).pack(side="left")
        ttk.Button(bar, text="Show report", command=self.show_report).pack(side="left", padx=6)
        self.r_text = tk.Text(f, font=("Courier", 10), state="disabled")
        self.r_text.pack(fill="both", expand=True, pady=6)
        self.refreshers.append(self.show_report)

    def show_report(self):
        days = {"Daily": 0, "Weekly": 6, "Monthly": 29}[self.r_period.get().split()[0]]
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
        s = q("SELECT COUNT(*) n, COALESCE(SUM(subtotal),0) sub, COALESCE(SUM(discount_amt),0) disc, "
              "COALESCE(SUM(tax_amt),0) tax, COALESCE(SUM(total),0) tot FROM invoices "
              "WHERE status='PAID' AND created_at>=?", (start,))[0]
        lines = [f"{self.r_period.get()}  (since {start[:10]})", "",
                 f"Invoices : {s['n']}", f"Subtotal : {s['sub']:.2f}", f"Discounts: {s['disc']:.2f}",
                 f"Tax      : {s['tax']:.2f}", f"REVENUE  : {s['tot']:.2f}", "", "Top products:"]
        for r in q("SELECT it.name, SUM(it.qty) qty, SUM(it.line_total) amt FROM invoice_items it "
                   "JOIN invoices i ON i.id=it.invoice_id WHERE i.status='PAID' AND i.created_at>=? "
                   "GROUP BY it.name ORDER BY qty DESC LIMIT 10", (start,)):
            lines.append(f"  {r['name'][:30]:<30} qty {r['qty']:<6} {r['amt']:>10.2f}")
        lines += ["", "By payment method:"]
        for r in q("SELECT payment_method, COUNT(*) n, SUM(total) t FROM invoices WHERE status='PAID' "
                   "AND created_at>=? GROUP BY payment_method", (start,)):
            lines.append(f"  {r['payment_method']:<8} {r['n']:>4} invoices {r['t']:>12.2f}")
        low = q("SELECT name, stock FROM products WHERE stock<=? ORDER BY stock", (core.LOW_STOCK,))
        lines += ["", f"Low stock (<= {core.LOW_STOCK}):"] + [f"  {r['name'][:30]:<30} {r['stock']}" for r in low]
        self.r_text.config(state="normal")
        self.r_text.delete("1.0", "end")
        self.r_text.insert("1.0", "\n".join(lines))
        self.r_text.config(state="disabled")


# ------------------------------------------------------------------ login
def clear(root):
    for w in root.winfo_children():
        w.destroy()


def show_login(root):
    clear(root)
    root.title("Billing System - Login")
    root.geometry("340x210")
    f = ttk.Frame(root, padding=20)
    f.pack(fill="both", expand=True)
    ttk.Label(f, text="Billing System", font=("TkDefaultFont", 15, "bold")).grid(columnspan=2, pady=(0, 12))
    u, p = tk.StringVar(), tk.StringVar()
    ttk.Label(f, text="Username").grid(row=1, column=0, sticky="e", pady=4)
    ue = ttk.Entry(f, textvariable=u)
    ue.grid(row=1, column=1, padx=6)
    ttk.Label(f, text="Password").grid(row=2, column=0, sticky="e", pady=4)
    ttk.Entry(f, textvariable=p, show="*").grid(row=2, column=1, padx=6)
    ue.focus()

    def attempt(*_):
        rows = q("SELECT * FROM users WHERE username=? AND active=1", (u.get().strip(),))
        if rows and core.secrets.compare_digest(rows[0]["pw_hash"], core.hash_pw(p.get(), rows[0]["salt"])):
            user = rows[0]
            clear(root)
            root.unbind("<Return>")
            App(root, user, lambda: show_login(root))
            if user["username"] == "admin" and core.hash_pw("admin123", user["salt"]) == user["pw_hash"]:
                messagebox.showwarning("Change password", "You are using the default admin password.\n"
                                       "Change it in the Users tab.")
        else:
            messagebox.showerror("Login", "Invalid username or password.")

    ttk.Button(f, text="Login", command=attempt).grid(row=3, columnspan=2, pady=14, ipadx=20)
    root.bind("<Return>", attempt)


def main():
    core.init_db()
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    show_login(root)
    root.mainloop()


if __name__ == "__main__":
    main()
