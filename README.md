# Grace Furnitures Web Invoice Application

Responsive Flask application for creating, editing, saving, and downloading Grace Furnitures tax invoices from a phone or computer.

## Features

- Password login
- Mobile-responsive HTML interface
- Automatic invoice numbering
- Editable saved invoices
- Consignee and buyer entry
- Multiple invoice items
- Automatic HSN from Product-HSN Master
- Unknown products default to HSN `940350`
- Product name, HSN, and latest rate are saved for reuse
- CGST 9%, SGST 9%, totals, amount in words, and HSN tax summary
- One-page A4 PDF for normal invoice sizes
- Closed authorised-signatory box
- No visible HTML tags in the generated PDF

## Local test

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5050`.

Default local login:

- Username: `admin`
- Password: `Grace@2026`

Change the password after first login.

## Use it from a phone at any time

The application must be deployed to an internet hosting service. A local HTML file alone cannot provide secure login, permanent invoice storage, or access from different devices.

### Recommended simple option: PythonAnywhere

1. Create a PythonAnywhere account.
2. Upload this folder as a ZIP and extract it.
3. Create a virtual environment and install `requirements.txt`.
4. Create a new Flask web app and set the WSGI file to import `app` from this folder.
5. Set a secure `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD`.
6. Reload the web app.
7. Open the PythonAnywhere URL on the phone and add it to the home screen.

SQLite storage is persistent on PythonAnywhere, which suits a small single-user invoice application.

### Render deployment

A `render.yaml` and `Procfile` are included. Render requires persistent storage for SQLite, or an external PostgreSQL database. Do not rely on an ephemeral filesystem for permanent invoice records.

## Security before public deployment

Set these environment variables:

```text
SECRET_KEY=<long-random-value>
ADMIN_USERNAME=<your-login-name>
ADMIN_PASSWORD=<strong-password>
```

The application hashes passwords. It does not store them as plain text.

## HSN behaviour

- Existing product: HSN is inserted from Product-HSN Master.
- New product: HSN defaults to `940350`.
- After saving an invoice, the product, HSN, and rate are stored for future invoices.
- Product-HSN Master can be used to correct or predefine codes.

Review HSN classifications with your accountant because HSN depends on furniture type and material.


## Invoice format refinements

- Only the `for GraceFurnitures-2026-27 / Authorised Signatory` area has a closed box.
- The declaration and tax-amount-in-words area on the left has no border.
- Unnecessary internal borders in the amount-in-words row were removed.
- Item values, taxable values and tax values are printed without thousands commas, matching the original invoice.
- The grand total retains the thousands comma, matching the original invoice.
- PDF dates are displayed as `17-Jul-2026`.


## Invoice number

Invoice numbers are auto-populated using the next available number. The field remains editable before saving and when reopening a saved invoice. Duplicate invoice numbers are not permitted.


## Saved vehicle numbers
Vehicle numbers appear in a reusable dropdown. Any new vehicle number entered in an invoice is saved automatically for future invoices.


## Supplier address

No.27, Sai Baba Street, Sandhosh Nagar, Palavakkam, Chennai, Tamil Nadu - 600041.


## Version 16 product-entry correction

- A visible Saved Product dropdown is included for every invoice item.
- Selecting a saved product fills Description, HSN/SAC, and Rate.
- Selecting a different product replaces the previous rate instead of retaining it.
- A new product can be entered through Manual / New Product.
- New product description, HSN, and rate are saved when the invoice is saved.


## Version 17 product-master change

The following preloaded products were removed:

- Dining Table
- Kitchen Furniture
- Metal Office Furniture
- Office Table
- Pooja Unit
- Sofa
- Wooden Bed
- Wooden Chair
- Wooden Cot
- Wooden Wardrobe


## Version 18 one-page PDF change

- The PDF now adjusts vertical spacing according to the number of invoice items.
- Invoices with 6-8 items use a compact one-page layout.
- The large blank goods area is reduced before font sizes are reduced.
- Header, HSN summary, and footer heights are compressed only when needed.
- The approved border structure and column widths are retained.

## GitHub Codespaces

This version is ready for GitHub Codespaces. After uploading the repository, choose **Code → Codespaces → Create codespace on main**, then run:

```bash
./start_codespaces.sh
```

Open forwarded port **5050**. See `CODESPACES.md` for iPad/iPhone instructions and data-persistence notes.
