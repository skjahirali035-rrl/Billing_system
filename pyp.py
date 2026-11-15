
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime, timedelta


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

cur.execute("SELECT * FROM users WHERE username='admin'")
if not cur.fetchone():
    cur.execute("INSERT INTO users VALUES(?,?,?)",
                ("admin", "admin123", "Admin"))

db.commit()

cart = []
current_user = ""
current_role = ""


root = tk.Tk()
root.title("Billing Management System")
root.geometry("1100x700")
root.configure(bg="#eaf0f6")


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



def product_screen():
    win = tk.Toplevel(root)
    win.title("Product Management")
    win.geometry("800x550")

    tk.Label(win, text="PRODUCT MANAGEMENT",
             font=("Arial", 18, "bold")).pack(pady=10)

    frame = tk.Frame(win)
    frame.pack(pady=10)

    labels = ["Product Name", "Category", "Price", "Stock"]
    entries = []

    for i, label in enumerate(labels):
        tk.Label(frame, text=label).grid(row=i, column=0, padx=10, pady=7)
        e = tk.Entry(frame, width=30)
        e.grid(row=i, column=1, padx=10, pady=7)
        entries.append(e)

    name, category, price, stock = entries

    tree = ttk.Treeview(win,
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

    buttons = tk.Frame(win)
    buttons.pack(pady=10)

    tk.Button(buttons, text="Add Product",
              command=add_product, width=15).pack(side="left", padx=5)
    tk.Button(buttons, text="Update",
              command=update_product, width=15).pack(side="left", padx=5)
    tk.Button(buttons, text="Delete",
              command=delete_product, width=15).pack(side="left", padx=5)

    refresh()



def customer_screen():
    win = tk.Toplevel(root)
    win.title("Customer Management")
    win.geometry("700x500")

    tk.Label(win, text="CUSTOMER MANAGEMENT",
             font=("Arial", 18, "bold")).pack(pady=15)

    frame = tk.Frame(win)
    frame.pack()

    tk.Label(frame, text="Customer Name").grid(row=0, column=0, padx=10, pady=10)
    name = tk.Entry(frame, width=30)
    name.grid(row=0, column=1)

    tk.Label(frame, text="Phone Number").grid(row=1, column=0, padx=10, pady=10)
    phone = tk.Entry(frame, width=30)
    phone.grid(row=1, column=1)

    tree = ttk.Treeview(win, columns=("ID", "Name", "Phone"),
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

    tk.Button(win, text="Add Customer", command=add).pack(side="left", padx=150)
    tk.Button(win, text="Delete Customer", command=delete).pack(side="left")

    refresh()



def user_screen():
    win = tk.Toplevel(root)
    win.title("Employee Management")
    win.geometry("650x450")

    tk.Label(win, text="EMPLOYEE MANAGEMENT",
             font=("Arial", 18, "bold")).pack(pady=15)

    frame = tk.Frame(win)
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

    tree = ttk.Treeview(win, columns=("Username", "Role"),
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

    tk.Button(win, text="Add Employee", command=add).pack(side="left", padx=160)
    tk.Button(win, text="Delete Employee", command=delete).pack(side="left")

    refresh()



def billing_screen():
    win = tk.Toplevel(root)
    win.title("Create New Bill")
    win.geometry("1000x700")

    tk.Label(win, text="BILL GENERATION",
             font=("Arial", 20, "bold")).pack(pady=10)

    top = tk.Frame(win)
    top.pack(pady=5)

    tk.Label(top, text="Customer Name").grid(row=0, column=0, padx=5)
    customer = ttk.Combobox(top, width=25)
    customer.grid(row=0, column=1, padx=5)

    cur.execute("SELECT name FROM customers")
    customer["values"] = [r[0] for r in cur.fetchall()]

    tk.Label(top, text="New Customer Phone").grid(row=0, column=2, padx=5)
    phone = tk.Entry(top, width=18)
    phone.grid(row=0, column=3, padx=5)

    product_frame = tk.Frame(win)
    product_frame.pack(pady=15)

    tk.Label(product_frame, text="Product").grid(row=0, column=0)
    product = ttk.Combobox(product_frame, width=30, state="readonly")
    product.grid(row=0, column=1, padx=10)

    tk.Label(product_frame, text="Quantity").grid(row=0, column=2)
    quantity = tk.Entry(product_frame, width=10)
    quantity.grid(row=0, column=3, padx=10)

    def refresh_products():
        cur.execute("SELECT name FROM products WHERE stock>0")
        product["values"] = [r[0] for r in cur.fetchall()]

    tree = ttk.Treeview(win,
        columns=("Product", "Price", "Quantity", "Amount"),
        show="headings")

    for col in ("Product", "Price", "Quantity", "Amount"):
        tree.heading(col, text=col)
        tree.column(col, width=180)

    tree.pack(fill="both", expand=True, padx=15, pady=10)

    subtotal_var = tk.StringVar(value="0.00")

    def add_to_cart():
        try:
            pname = product.get()
            qty = int(quantity.get())

            if not pname or qty <= 0:
                raise ValueError("Select a product and enter valid quantity")

            cur.execute("SELECT price,stock FROM products WHERE name=?", (pname,))
            result = cur.fetchone()

            if not result:
                raise ValueError("Product not found")

            price, stock = result
            already = sum(item[1] for item in cart if item[0] == pname)

            if qty + already > stock:
                raise ValueError("Not enough stock available")

            for item in cart:
                if item[0] == pname:
                    item[1] += qty
                    item[3] = item[1] * item[2]
                    break
            else:
                cart.append([pname, qty, price, qty * price])

            refresh_cart()
            quantity.delete(0, tk.END)

        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def refresh_cart():
        tree.delete(*tree.get_children())
        total = 0

        for item in cart:
            tree.insert("", "end",
                        values=(item[0], item[2], item[1], item[3]))
            total += item[3]

        subtotal_var.set(f"{total:.2f}")

    def remove_item():
        selected = tree.selection()
        if not selected:
            return

        pname = tree.item(selected[0])["values"][0]
        for item in cart:
            if item[0] == pname:
                cart.remove(item)
                break
        refresh_cart()

    tk.Button(product_frame, text="Add to Bill",
              command=add_to_cart).grid(row=0, column=4, padx=10)

    tk.Button(win, text="Remove Selected Product",
              command=remove_item).pack(pady=5)

    bottom = tk.Frame(win)
    bottom.pack(pady=15)

    tk.Label(bottom, text="Subtotal:").grid(row=0, column=0, padx=10)
    tk.Label(bottom, textvariable=subtotal_var,
             font=("Arial", 12, "bold")).grid(row=0, column=1)

    tk.Label(bottom, text="Discount (%)").grid(row=1, column=0, pady=5)
    discount = tk.Entry(bottom, width=15)
    discount.insert(0, "0")
    discount.grid(row=1, column=1)

    tk.Label(bottom, text="GST (%)").grid(row=2, column=0, pady=5)
    tax = tk.Entry(bottom, width=15)
    tax.insert(0, "0")
    tax.grid(row=2, column=1)

    tk.Label(bottom, text="Payment Method").grid(row=3, column=0, pady=5)
    payment = ttk.Combobox(bottom, values=["Cash", "UPI", "Card"],
                           state="readonly", width=13)
    payment.set("Cash")
    payment.grid(row=3, column=1)

    total_var = tk.StringVar(value="0.00")

    tk.Label(bottom, text="Final Amount:").grid(row=4, column=0, pady=10)
    tk.Label(bottom, textvariable=total_var,
             font=("Arial", 15, "bold")).grid(row=4, column=1)

    def calculate():
        try:
            sub = sum(item[3] for item in cart)
            d = float(discount.get())
            t = float(tax.get())

            if not 0 <= d <= 100 or not 0 <= t <= 100:
                raise ValueError("Discount and GST must be between 0 and 100")

            discounted = sub - (sub * d / 100)
            final = discounted + (discounted * t / 100)

            total_var.set(f"{final:.2f}")
            return sub, d, t, final

        except ValueError as e:
            messagebox.showerror("Error", str(e))
            return None

    tk.Button(bottom, text="Calculate Total",
              command=calculate).grid(row=4, column=2, padx=15)

    def save_bill():
        if not cart:
            messagebox.showerror("Error", "Add products first")
            return

        if not customer.get().strip():
            messagebox.showerror("Error", "Enter customer name")
            return

        result = calculate()
        if result is None:
            return

        sub, d, t, final = result

        if not payment.get():
            messagebox.showerror("Error", "Select payment method")
            return

        for item in cart:
            cur.execute("SELECT stock FROM products WHERE name=?", (item[0],))
            row = cur.fetchone()
            if not row or row[0] < item[1]:
                messagebox.showerror("Error", "Insufficient stock: " + item[0])
                return

        try:
            db.execute("BEGIN")

            phone_value = phone.get().strip()
            cur.execute("SELECT id FROM customers WHERE name=?",
                        (customer.get().strip(),))
            if not cur.fetchone():
                cur.execute("INSERT INTO customers(name,phone) VALUES(?,?)",
                            (customer.get().strip(), phone_value))

            cur.execute("""INSERT INTO sales
                (customer,subtotal,discount,tax,total,payment,date,status)
                VALUES(?,?,?,?,?,?,?,?)""",
                (customer.get(), sub, d, t, final, payment.get(),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Completed"))

            sale_id = cur.lastrowid

            for item in cart:
                cur.execute("""INSERT INTO sale_items
                    (sale_id,product,quantity,price,amount)
                    VALUES(?,?,?,?,?)""",
                    (sale_id, item[0], item[1], item[2], item[3]))

                cur.execute("""UPDATE products SET stock=stock-?
                    WHERE name=?""", (item[1], item[0]))

            db.commit()

        except Exception as e:
            db.rollback()
            messagebox.showerror("Database Error", str(e))
            return

        invoice = f"""
====================================
          BILLING SYSTEM
====================================
Invoice Number : {sale_id}
Date           : {datetime.now()}
Customer       : {customer.get()}
------------------------------------
Product       Qty       Price       Amount
------------------------------------
"""
        for item in cart:
            invoice += f"{item[0]:15} {item[1]:5} {item[2]:10.2f} {item[3]:10.2f}\n"

        invoice += f"""
------------------------------------
Subtotal       : Rs. {sub:.2f}
Discount       : {d}%
GST            : {t}%
Final Amount   : Rs. {final:.2f}
Payment        : {payment.get()}
------------------------------------
       THANK YOU! VISIT AGAIN
====================================
"""

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"Invoice_{sale_id}.txt",
            filetypes=[("Text files", "*.txt")])

        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(invoice)

        messagebox.showinfo("Success",
                            f"Bill #{sale_id} saved successfully")

        cart.clear()
        refresh_cart()
        refresh_products()
        customer.set("")
        phone.delete(0, tk.END)
        total_var.set("0.00")

    tk.Button(win, text="SAVE BILL / GENERATE INVOICE",
              bg="green", fg="white",
              font=("Arial", 12, "bold"),
              command=save_bill).pack(pady=15)

    refresh_products()



def history_screen():
    win = tk.Toplevel(root)
    win.title("Sales History")
    win.geometry("950x550")

    tk.Label(win, text="SALES TRANSACTION HISTORY",
             font=("Arial", 18, "bold")).pack(pady=15)

    tree = ttk.Treeview(win,
        columns=("ID", "Customer", "Subtotal", "Discount",
                 "Tax", "Total", "Payment", "Date", "Status"),
        show="headings")

    for col in ("ID", "Customer", "Subtotal", "Discount",
                "Tax", "Total", "Payment", "Date", "Status"):
        tree.heading(col, text=col)
        tree.column(col, width=100)

    tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh():
        tree.delete(*tree.get_children())
        cur.execute("SELECT * FROM sales ORDER BY id DESC")
        for row in cur.fetchall():
            tree.insert("", "end", values=row)

    def cancel_sale():
        selected = tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Select a transaction")
            return

        values = tree.item(selected[0])["values"]
        sale_id = values[0]

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
                items = cur.fetchall()

                for pname, qty in items:
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

    tk.Button(win, text="Cancel Transaction",
              command=cancel_sale).pack(pady=10)

    refresh()



def report_screen():
    win = tk.Toplevel(root)
    win.title("Sales Reports")
    win.geometry("600x450")

    tk.Label(win, text="SALES REPORTS",
             font=("Arial", 20, "bold")).pack(pady=20)

    result = tk.Label(win, text="", font=("Arial", 14),
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

    buttons = tk.Frame(win)
    buttons.pack()

    for period in ("Daily", "Weekly", "Monthly"):
        tk.Button(buttons, text=period,
                  width=15, command=lambda p=period: report(p)
                  ).pack(side="left", padx=10)



def main_screen():
    root.title("Billing Management System - Dashboard")

    tk.Label(root, text="BILLING MANAGEMENT SYSTEM",
             font=("Arial", 25, "bold"),
             bg="#1c3557", fg="white",
             pady=20).pack(fill="x")

    tk.Label(root, text=f"Welcome {current_user} ({current_role})",
             font=("Arial", 13),
             bg="#eaf0f6").pack(pady=15)

    frame = tk.Frame(root, bg="#eaf0f6")
    frame.pack(pady=30)

    def make_button(text, command, row, col):
        tk.Button(frame, text=text, command=command,
                  width=25, height=3,
                  font=("Arial", 11, "bold"),
                  bg="#28527a", fg="white",
                  cursor="hand2").grid(row=row, column=col,
                                      padx=15, pady=15)

    if current_role == "Admin":
        make_button("Product Management", product_screen, 0, 0)
        make_button("Customer Management", customer_screen, 0, 1)
        make_button("Employee Management", user_screen, 1, 0)
        make_button("Sales Reports", report_screen, 1, 1)

    make_button("Create New Bill", billing_screen, 2, 0)
    make_button("Sales History", history_screen, 2, 1)
    make_button("Logout", logout, 3, 0)



login_frame = tk.Frame(root, bg="#eaf0f6")
login_frame.pack(expand=True)

tk.Label(login_frame, text="BILLING SYSTEM",
         font=("Arial", 25, "bold"),
         bg="#eaf0f6", fg="#1c3557").pack(pady=20)

tk.Label(login_frame, text="Username",
         font=("Arial", 12), bg="#eaf0f6").pack()

user_entry = tk.Entry(login_frame, width=30,
                      font=("Arial", 12))
user_entry.pack(pady=8)

tk.Label(login_frame, text="Password",
         font=("Arial", 12), bg="#eaf0f6").pack()

pass_entry = tk.Entry(login_frame, width=30,
                      show="*", font=("Arial", 12))
pass_entry.pack(pady=8)

tk.Button(login_frame, text="LOGIN",
          command=login, width=20, height=2,
          bg="#28527a", fg="white",
          font=("Arial", 12, "bold")).pack(pady=20)

tk.Label(login_frame,
         text="Admin Username: admin\nAdmin Password: admin123",
         bg="#eaf0f6", fg="gray").pack(pady=10)

root.mainloop()
