from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from io import BytesIO
from pathlib import Path

from flask import (
    Flask, flash, redirect, render_template, request, send_file,
    session, url_for, jsonify
)
from werkzeug.security import check_password_hash, generate_password_hash

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

try:
    from num2words import num2words
except ImportError:
    num2words = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "grace_web.db"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-public-deployment")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

COMPANY = {
    "name": "Grace Furnitures",
    "address": "No.27, Sai Baba Street, Sandhosh Nagar, Palavakkam, Chennai, Tamil Nadu - 600041",
    "gstin": "33BBNPR5674N1ZS",
    "state": "Tamil Nadu",
    "email": "gracefurnitures01@gmail.com",
    "jurisdiction": "SUBJECT TO CHENNAI JURISDICTION",
}
CGST_RATE = Decimal("9.00")
SGST_RATE = Decimal("9.00")
DEFAULT_HSN = "940350"


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            hsn TEXT NOT NULL DEFAULT '940350',
            default_rate REAL
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            address TEXT NOT NULL,
            gstin TEXT,
            state TEXT NOT NULL DEFAULT 'Tamil Nadu',
            place_of_supply TEXT NOT NULL DEFAULT 'Tamil Nadu'
        );

        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_no TEXT NOT NULL UNIQUE COLLATE NOCASE
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no INTEGER NOT NULL UNIQUE,
            invoice_date TEXT NOT NULL,
            consignee_name TEXT NOT NULL,
            consignee_address TEXT NOT NULL,
            consignee_gstin TEXT,
            consignee_state TEXT,
            buyer_name TEXT NOT NULL,
            buyer_address TEXT NOT NULL,
            buyer_gstin TEXT,
            buyer_state TEXT,
            place_of_supply TEXT,
            vehicle_no TEXT NOT NULL,
            despatched_through TEXT DEFAULT 'By Road',
            destination TEXT DEFAULT 'Chennai',
            delivery_note TEXT,
            other_reference TEXT,
            despatch_document_no TEXT,
            delivery_note_date TEXT,
            bill_of_lading TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            line_no INTEGER NOT NULL,
            description TEXT NOT NULL,
            hsn TEXT NOT NULL,
            quantity REAL NOT NULL,
            rate REAL NOT NULL,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
        );
        """
    )

    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "Grace@2026")
    exists = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not exists:
        con.execute(
            "INSERT INTO users(username,password_hash) VALUES (?,?)",
            (username, generate_password_hash(password)),
        )

    seed_products = [
        ("Jfa-pgf-ct21 Office Table", "940330", 1250),
        ("3*2 Pooja", "940360", 4500),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO products(name,hsn,default_rate) VALUES (?,?,?)",
        seed_products,
    )

    # Remove unwanted built-in products from databases created by older versions.
    unwanted_default_products = (
        "Dining Table",
        "Kitchen Furniture",
        "Metal Office Furniture",
        "Office Table",
        "Pooja Unit",
        "Sofa",
        "Wooden Bed",
        "Wooden Chair",
        "Wooden Cot",
        "Wooden Wardrobe",
    )
    placeholders = ",".join("?" for _ in unwanted_default_products)
    con.execute(
        f"DELETE FROM products WHERE name IN ({placeholders})",
        unwanted_default_products,
    )

    seed_customers = [
        (
            "Jayabharatham Furniture & Appliance Pvt Ltd",
            "No:3, Kalingarayan Street,Royapettah\nChennai Tamil Nadu 600014\nIndia",
            "33AAACJ1521A1ZK",
            "Tamil Nadu",
            "Tamil Nadu",
        ),
        (
            "Hari Furniture & Bed Centre",
            "No.13/33, Avvai Nagar Main Road, Thiruvanmiyur, Chennai,\nTamil Nadu-600 041",
            "33ABGPH5162H1ZW",
            "Tamil Nadu",
            "Tamil Nadu",
        ),
    ]
    con.executemany(
        "INSERT OR IGNORE INTO customers(name,address,gstin,state,place_of_supply) VALUES (?,?,?,?,?)",
        seed_customers,
    )
    con.executemany(
        "INSERT OR IGNORE INTO vehicles(vehicle_no) VALUES (?)",
        [("TN03X1711",), ("TN06AD0536",)],
    )
    con.commit()
    con.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(value) -> str:
    """Grand-total format used in the original invoice (with thousands separators)."""
    return f"{dec(value):,.2f}"


def fmt_plain(value) -> str:
    """Line-value and tax format used in the original invoice (without commas)."""
    return f"{dec(value):.2f}"


def display_date(value) -> str:
    """Render an ISO date as 17-Jul-2026, matching the original invoice."""
    text = str(value or "").strip()
    if not text:
        return ""
    for pattern in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).strftime("%d-%b-%Y")
        except ValueError:
            pass
    return text


def amount_words(value) -> str:
    value = dec(value)
    rupees = int(value)
    paise = int((value - rupees) * 100)
    if num2words:
        words = num2words(rupees, lang="en_IN").replace("-", " ").replace(",", "")
        result = f"INR {words.title()} Rupees"
        if paise:
            p = num2words(paise, lang="en_IN").replace("-", " ").replace(",", "")
            result += f" and {p.title()} Paise"
        return result + " Only"
    return f"INR {rupees:,} Rupees Only"


def next_invoice_no(con) -> int:
    row = con.execute("SELECT COALESCE(MAX(invoice_no),0)+1 AS n FROM invoices").fetchone()
    return int(row["n"])


def parse_items(form):
    descriptions = form.getlist("description[]")
    hsns = form.getlist("hsn[]")
    quantities = form.getlist("quantity[]")
    rates = form.getlist("rate[]")
    items = []
    for i, description in enumerate(descriptions):
        description = description.strip()
        if not description:
            continue
        hsn = (hsns[i].strip() if i < len(hsns) else "") or DEFAULT_HSN
        quantity = dec(quantities[i] if i < len(quantities) else 0)
        rate = dec(rates[i] if i < len(rates) else 0)
        if quantity <= 0:
            raise ValueError(f"Quantity must be greater than zero for item {i+1}.")
        if rate < 0:
            raise ValueError(f"Rate cannot be negative for item {i+1}.")
        items.append({"description": description, "hsn": hsn, "quantity": quantity, "rate": rate})
    if not items:
        raise ValueError("Add at least one item.")
    return items


def save_vehicle(con, vehicle_no):
    """Save a newly entered vehicle number for future invoices."""
    vehicle_no = (vehicle_no or "").strip().upper()
    if vehicle_no:
        con.execute("INSERT OR IGNORE INTO vehicles(vehicle_no) VALUES (?)", (vehicle_no,))


def save_customer(con, name, address, gstin, state, place_of_supply):
    """Save a newly entered customer or refresh an existing customer record."""
    name = (name or "").strip()
    address = (address or "").strip()
    if not name or not address:
        return
    con.execute(
        """
        INSERT INTO customers(name,address,gstin,state,place_of_supply)
        VALUES (?,?,?,?,?)
        ON CONFLICT(name) DO UPDATE SET
            address=excluded.address,
            gstin=excluded.gstin,
            state=excluded.state,
            place_of_supply=excluded.place_of_supply
        """,
        (name, address, (gstin or "").strip(), (state or "Tamil Nadu").strip(),
         (place_of_supply or state or "Tamil Nadu").strip()),
    )


def invoice_form_data(form):
    required = {
        "consignee_name": "Consignee name",
        "consignee_address": "Consignee address",
        "buyer_name": "Buyer name",
        "buyer_address": "Buyer address",
        "vehicle_no": "Vehicle number",
    }
    data = {k: form.get(k, "").strip() for k in [
        "invoice_date", "consignee_name", "consignee_address", "consignee_gstin", "consignee_state",
        "buyer_name", "buyer_address", "buyer_gstin", "buyer_state", "place_of_supply",
        "vehicle_no", "despatched_through", "destination", "delivery_note", "other_reference",
        "despatch_document_no", "delivery_note_date", "bill_of_lading"
    ]}
    for key, label in required.items():
        if not data[key]:
            raise ValueError(f"{label} is required.")
    data["vehicle_no"] = data["vehicle_no"].upper()
    raw_invoice_no = (form.get("invoice_no") or "").strip()
    if not raw_invoice_no:
        raise ValueError("Invoice number is required.")
    try:
        data["invoice_no"] = int(raw_invoice_no)
    except ValueError as exc:
        raise ValueError("Invoice number must be a whole number.") from exc
    if data["invoice_no"] < 1:
        raise ValueError("Invoice number must be 1 or greater.")
    return data


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        con = db()
        user = con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        con.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    con = db()
    invoices = con.execute(
        "SELECT * FROM invoices ORDER BY invoice_no DESC LIMIT 100"
    ).fetchall()
    con.close()
    return render_template("dashboard.html", invoices=invoices)


@app.route("/invoice/new")
@login_required
def new_invoice():
    con = db()
    number = next_invoice_no(con)
    products = con.execute("SELECT * FROM products ORDER BY name").fetchall()
    customers = con.execute("SELECT * FROM customers ORDER BY name").fetchall()
    vehicles = con.execute("SELECT * FROM vehicles ORDER BY vehicle_no").fetchall()
    con.close()
    invoice = {
        "invoice_no": number,
        "invoice_date": date.today().isoformat(),
        "consignee_state": "Tamil Nadu",
        "buyer_state": "Tamil Nadu",
        "place_of_supply": "Tamil Nadu",
        "despatched_through": "By Road",
        "destination": "Chennai",
    }
    return render_template("invoice_form.html", invoice=invoice, items=[{}], products=products, customers=customers, vehicles=vehicles, is_edit=False)


@app.route("/invoice/create", methods=["POST"])
@login_required
def create_invoice():
    try:
        header = invoice_form_data(request.form)
        items = parse_items(request.form)
    except (ValueError, TypeError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("new_invoice"))

    con = db()
    now = datetime.now().isoformat(timespec="seconds")
    try:
        cur = con.execute(
            """
            INSERT INTO invoices (
                invoice_no,invoice_date,consignee_name,consignee_address,consignee_gstin,consignee_state,
                buyer_name,buyer_address,buyer_gstin,buyer_state,place_of_supply,vehicle_no,
                despatched_through,destination,delivery_note,other_reference,despatch_document_no,
                delivery_note_date,bill_of_lading,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                header["invoice_no"],header["invoice_date"],header["consignee_name"],header["consignee_address"],
                header["consignee_gstin"],header["consignee_state"],header["buyer_name"],header["buyer_address"],
                header["buyer_gstin"],header["buyer_state"],header["place_of_supply"],header["vehicle_no"],
                header["despatched_through"],header["destination"],header["delivery_note"],header["other_reference"],
                header["despatch_document_no"],header["delivery_note_date"],header["bill_of_lading"],now,now,
            ),
        )
        invoice_id = cur.lastrowid
        for line, item in enumerate(items, 1):
            con.execute(
                "INSERT INTO invoice_items(invoice_id,line_no,description,hsn,quantity,rate) VALUES (?,?,?,?,?,?)",
                (invoice_id,line,item["description"],item["hsn"],float(item["quantity"]),float(item["rate"])),
            )
            con.execute(
                "INSERT INTO products(name,hsn,default_rate) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET hsn=excluded.hsn, default_rate=excluded.default_rate",
                (item["description"],item["hsn"],float(item["rate"])),
            )
        save_customer(con, header["consignee_name"], header["consignee_address"],
                      header["consignee_gstin"], header["consignee_state"], header["place_of_supply"])
        save_customer(con, header["buyer_name"], header["buyer_address"],
                      header["buyer_gstin"], header["buyer_state"], header["place_of_supply"])
        save_vehicle(con, header["vehicle_no"])
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        flash("That invoice number is already used. Enter another invoice number.", "danger")
        return redirect(url_for("new_invoice"))
    finally:
        con.close()

    flash("Invoice saved.", "success")
    return redirect(url_for("view_invoice", invoice_id=invoice_id))


@app.route("/invoice/<int:invoice_id>")
@login_required
def view_invoice(invoice_id):
    con = db()
    invoice = con.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    items = con.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY line_no", (invoice_id,)).fetchall()
    con.close()
    if not invoice:
        return "Invoice not found", 404
    subtotal = sum((dec(x["quantity"]) * dec(x["rate"]) for x in items), Decimal("0"))
    cgst = dec(subtotal * CGST_RATE / 100)
    sgst = dec(subtotal * SGST_RATE / 100)
    total = dec(subtotal + cgst + sgst)
    return render_template("invoice_view.html", invoice=invoice, items=items, subtotal=subtotal,
                           cgst=cgst, sgst=sgst, total=total, fmt=fmt, company=COMPANY)


@app.route("/invoice/<int:invoice_id>/edit")
@login_required
def edit_invoice(invoice_id):
    con = db()
    invoice = con.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    items = con.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY line_no", (invoice_id,)).fetchall()
    products = con.execute("SELECT * FROM products ORDER BY name").fetchall()
    customers = con.execute("SELECT * FROM customers ORDER BY name").fetchall()
    vehicles = con.execute("SELECT * FROM vehicles ORDER BY vehicle_no").fetchall()
    con.close()
    if not invoice:
        return "Invoice not found", 404
    return render_template("invoice_form.html", invoice=invoice, items=items, products=products, customers=customers, vehicles=vehicles, is_edit=True)


@app.route("/invoice/<int:invoice_id>/update", methods=["POST"])
@login_required
def update_invoice(invoice_id):
    try:
        header = invoice_form_data(request.form)
        items = parse_items(request.form)
    except (ValueError, TypeError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("edit_invoice", invoice_id=invoice_id))

    con = db()
    now = datetime.now().isoformat(timespec="seconds")
    try:
        con.execute(
            """
            UPDATE invoices SET invoice_no=?,invoice_date=?,consignee_name=?,consignee_address=?,
            consignee_gstin=?,consignee_state=?,buyer_name=?,buyer_address=?,buyer_gstin=?,buyer_state=?,
            place_of_supply=?,vehicle_no=?,despatched_through=?,destination=?,delivery_note=?,other_reference=?,
            despatch_document_no=?,delivery_note_date=?,bill_of_lading=?,updated_at=? WHERE id=?
            """,
            (
                header["invoice_no"],header["invoice_date"],header["consignee_name"],header["consignee_address"],
                header["consignee_gstin"],header["consignee_state"],header["buyer_name"],header["buyer_address"],
                header["buyer_gstin"],header["buyer_state"],header["place_of_supply"],header["vehicle_no"],
                header["despatched_through"],header["destination"],header["delivery_note"],header["other_reference"],
                header["despatch_document_no"],header["delivery_note_date"],header["bill_of_lading"],now,invoice_id,
            ),
        )
        con.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
        for line, item in enumerate(items, 1):
            con.execute(
                "INSERT INTO invoice_items(invoice_id,line_no,description,hsn,quantity,rate) VALUES (?,?,?,?,?,?)",
                (invoice_id,line,item["description"],item["hsn"],float(item["quantity"]),float(item["rate"])),
            )
            con.execute(
                "INSERT INTO products(name,hsn,default_rate) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET hsn=excluded.hsn, default_rate=excluded.default_rate",
                (item["description"],item["hsn"],float(item["rate"])),
            )
        save_customer(con, header["consignee_name"], header["consignee_address"],
                      header["consignee_gstin"], header["consignee_state"], header["place_of_supply"])
        save_customer(con, header["buyer_name"], header["buyer_address"],
                      header["buyer_gstin"], header["buyer_state"], header["place_of_supply"])
        save_vehicle(con, header["vehicle_no"])
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback()
        flash("That invoice number is already used.", "danger")
        return redirect(url_for("edit_invoice", invoice_id=invoice_id))
    finally:
        con.close()
    flash("Invoice updated.", "success")
    return redirect(url_for("view_invoice", invoice_id=invoice_id))


@app.route("/invoice/<int:invoice_id>/delete", methods=["POST"])
@login_required
def delete_invoice(invoice_id):
    con = db()
    con.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
    con.commit()
    con.close()
    flash("Invoice deleted.", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/customer")
@login_required
def api_customer():
    name = request.args.get("name", "").strip()
    con = db()
    customer = con.execute(
        "SELECT name,address,gstin,state,place_of_supply FROM customers WHERE name=? COLLATE NOCASE",
        (name,),
    ).fetchone()
    con.close()
    if not customer:
        return jsonify({"found": False})
    return jsonify({
        "found": True,
        "name": customer["name"],
        "address": customer["address"],
        "gstin": customer["gstin"] or "",
        "state": customer["state"] or "Tamil Nadu",
        "place_of_supply": customer["place_of_supply"] or customer["state"] or "Tamil Nadu",
    })


@app.route("/api/product")
@login_required
def api_product():
    name = request.args.get("name", "").strip()
    con = db()
    product = con.execute("SELECT * FROM products WHERE name=? COLLATE NOCASE", (name,)).fetchone()
    con.close()
    if product:
        return jsonify({"found": True, "hsn": product["hsn"], "rate": product["default_rate"]})
    return jsonify({"found": False, "hsn": DEFAULT_HSN, "rate": None})


def p(text, style):
    text = str(text or "")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("\n", "<br/>")
    return Paragraph(text, style)


def bold_label(label, value, style):
    # Only controlled markup is inserted here; user text remains escaped.
    safe = str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace("\n", "<br/>")
    return Paragraph(f"{label}<br/><b>{safe}</b>", style)


def make_pdf(invoice, items):
    buffer = BytesIO()

    # Dynamically compress only the vertical spacing when many products are
    # present. This keeps an 8-item invoice on one A4 page without changing
    # the approved border structure or column widths.
    item_count = len(items)
    compact = item_count >= 6
    very_compact = item_count >= 9

    page_margin = 4*mm if compact else 6*mm
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=8*mm, rightMargin=8*mm,
        topMargin=page_margin, bottomMargin=page_margin
    )

    if very_compact:
        normal_size, normal_leading = 5.4, 6.2
        header_size, header_leading = 5.8, 6.8
        title_size, title_leading = 8.0, 8.8
        title_space = 0.6*mm
    elif compact:
        normal_size, normal_leading = 5.8, 6.7
        header_size, header_leading = 6.2, 7.3
        title_size, title_leading = 8.4, 9.2
        title_space = 0.8*mm
    else:
        normal_size, normal_leading = 6.4, 7.6
        header_size, header_leading = 6.9, 8.5
        title_size, title_leading = 9.0, 10.0
        title_space = 2*mm

    normal = ParagraphStyle("n", fontName="Helvetica", fontSize=normal_size, leading=normal_leading)
    tiny = ParagraphStyle("t", parent=normal, fontSize=max(5.0, normal_size-0.6), leading=max(5.8, normal_leading-0.8))
    header_text = ParagraphStyle("ht", fontName="Helvetica", fontSize=header_size, leading=header_leading)
    bold = ParagraphStyle("b", parent=normal, fontName="Helvetica-Bold")
    center = ParagraphStyle("c", parent=normal, alignment=TA_CENTER)
    right = ParagraphStyle("r", parent=normal, alignment=TA_RIGHT)
    title = ParagraphStyle("title", parent=normal, fontName="Helvetica-Bold", fontSize=title_size, leading=title_leading, alignment=TA_CENTER)

    story = [Paragraph("TAX INVOICE", title), Spacer(1, title_space)]
    company = Paragraph(
        f"<b>{COMPANY['name']}</b><br/>"
        "No.27, Sai Baba Street,<br/>Sandhosh Nagar, Palavakkam,<br/>"
        "Chennai, Tamil Nadu - 600041<br/>"
        f"GSTIN/UIN:{COMPANY['gstin']}<br/>"
        f"State Name: {COMPANY['state']}<br/>Email: {COMPANY['email']}", header_text
    )
    consignee_extra = ""
    if invoice["consignee_gstin"]:
        consignee_extra += f"<br/>GSTIN: {invoice['consignee_gstin']}"
    if invoice["consignee_state"]:
        consignee_extra += f"<br/>State Name: {invoice['consignee_state']}"
    consignee = Paragraph(
        "Consignee(Shipping Address)<br/><br/><b>" +
        str(invoice["consignee_name"]).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;") +
        "</b><br/>" + str(invoice["consignee_address"]).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>") +
        consignee_extra, header_text
    )
    buyer = Paragraph(
        "Buyer (if other than consignee)<br/><br/><b>" +
        str(invoice["buyer_name"]).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;") +
        "</b><br/>" + str(invoice["buyer_address"]).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br/>") +
        f"<br/>GSTIN: {invoice['buyer_gstin'] or ''}<br/>State Name: {invoice['buyer_state'] or ''}"
        f"<br/>Place of Supply: {invoice['place_of_supply'] or ''}", header_text
    )

    # Compact fixed-height header to retain one-page output for normal invoices.
    meta = [
        [company, bold_label("Invoice No.", invoice["invoice_no"], normal), bold_label("Dated", display_date(invoice["invoice_date"]), normal)],
        ["", bold_label("Delivery Note", invoice["delivery_note"], normal), bold_label("Other Reference(s)", invoice["other_reference"], normal)],
        [consignee, bold_label("Supplier's Ref.", invoice["invoice_no"], normal), ""],
        ["", bold_label("Despatch Document No.", invoice["despatch_document_no"], normal), bold_label("Delivery Note Date", invoice["delivery_note_date"], normal)],
        [buyer, bold_label("Despatched through", invoice["despatched_through"], normal), bold_label("Destination", invoice["destination"], normal)],
        ["", bold_label("Bill of Lading/LR-RR No.", invoice["bill_of_lading"], normal), bold_label("Motor Vehicle No.", invoice["vehicle_no"], normal)],
    ]
    if very_compact:
        meta_heights = [18*mm,8*mm,19*mm,8*mm,19*mm,8*mm]
    elif compact:
        meta_heights = [20*mm,9*mm,21*mm,9*mm,21*mm,9*mm]
    else:
        meta_heights = [24*mm,11*mm,25*mm,11*mm,25*mm,11*mm]
    meta_table = Table(meta, colWidths=[96*mm,48*mm,48*mm], rowHeights=meta_heights)
    meta_table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.55,colors.black),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
        ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("SPAN",(0,0),(0,1)),("SPAN",(0,2),(0,3)),("SPAN",(0,4),(0,5)),
    ]))
    story.append(meta_table)

    subtotal = sum((dec(x["quantity"]) * dec(x["rate"]) for x in items), Decimal("0"))
    cgst = dec(subtotal * CGST_RATE / 100)
    sgst = dec(subtotal * SGST_RATE / 100)
    total = dec(subtotal + cgst + sgst)
    qty_total = sum((dec(x["quantity"]) for x in items), Decimal("0"))

    rows = [[p("Sl No.",center),p("Description of Goods",center),p("HSN/SAC",center),p("Quantity",center),p("Rate",center),p("per",center),p("Amount",center)]]
    for i, item in enumerate(items,1):
        rows.append([
            p(i,center), p(item["description"],bold), p(item["hsn"],center),
            p(f"{dec(item['quantity']):f}".rstrip("0").rstrip("."),center),
            p(f"{dec(item['rate']):f}".rstrip("0").rstrip("."),center), p("",center),
            p(fmt_plain(dec(item["quantity"])*dec(item["rate"])),right),
        ])

    # Use one open tax block instead of three separately bordered rows.
    # This matches the original invoice: CGST, SGST, and Round Off appear
    # as neatly spaced lines inside the goods area without horizontal boxes.
    # Reserve a small full-width separator row below Total, as in the original.
    # Reduce the flexible tax block by the same amount so the invoice stays on one page.
    if very_compact:
        tax_block_height = 10*mm
        item_header_height = 5*mm
        item_row_height = 5.2*mm
        total_height = 5.5*mm
        separator_height = 1.5*mm
        tax_line_leading = 6.2
    elif compact:
        # For 6-8 products the large decorative blank area is reduced first.
        tax_block_height = max(11*mm, (22 - max(0, item_count-6)*3) * mm)
        item_header_height = 5.5*mm
        item_row_height = 5.8*mm
        total_height = 6*mm
        separator_height = 2*mm
        tax_line_leading = 7.0
    else:
        tax_block_height = max(29*mm, (49 - max(0, item_count-1)*5) * mm)
        item_header_height = 7*mm
        item_row_height = 8*mm
        total_height = 7*mm
        separator_height = 3*mm
        tax_line_leading = 10.5

    tax_labels = Paragraph(
        "<b>CGST@9%</b><br/><b>SGST@9%</b><br/><b>Round Off Sales</b>",
        ParagraphStyle("taxlabels", parent=right, leading=tax_line_leading)
    )
    tax_values = Paragraph(
        f"{fmt_plain(cgst)}<br/>{fmt_plain(sgst)}<br/>0.00",
        ParagraphStyle("taxvalues", parent=right, leading=tax_line_leading)
    )
    rows += [
        ["",tax_labels,"","","","",tax_values],
        [p("Total",right),"","",p(f"{qty_total:f}".rstrip("0").rstrip("."),center),"","",p("Rs. "+fmt(total),right)],
        ["","","","","","",""],
    ]
    heights=[item_header_height] + [item_row_height]*item_count + [tax_block_height,total_height,separator_height]
    table=Table(rows,colWidths=[10*mm,86*mm,19*mm,18*mm,19*mm,8*mm,32*mm],rowHeights=heights)
    tax_block_row = 1 + len(items)
    total_row = tax_block_row + 1
    separator_row = total_row + 1
    table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.55,colors.black),("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("VALIGN",(0,tax_block_row),(-1,tax_block_row),"BOTTOM"),
        ("SPAN",(1,tax_block_row),(5,tax_block_row)),
        ("SPAN",(0,total_row),(1,total_row)),
        # Full-width blank separator immediately below Total.
        ("SPAN",(0,separator_row),(-1,separator_row)),
    ]))
    story.append(table)

    amount_words_para = Paragraph(
        "Amount Chargeable (in words)<br/><b>" + amount_words(total) + "</b>",
        normal,
    )
    words=Table([[amount_words_para,p("E. & O.E",right)]],colWidths=[166*mm,26*mm])
    words.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.55,colors.black),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
        ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2)
    ]))
    story.append(words)

    # HSN summary grouped by code. Match the original grouped header layout.
    grouped={}
    for item in items:
        grouped[item["hsn"]]=grouped.get(item["hsn"],Decimal("0"))+dec(item["quantity"])*dec(item["rate"])
    tax_rows=[
        [p("HSN/SAC",center), p("Taxable Value",center), p("Central Tax",center), "", p("State Tax",center), "", p("Total Tax Amount",center)],
        ["", "", p("Rate",center), p("Amount",center), p("Rate",center), p("Amount",center), ""],
    ]
    for hsn,taxable in grouped.items():
        c=dec(taxable*CGST_RATE/100); s=dec(taxable*SGST_RATE/100)
        tax_rows.append([p(hsn,center),p(fmt_plain(taxable),center),p("9%",center),p(fmt_plain(c),center),p("9%",center),p(fmt_plain(s),center),p(fmt_plain(c+s),center)])
    tax_rows.append([p("Total",center),p(fmt_plain(subtotal),center),"",p(fmt_plain(cgst),center),"",p(fmt_plain(sgst),center),p(fmt_plain(cgst+sgst),center)])
    # Full 192 mm width so the HSN summary aligns with the invoice table.
    if very_compact:
        tax_header_h, tax_data_h, tax_total_h = 4*mm, 4.5*mm, 4.5*mm
    elif compact:
        tax_header_h, tax_data_h, tax_total_h = 4.5*mm, 5*mm, 5*mm
    else:
        tax_header_h, tax_data_h, tax_total_h = 5.5*mm, 7*mm, 7*mm
    tax=Table(
        tax_rows,
        colWidths=[40*mm,28*mm,16*mm,24*mm,16*mm,24*mm,44*mm],
        rowHeights=[tax_header_h,tax_header_h]+[tax_data_h]*len(grouped)+[tax_total_h]
    )
    tax.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.55,colors.black),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),2),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),1),("BOTTOMPADDING",(0,0),(-1,-1),1),
        ("SPAN",(0,0),(0,1)), ("SPAN",(1,0),(1,1)), ("SPAN",(2,0),(3,0)),
        ("SPAN",(4,0),(5,0)), ("SPAN",(6,0),(6,1)),
    ]))
    story.append(tax)

    tax_words=amount_words(cgst+sgst).replace("INR ","",1)
    tax_words_box=Paragraph(
        "Tax Amount (in words):<br/><br/><b>"+tax_words+"</b>", normal)
    declaration=Paragraph(
        "<u>Declaration</u><br/>We declare that this invoice shows the actual price of the goods "
        "described and that all particulars are true and correct.", normal)
    right_box=Paragraph(
        "<b>for GraceFurnitures-2026-27</b><br/><br/><br/>Authorised Signatory", right)

    # Exact lower layout requested:
    # - tax amount in words occupies the full-width upper area;
    # - declaration below is open at the top;
    # - signatory box begins lower and is fully closed.
    if very_compact:
        footer_heights = [10*mm,14*mm]
    elif compact:
        footer_heights = [11*mm,16*mm]
    else:
        footer_heights = [15*mm,20*mm]
    footer=Table(
        [[tax_words_box, ""], [declaration, right_box]],
        colWidths=[96*mm,96*mm],
        rowHeights=footer_heights,
    )
    footer.setStyle(TableStyle([
        ("SPAN",(0,0),(1,0)),
        # Upper tax-words area: side borders only; no lower divider.
        ("LINEBEFORE",(0,0),(0,0),0.55,colors.black),
        ("LINEAFTER",(1,0),(1,0),0.55,colors.black),
        # Declaration: open at the top, closed on left, right, and bottom.
        ("LINEBEFORE",(0,1),(0,1),0.55,colors.black),
        ("LINEAFTER",(0,1),(0,1),0.55,colors.black),
        ("LINEBELOW",(0,1),(0,1),0.55,colors.black),
        # Signatory box begins only at the declaration level and is fully closed.
        ("BOX",(1,1),(1,1),0.55,colors.black),
        # Match the earlier layout: tax words and declaration start near the top,
        # while the authorised-signatory text remains anchored toward the bottom.
        ("VALIGN",(0,0),(1,0),"TOP"),
        ("VALIGN",(0,1),(0,1),"TOP"),
        ("VALIGN",(1,1),(1,1),"BOTTOM"),
        ("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
        ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(footer)
    story.append(Spacer(1,0.1*mm if compact else 0.2*mm))
    story.append(Paragraph(COMPANY["jurisdiction"],center))
    story.append(Paragraph("This is a Computer Generated Invoice",center))
    doc.build(story)
    buffer.seek(0)
    return buffer


@app.route("/invoice/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id):
    con = db()
    invoice = con.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
    items = con.execute("SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY line_no", (invoice_id,)).fetchall()
    con.close()
    if not invoice:
        return "Invoice not found", 404
    pdf = make_pdf(invoice, items)
    filename = f"Invoice_{invoice['invoice_no']}_{invoice['vehicle_no']}.pdf"
    return send_file(pdf, mimetype="application/pdf", as_attachment=True, download_name=filename)


@app.route("/products", methods=["GET", "POST"])
@login_required
def products():
    con = db()
    if request.method == "POST":
        name=request.form.get("name","").strip()
        hsn=request.form.get("hsn",DEFAULT_HSN).strip() or DEFAULT_HSN
        rate=request.form.get("default_rate","").strip()
        if name:
            con.execute(
                "INSERT INTO products(name,hsn,default_rate) VALUES (?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET hsn=excluded.hsn, default_rate=excluded.default_rate",
                (name,hsn,float(rate) if rate else None),
            )
            con.commit()
            flash("Product master updated.","success")
    rows=con.execute("SELECT * FROM products ORDER BY name").fetchall()
    con.close()
    return render_template("products.html",products=rows)


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current=request.form.get("current_password","")
        new=request.form.get("new_password","")
        confirm=request.form.get("confirm_password","")
        con=db(); user=con.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone()
        if not check_password_hash(user["password_hash"],current):
            flash("Current password is incorrect.","danger")
        elif len(new)<8:
            flash("New password must contain at least 8 characters.","danger")
        elif new!=confirm:
            flash("New password and confirmation do not match.","danger")
        else:
            con.execute("UPDATE users SET password_hash=? WHERE id=?",(generate_password_hash(new),session["user_id"]))
            con.commit(); flash("Password changed.","success")
        con.close()
    return render_template("change_password.html")


@app.template_filter("money")
def money_filter(v):
    return fmt(v)


@app.template_filter("money_plain")
def money_plain_filter(v):
    return fmt_plain(v)


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5050)), debug=os.environ.get("FLASK_DEBUG")=="1")
