# Billing Management System

A desktop-based Billing Management System developed using **Python, Tkinter, and SQLite**. This application helps manage products, customers, employees, sales transactions, invoices, and sales reports.

## Features

### 1. Login System
- Admin and Staff login.
- Username and password authentication.
- Role-based access.

### 2. Product Management (Admin)
- Add new products.
- Update product details.
- Delete products.
- Manage product name, category, price, and stock.

### 3. Customer Management (Admin)
- Add new customers.
- View customer details.
- Delete customers.
- Store customer name and phone number.

### 4. Employee Management (Admin)
- Add employees.
- Assign Admin or Staff roles.
- Delete employees.
- Prevent deletion of the default admin account.

### 5. Billing System
- Search and select products.
- Add products to cart.
- Update product quantities.
- Remove products from cart.
- Automatic subtotal calculation.
- Discount calculation.
- 18% tax calculation.
- Cash, UPI, and Card payment options.
- Generate invoices.

### 6. Invoice Management
- Generate invoices automatically.
- Save invoices as TXT files.
- Print invoices.
- Display customer and cashier details.

### 7. Sales History
- View previous transactions.
- View and print invoices.
- Cancel completed transactions (Admin only).
- Automatically restore product stock after cancellation.

### 8. Sales Reports (Admin)
- Daily sales report.
- Weekly sales report.
- Monthly sales report.
- Total number of sales.
- Total revenue calculation.

## Technologies Used

- **Programming Language:** Python
- **GUI:** Tkinter
- **Database:** SQLite
- **Database Library:** sqlite3
- **Additional Libraries:** os, tempfile, datetime

## Requirements

- Python 3.x
- Windows / Linux
- VS Code or any Python IDE

No external Python packages are required because the project uses Python's built-in libraries.

## Installation and Setup

**Step 1: Download or Clone the Repository**

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
```

**Step 2: Open the Project Folder**

Open the downloaded folder in VS Code.

**Step 3: Run the Application**

```bash
python Billing_system.py
```

## Default Admin Login

| Field | Details |
|---|---|
| Username | admin |
| Password | admin123 |
| Role | Admin |

**Note:** Change the default password before using the application in a real environment.

## Database Information

The application automatically creates an SQLite database named:

`billing.db`

The database contains the following tables:

- `users` – Stores login details and employee roles.
- `products` – Stores product information and stock.
- `customers` – Stores customer information.
- `sales` – Stores billing and transaction records.
- `sale_items` – Stores individual products in each sale.

## Project Structure

```text
Billing_System/
│
├── Billing_system.py
├── billing.db          (Created automatically)
├── README.md
└── Invoice Files       (Generated when saved)
```

## Future Improvements

- Password encryption.
- Improved invoice design.
- PDF invoice generation.
- Online payment integration.
- Cloud database support.
- Advanced sales analytics.

## Author

**Sk Jahir Ali**

BCA Student

## License

This project is developed for educational and academic purposes.
