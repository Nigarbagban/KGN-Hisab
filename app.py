from datetime import datetime
import io
import os
import sqlite3
import urllib.parse
import pandas as pd
import streamlit as st

# ReportLab imports for PDF Generation
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Page Configuration
st.set_page_config(
    page_title="KGN Business Suite", page_icon="📊", layout="wide"
)


# Database Initialization
def init_db():
  conn = sqlite3.connect("kgn_business.db", check_same_thread=False)
  cursor = conn.cursor()

  # Settings Table for Shop Info
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_name TEXT,
            address TEXT,
            mobile TEXT
        )
    """)
  cursor.execute("SELECT COUNT(*) FROM settings")
  if cursor.fetchone()[0] == 0:
    cursor.execute(
        "INSERT INTO settings (shop_name, address, mobile) VALUES (?, ?, ?)",
        ("KGN ENTERPRISES", "Malegaon, Maharashtra", "9876543210"),
    )

  # Transactions Table
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            party_name TEXT,
            category TEXT,
            item_name TEXT,
            qty REAL,
            amount REAL,
            discount REAL,
            tax REAL,
            note TEXT
        )
    """)

  # Stock Table
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT UNIQUE,
            quantity REAL,
            price REAL
        )
    """)
  conn.commit()
  conn.close()


init_db()


def run_query(query, params=(), fetch=True):
  conn = sqlite3.connect("kgn_business.db", check_same_thread=False)
  cursor = conn.cursor()
  cursor.execute(query, params)
  if fetch:
    res = cursor.fetchall()
    conn.close()
    return res
  conn.commit()
  conn.close()


# Get Shop Profile Info
shop_info = run_query("SELECT shop_name, address, mobile FROM settings LIMIT 1")[
    0
]
shop_name, shop_addr, shop_mob = shop_info

# App Header
st.title(f"🏢 {shop_name}")
st.subheader("KGN Business Suite: Ledger, Stock & WhatsApp Reports")
st.markdown(f"📍 **Address:** {shop_addr} | 📞 **Mobile:** {shop_mob}")
st.markdown("---")

# Sidebar Navigation Tabs
menu = st.sidebar.selectbox(
    "Navigation Menu",
    [
        "📝 Transactions & Invoicing",
        "📦 Stock Inventory",
        "📊 Reports & Analytics",
        "📱 Partner WhatsApp Report",
        "⚙️ Shop Profile Settings",
    ],
)

# ---------------- 1. TRANSACTIONS & INVOICING ----------------
if menu == "📝 Transactions & Invoicing":
  st.header("📝 New Transaction & Sale Entry")

  with st.form("txn_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
      t_date = st.date_input("Date", datetime.today())
      t_name = st.text_input("Party / Customer Name")
      t_cat = st.selectbox(
          "Category",
          [
              "Sale (Bikri)",
              "Purchase (Khareed)",
              "Daily Expense",
              "Return Maal",
              "Truck Bhada",
              "Shop Rent",
              "Other",
          ],
      )
      t_item = st.text_input(
          "Item Name (Optional for Stock Update)", placeholder="e.g. Tyres / Scrap"
      )
    with col2:
      t_qty = st.number_input("Quantity", min_value=0.0, value=1.0)
      t_amt = st.number_input("Amount (₹)", min_value=0.0, value=0.0)
      t_disc = st.number_input("Discount (₹)", min_value=0.0, value=0.0)
      t_tax = st.number_input("Tax / GST (₹)", min_value=0.0, value=0.0)

    t_note = st.text_area("Note / Description")
    submit = st.form_submit_button("Save Transaction")

    if submit:
      if not t_name or t_amt == 0:
        st.error("Please enter Party Name and a valid Amount!")
      else:
        run_query(
            "INSERT INTO transactions (date, party_name, category, item_name,"
            " qty, amount, discount, tax, note) VALUES (?, ?, ?, ?, ?, ?, ?,"
            " ?, ?)",
            (
                str(t_date),
                t_name,
                t_cat,
                t_item,
                t_qty,
                t_amt,
                t_disc,
                t_tax,
                t_note,
            ),
            fetch=False,
        )

        # Update Stock if item is provided
        if t_item.strip() and t_qty > 0:
          existing = run_query(
              "SELECT quantity FROM stock WHERE item_name = ?", (t_item,)
          )
          if existing:
            curr_qty = existing[0][0]
            new_qty = (
                curr_qty - t_qty
                if "Sale" in t_cat
                else curr_qty + t_qty
            )
            run_query(
                "UPDATE stock SET quantity = ? WHERE item_name = ?",
                (new_qty, t_item),
                fetch=False,
            )
          elif "Purchase" in t_cat:
            run_query(
                "INSERT INTO stock (item_name, quantity, price) VALUES (?, ?,"
                " ?)",
                (t_item, t_qty, t_amt / t_qty if t_qty > 0 else 0),
                fetch=False,
            )

        st.success("Transaction saved successfully & Stock updated!")

  st.markdown("---")
  st.subheader("📋 Recent Transactions Ledger")
  rows = run_query("SELECT * FROM transactions ORDER BY id DESC")
  if rows:
    df = pd.DataFrame(
        rows,
        columns=[
            "ID",
            "Date",
            "Party",
            "Category",
            "Item",
            "Qty",
            "Amount",
            "Discount",
            "Tax",
            "Note",
        ],
    )
    st.dataframe(df, use_container_width=True)

    # Net Balance Calculation
    net_bal = 0
    for r in rows:
      final_amt = r[6] - r[7] + r[8]
      if "Sale" in r[3]:
        net_bal += final_amt
      else:
        net_bal -= final_amt
    st.metric(label="Net Balance (Inflow - Outflow)", value=f"₹{net_bal:.2f}")

    # Delete Option
    del_id = st.number_input(
        "Enter Transaction ID to Delete", min_value=1, step=1
    )
    if st.button("Delete Transaction"):
      run_query("DELETE FROM transactions WHERE id = ?", (del_id,), fetch=False)
      st.warning(f"Transaction ID {del_id} deleted!")
      st.rerun()
  else:
    st.info("No transactions found.")

# ---------------- 2. STOCK INVENTORY ----------------
elif menu == "📦 Stock Inventory":
  st.header("📦 KGN Stock Inventory Management")

  with st.form("stock_form"):
    c1, c2, c3 = st.columns(3)
    s_name = c1.text_input("Item Name")
    s_qty = c2.number_input("Available Quantity", min_value=0.0)
    s_price = c3.number_input("Unit Price (₹)", min_value=0.0)
    s_submit = st.form_submit_button("Save / Update Stock")

    if s_submit:
      if s_name:
        run_query(
            "INSERT OR REPLACE INTO stock (id, item_name, quantity, price)"
            " VALUES ((SELECT id FROM stock WHERE item_name = ?), ?, ?, ?)",
            (s_name, s_name, s_qty, s_price),
            fetch=False,
        )
        st.success(f"Stock for '{s_name}' updated successfully!")
        st.rerun()
      else:
        st.error("Please enter an item name.")

  st.subheader("Current Stock Items")
  stock_rows = run_query("SELECT * FROM stock")
  if stock_rows:
    df_stock = pd.DataFrame(
        stock_rows, columns=["ID", "Item Name", "Quantity", "Price"]
    )
    st.dataframe(df_stock, use_container_width=True)
  else:
    st.info("Stock inventory is currently empty.")

# ---------------- 3. REPORTS & PDF EXPORT ----------------
elif menu == "📊 Reports & Analytics":
  st.header("📊 Reports & PDF Generation")

  st.markdown(
      "Download professional PDF records for your daily or monthly ledger."
  )


  def generate_pdf_report(title, data_rows):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, shop_name)
    c.setFont("Helvetica", 10)
    c.drawString(
        50, height - 68, f"{title} | Address: {shop_addr} | Mobile: {shop_mob}"
    )
    c.line(50, height - 78, width - 50, height - 78)

    y = height - 120
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Date")
    c.drawString(130, y, "Party")
    c.drawString(260, y, "Category")
    c.drawString(380, y, "Item")
    c.drawString(460, y, "Amount (₹)")
    y -= 15
    c.line(50, y + 5, width - 50, y + 5)

    c.setFont("Helvetica", 9)
    total_in = 0
    total_out = 0

    for r in data_rows:
      if y < 80:
        c.showPage()
        y = height - 50
      c.drawString(50, y, str(r[1]))
      c.drawString(130, y, str(r[2])[:18])
      c.drawString(260, y, str(r[3])[:16])
      c.drawString(380, y, str(r[4])[:12] if r[4] else "-")
      c.drawString(460, y, f"₹{r[6]}")

      if "Sale" in r[3]:
        total_in += r[6]
      else:
        total_out += r[6]
      y -= 20

    y -= 10
    c.line(50, y, width - 50, y)
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, f"Total Inflow (Sales): ₹{total_in}")
    c.drawString(300, y, f"Total Outflow (Expenses): ₹{total_out}")

    c.save()
    buffer.seek(0)
    return buffer


  all_data = run_query("SELECT * FROM transactions")
  if all_data:
    pdf_file = generate_pdf_report("KGN Complete Business Ledger Report", all_data)
    st.download_button(
        label="📥 Download Ledger Report (PDF)",
        data=pdf_file,
        file_name="KGN_Business_Report.pdf",
        mime="application/pdf",
    )
  else:
    st.info("No records available to generate PDF.")

# ---------------- 4. PARTNER WHATSAPP REPORT ----------------
elif menu == "📱 Partner WhatsApp Report":
  st.header("📱 Send Daily Summary to Partners via WhatsApp")

  sales = run_query(
      "SELECT SUM(amount) FROM transactions WHERE category LIKE '%Sale%'"
  )
  total_sale = sales[0][0] if sales and sales[0][0] else 0.0

  outflows = run_query(
      "SELECT SUM(amount) FROM transactions WHERE category NOT LIKE '%Sale%'"
  )
  total_out = outflows[0][0] if outflows and outflows[0][0] else 0.0
  net_bal = total_sale - total_out

  stock_items = run_query("SELECT item_name, quantity FROM stock")
  stock_str = ""
  for s in stock_items:
    stock_str += f"- {s[0]}: {s[1]}\n"

  today = datetime.today().strftime("%d-%m-%Y")
  msg = (
      f"🏢 *{shop_name}* 🏢\n"
      f"📅 *Daily Report ({today})*\n\n"
      f"💰 *Total Sales:* ₹{total_sale}\n"
      f"💸 *Total Outflow/Expenses:* ₹{total_out}\n"
      f"📊 *Net Balance:* ₹{net_bal}\n\n"
      f"📦 *Stock Inventory:*\n{stock_str if stock_str else 'No stock listed'}\n"
      f"_Sent via KGN Business Suite_"
  )

  st.text_area("Generated WhatsApp Message Preview:", value=msg, height=200)

  encoded_msg = urllib.parse.quote(msg)
  whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_msg}"

  st.markdown(
      f"👉 [Click here to send Report to WhatsApp Group / Partners]({whatsapp_url})"
      " target='_blank'",
      unsafe_allow_html=True,
  )

# ---------------- 5. SHOP PROFILE SETTINGS ----------------
elif menu == "⚙️ Shop Profile Settings":
  st.header("⚙️ Shop Profile & Details")

  with st.form("profile_form"):
    new_name = st.text_input("Business Name", value=shop_name)
    new_addr = st.text_input("Address", value=shop_addr)
    new_mob = st.text_input("Mobile Number", value=shop_mob)
    save_prof = st.form_submit_button("Update Profile")

    if save_prof:
      run_query(
          "UPDATE settings SET shop_name = ?, address = ?, mobile = ?",
          (new_name, new_addr, new_mob),
          fetch=False,
      )
      st.success("Shop profile updated successfully!")
      st.rerun()
