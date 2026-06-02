import streamlit as st
import pandas as pd
import csv
import difflib

# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Invoice Matcher", page_icon="⚖️")
st.title("⚖️ Customer Total Matcher")
st.write("Upload your Daily Reckon CSV and your Sales Order Report CSV. The app will pair up customer names (even if they are spelled differently) and find any mismatched totals.")

# Create two columns for the file uploaders side-by-side
col1, col2 = st.columns(2)
with col1:
    reckon_file = st.file_uploader("1. Upload 'Daily Reckon.csv'", type=['csv'])
with col2:
    sales_file = st.file_uploader("2. Upload 'Sales Order Report.csv'", type=['csv'])

# Only run if both files are uploaded
if reckon_file and sales_file:
    if st.button("Run Comparison", type="primary"):
        with st.spinner("Crunching the numbers..."):
            
            # --- 1. EXTRACT DATA FROM DAILY RECKON ---
            reckon_totals = {}
            
            # Smart text decoding to handle Excel files and Chinese characters
            raw_bytes = reckon_file.getvalue()
            try:
                content = raw_bytes.decode('utf-8').splitlines()
            except UnicodeDecodeError:
                try:
                    content = raw_bytes.decode('utf-8-sig').splitlines() # Common in Excel exports
                except UnicodeDecodeError:
                    try:
                        content = raw_bytes.decode('big5').splitlines() # Common in Hong Kong systems
                    except UnicodeDecodeError:
                        # Fallback that ignores completely unreadable characters without crashing
                        content = raw_bytes.decode('utf-8', errors='ignore').splitlines()
            
            reader = csv.reader(content)
            
            for row in reader:
                if not row: 
                    continue
                first_col = row[0].strip()
                # Look for the rows that summarize the customer total
                if first_col.startswith("Total ") and first_col.upper() != "TOTAL":
                    customer_name = first_col[6:].strip() # Remove the word "Total "
                    try:
                        # Extract the amount (usually the 6th column, index 5)
                        amount = float(row[5].replace(',', ''))
                        reckon_totals[customer_name] = amount
                    except:
                        pass

            # --- 2. EXTRACT DATA FROM SALES REPORT ---
            sales_df = pd.read_csv(sales_file)
            
            # Look for the relevant column names in the sales report
            amount_col = [c for c in sales_df.columns if 'Amount' in c]
            name_col = [c for c in sales_df.columns if 'Customer Name' in c]
            
            if amount_col and name_col:
                # Clean the data: turn to text, erase commas, then convert to numbers safely
                cleaned_amounts = sales_df[amount_col[0]].astype(str).str.replace(',', '', regex=False)
                sales_df[amount_col[0]] = pd.to_numeric(cleaned_amounts, errors='coerce').fillna(0.0)
                
                # Group by customer and add up their totals
                sales_totals_series = sales_df.groupby(name_col[0])[amount_col[0]].sum()
                sales_totals = sales_totals_series.to_dict()
            else:
                st.error("Error: Could not find 'Customer Name' or 'Amount' columns in the Sales Report.")
                st.stop()

# --- 3. MATCH AND COMPARE ---
            results = []
            
            # Create a lowercase map for case-insensitive matching
            sales_keys_lower = {str(k).lower(): k for k in sales_totals.keys()}
            used_sales_keys = set()
            
            # --- CUSTOM ALIAS DICTIONARY ---
            # You can add known abbreviations here! (Format: "reckon name": "sales name")
            aliases = {
                "la petite maison": "lpm"
                "ji ja": "jija 吱喳小館"
            }

            for r_name, r_amount in reckon_totals.items():
                s_name = None
                r_name_lower = str(r_name).lower()
                
                # Check 1: Custom Alias Dictionary
                if r_name_lower in aliases:
                    target_lower = aliases[r_name_lower]
                    if target_lower in sales_keys_lower:
                        s_name = sales_keys_lower[target_lower]

                # Check 2: Exact Case-Insensitive Match
                if not s_name and r_name_lower in sales_keys_lower:
                    s_name = sales_keys_lower[r_name_lower]
                
                # Check 3: Fuzzy Match (Strictness raised to 65%)
                if not s_name:
                    match = difflib.get_close_matches(r_name_lower, list(sales_keys_lower.keys()), n=1, cutoff=0.65)
                    if match:
                        s_name = sales_keys_lower[match[0]]
                        
                # Check 4: Substring Match (e.g. "AMI" matches "AMI - Central")
                if not s_name:
                    for s_key in sales_keys_lower.keys():
                        if len(r_name_lower) > 2 and (r_name_lower in s_key or s_key in r_name_lower):
                            s_name = sales_keys_lower[s_key]
                            break
                            
                if not s_name:
                    s_name = "No Match Found"

                if s_name != "No Match Found":
                    used_sales_keys.add(s_name)
                    s_amount = sales_totals[s_name]
                else:
                    s_amount = 0.0

                diff = round(r_amount - s_amount, 2)
                
                results.append({
                    "Reckon Customer": r_name,
                    "Reckon Total": f"${r_amount:,.2f}",
                    "Sales Customer (Best Match)": s_name,
                    "Sales Total": f"${s_amount:,.2f}",
                    "Difference": f"${diff:,.2f}",
                    "Needs Review": "✅ Match" if diff == 0 else "⚠️ MISMATCH"
                })

            # Add any customers that were in the Sales Report but not in the Daily Reckon
            for s_name, s_amount in sales_totals.items():
                if s_name not in used_sales_keys and s_amount > 0:
                    results.append({
                        "Reckon Customer": "Not found in Reckon",
                        "Reckon Total": "$0.00",
                        "Sales Customer (Best Match)": s_name,
                        "Sales Total": f"${s_amount:,.2f}",
                        "Difference": f"${-s_amount:,.2f}",
                        "Needs Review": "⚠️ MISMATCH"
                    })

            # --- 4. SHOW RESULTS ---
            results_df = pd.DataFrame(results)
            st.success("Comparison Complete! Review the table below.")
            
            # Display the table on the web page
            st.dataframe(results_df, use_container_width=True)
            
            # Create a download button for the final report
            csv_data = results_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ Download Discrepancy Report (CSV)", 
                data=csv_data, 
                file_name="Discrepancy_Report.csv", 
                mime="text/csv"
            )
