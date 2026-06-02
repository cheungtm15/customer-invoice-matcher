import streamlit as st
import pandas as pd
import csv
import difflib

# --- STREAMLIT USER INTERFACE ---
st.set_page_config(page_title="Invoice Matcher", page_icon="⚖️", layout="wide")
st.title("⚖️ Customer Total & Item Matcher")
st.write("Upload your Daily Reckon CSV and your Sales Order Report CSV. The app will pair up customer names, find any mismatched totals, and tell you EXACTLY which items are missing.")

col1, col2 = st.columns(2)
with col1:
    reckon_file = st.file_uploader("1. Upload 'Daily Reckon.csv'", type=['csv'])
with col2:
    sales_file = st.file_uploader("2. Upload 'Sales Order Report.csv'", type=['csv'])

if reckon_file and sales_file:
    if st.button("Run Comparison & Item Check", type="primary"):
        with st.spinner("Cross-referencing totals and line items..."):
            
            # --- CUSTOM ALIAS DICTIONARY ---
            aliases = {
                "la petite maison": "lpm",
                "ji ja": "jija 吱喳小館",
                "crowne plaza hong kong": "crowne plaza",
                "bourke's": "bourke’s (ex shady acres)",
                "dalloyau bistro(tsuen wan)": "dalloyau division  (food lab)",
                "foreign corresp. club 外國記者會": "foreign correspondents' club hong kong",
                "chuang, karen": "chuang, karen  莊太- (nina chung)",
                "jep by involtini": "half by involtini - tuen mun",
                "anna hui": "hui, anna",
                "yu, tim (arcane)": "tim yu - arcane",
                "que": "que - pok fu lam",
                "park lane hong kong柏寧酒店": "park lane hotel",
                "ng, nikki": "ng mien hua (ng nikki) ",
                "milo (eric kayser)": "milo - eric kayser artisan boulanger",
                "justin (te bo)": "justin - tong chong kitchen - te bo 2/f",
                "harbour grand hong kong": "harbour grand hong kong (north point)",
                "grazizno chef": "graziano de gregorio - estro"
            }

            # --- 1. EXTRACT DATA & ITEMS FROM DAILY RECKON ---
            reckon_totals = {}
            reckon_items = {}
            current_customer_items = []
            
            raw_bytes = reckon_file.getvalue()
            try:
                content = raw_bytes.decode('utf-8').splitlines()
            except UnicodeDecodeError:
                try: content = raw_bytes.decode('utf-8-sig').splitlines()
                except UnicodeDecodeError:
                    try: content = raw_bytes.decode('big5').splitlines()
                    except UnicodeDecodeError: content = raw_bytes.decode('utf-8', errors='ignore').splitlines()
            
            reader = csv.reader(content)
            for row in reader:
                if not row: continue
                col0 = row[0].strip()
                
                if col0.startswith("Total ") and col0.upper() != "TOTAL":
                    customer_name = col0[6:].strip()
                    try:
                        amount = float(row[5].replace(',', ''))
                        reckon_totals[customer_name] = amount
                        reckon_items[customer_name] = current_customer_items
                    except: pass
                    current_customer_items = []
                elif col0.upper() == "TOTAL":
                    continue
                else:
                    # Look for line items (rows that have a monetary amount in the 6th column)
                    if len(row) > 5:
                        try:
                            amt = float(row[5].replace(',', ''))
                            # Get the description, fallback to Item code if description is blank
                            desc = row[1].strip() if row[1].strip() else (row[2].strip() if len(row)>2 else "Discount/Other")
                            current_customer_items.append({"desc": desc, "amount": amt})
                        except: pass

            # --- 2. EXTRACT DATA & ITEMS FROM SALES REPORT ---
            sales_df = pd.read_csv(sales_file)
            amount_col = [c for c in sales_df.columns if 'Amount' in c]
            name_col = [c for c in sales_df.columns if 'Customer Name' in c]
            # Try to find the product description column
            product_col_search = [c for c in sales_df.columns if 'Product' in c or 'Material' in c]
            product_col = product_col_search[0] if product_col_search else sales_df.columns[1]
            
            if amount_col and name_col:
                cleaned_amounts = sales_df[amount_col[0]].astype(str).str.replace(',', '', regex=False)
                sales_df[amount_col[0]] = pd.to_numeric(cleaned_amounts, errors='coerce').fillna(0.0)
                sales_totals_series = sales_df.groupby(name_col[0])[amount_col[0]].sum()
                sales_totals = sales_totals_series.to_dict()
            else:
                st.error("Error: Could not find 'Customer Name' or 'Amount' columns in the Sales Report.")
                st.stop()

            # --- 3. MATCH CUSTOMERS & FIND MISSING ITEMS ---
            results = []
            breakdown_results = []
            sales_keys_lower = {str(k).lower(): k for k in sales_totals.keys()}
            used_sales_keys = set()

            for r_name, r_amount in reckon_totals.items():
                s_name = None
                r_name_lower = str(r_name).lower()
                
                if r_name_lower in aliases:
                    target_lower = aliases[r_name_lower]
                    if target_lower in sales_keys_lower: s_name = sales_keys_lower[target_lower]

                if not s_name and r_name_lower in sales_keys_lower:
                    s_name = sales_keys_lower[r_name_lower]
                
                if not s_name:
                    match = difflib.get_close_matches(r_name_lower, list(sales_keys_lower.keys()), n=1, cutoff=0.65)
                    if match: s_name = sales_keys_lower[match[0]]
                        
                if not s_name:
                    for s_key in sales_keys_lower.keys():
                        if len(r_name_lower) > 2 and (r_name_lower in s_key or s_key in r_name_lower):
                            s_name = sales_keys_lower[s_key]
                            break
                            
                if not s_name: s_name = "No Match Found"

                if s_name != "No Match Found":
                    used_sales_keys.add(s_name)
                    s_amount = sales_totals[s_name]
                else:
                    s_amount = 0.0

                diff = round(r_amount - s_amount, 2)
                
                results.append({
                    "Reckon Customer": r_name,
                    "Reckon Total": f"${r_amount:,.2f}",
                    "Sales Customer": s_name,
                    "Sales Total": f"${s_amount:,.2f}",
                    "Difference": f"${diff:,.2f}",
                    "Status": "✅ Match" if abs(diff) < 0.01 else "⚠️ MISMATCH"
                })

                # --- ITEM CHECKER LOGIC ---
                if abs(diff) >= 0.01:
                    r_list = reckon_items.get(r_name, [])
                    if s_name != "No Match Found":
                        s_items_df = sales_df[sales_df[name_col[0]] == s_name]
                        s_list = [{"desc": row[product_col], "amount": row[amount_col[0]]} for _, row in s_items_df.iterrows()]
                    else:
                        s_list = []
                    
                    temp_s_list = s_list.copy()
                    unmatched_r = []
                    
                    # Try to pair items with the exact same amount
                    for r_item in r_list:
                        matched = False
                        for s_item in temp_s_list:
                            if abs(r_item["amount"] - s_item["amount"]) < 0.05:
                                temp_s_list.remove(s_item)
                                matched = True
                                break
                        if not matched:
                            unmatched_r.append(r_item)
                    
                    unmatched_s = temp_s_list # Whatever is left in Sales wasn't in Reckon
                    
                    for item in unmatched_r:
                        breakdown_results.append({
                            "Customer": r_name,
                            "Issue Type": "Missing from Sales (or Wrong Price)",
                            "Item Description": item["desc"],
                            "Amount Discrepancy": item["amount"]
                        })
                    for item in unmatched_s:
                        breakdown_results.append({
                            "Customer": s_name,
                            "Issue Type": "Extra in Sales (Not in Reckon)",
                            "Item Description": item["desc"],
                            "Amount Discrepancy": item["amount"]
                        })

            # Add customers that were in Sales but completely missing from Reckon
            for s_name, s_amount in sales_totals.items():
                if s_name not in used_sales_keys and s_amount > 0:
                    results.append({
                        "Reckon Customer": "Not found in Reckon",
                        "Reckon Total": "$0.00",
                        "Sales Customer": s_name,
                        "Sales Total": f"${s_amount:,.2f}",
                        "Difference": f"${-s_amount:,.2f}",
                        "Status": "⚠️ MISMATCH"
                    })
                    # Add to item breakdown
                    s_items_df = sales_df[sales_df[name_col[0]] == s_name]
                    for _, row in s_items_df.iterrows():
                        breakdown_results.append({
                            "Customer": s_name,
                            "Issue Type": "Ghost Order (Customer Missing from Reckon)",
                            "Item Description": row[product_col],
                            "Amount Discrepancy": row[amount_col[0]]
                        })

            # --- 4. SHOW RESULTS ---
            results_df = pd.DataFrame(results)
            breakdown_df = pd.DataFrame(breakdown_results)
            
            st.success("Comparison & Item Check Complete!")
            
            # Create interactive tabs to organize the data on the screen
            tab1, tab2 = st.tabs(["📊 Customer Totals (Discrepancy Report)", "🔍 Itemized Breakdown (The Missing Items)"])
            
            with tab1:
                st.dataframe(results_df, use_container_width=True)
                csv_main = results_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("⬇️ Download Discrepancy Report", data=csv_main, file_name="Discrepancy_Report.csv", mime="text/csv")
                
            with tab2:
                if not breakdown_df.empty:
                    # Format the amount column cleanly
                    breakdown_df['Amount Discrepancy'] = breakdown_df['Amount Discrepancy'].apply(lambda x: f"${x:,.2f}")
                    st.dataframe(breakdown_df, use_container_width=True)
                    csv_items = breakdown_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("⬇️ Download Itemized Breakdown", data=csv_items, file_name="Itemized_Breakdown.csv", mime="text/csv")
                else:
                    st.write("🎉 No mismatched items found!")
