import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from fpdf import FPDF
import io
from datetime import date

# ================== SUNLY HOME BRANDING + FORCED WHITE BACKGROUND ==================
st.set_page_config(page_title="Historical and Projected Electricity Cost", layout="centered", initial_sidebar_state="collapsed")

# FORCE WHITE/LIGHT THEME (fixes logo blending + removes dark mode)
st.markdown("""
    <style>
        [data-testid="stAppViewContainer"] { background-color: #ffffff !important; }
        [data-testid="stHeader"] { background-color: #ffffff !important; }
        [data-testid="stSidebar"] { background-color: #ffffff !important; }
        .stApp { background-color: #ffffff !important; color: #000000 !important; }
        .stMarkdown, .st-emotion-cache-1y4p8pa, p, h1, h2, h3, label { color: #000000 !important; }
        .stButton > button { background-color: #0066CC !important; color: white !important; }
    </style>
""", unsafe_allow_html=True)

# Display Sunly Home logo (perfect on white background)
st.image("sunly-logo.png", width=380)

st.title("Historical and Projected Electricity Cost")
st.markdown("**Real EIA data • 10 years back + 10 years forward • Powered by Sunly Home**")

address = st.text_input("Prospect's Address (street, city, state)", value="2701 Southwood Dr, Champaign, IL 61821")
utility = st.text_input("Utility Company (e.g. Oncor, TXU, CenterPoint)", value="Ameren")
avg_bill = st.number_input("Average Monthly Electric Bill ($)", min_value=10.0, value=170.0, step=5.0)

EIA_API_KEY = st.secrets["api"]["EIA_API_KEY"]

if st.button("🚀 Generate 20-Year Forecast Report", type="primary"):
    with st.spinner("Fetching real EIA data and building your report..."):
        geolocator = Nominatim(user_agent="solar_consultant_tool")
        state = "IL"
        try:
            loc = geolocator.geocode(address, timeout=10)
            if loc and 'address' in loc.raw:
                state_code = loc.raw['address'].get('ISO3166-2-lvl4', '').split('-')[-1]
                if len(state_code) == 2:
                    state = state_code
        except:
            pass

        today = date.today()
        start_date = f"{today.year - 10}-01-01"
        end_date = today.strftime("%Y-%m-%d")

        url = (
            f"https://api.eia.gov/v2/electricity/retail-sales/data/"
            f"?api_key={EIA_API_KEY}"
            f"&data[]=price"
            f"&facets[stateid][]={state}"
            f"&facets[sectorid][]=RES"
            f"&frequency=monthly"
            f"&start={start_date}"
            f"&end={end_date}"
            f"&sort[0][column]=period"
            f"&sort[0][direction]=desc"
        )

        try:
            response = requests.get(url, timeout=15)
            data = response.json()

            if response.status_code != 200 or 'error' in data or not data.get('response', {}).get('data'):
                st.error("Could not fetch data right now. Try again in a minute.")
            else:
                df = pd.DataFrame(data['response']['data'])
                df['period'] = pd.to_datetime(df['period'])
                df = df.sort_values('period')
                df['price'] = pd.to_numeric(df['price']) / 100
                df['year'] = df['period'].dt.year
                annual = df.groupby('year')['price'].mean().reset_index()
                
                current_price = annual['price'].iloc[-1]
                usage_kwh = avg_bill / current_price
                
                avg_annual_increase = annual['price'].pct_change().mean() + 1 if len(annual) > 1 else 1.03
                last_year = annual['year'].max()
                future_years = list(range(last_year + 1, last_year + 11))
                future_prices = [current_price * (avg_annual_increase ** i) for i in range(1, 11)]
                
                proj_df = pd.DataFrame({'year': future_years, 'price': future_prices})
                
                full_df = pd.concat([annual, proj_df], ignore_index=True)
                full_df['type'] = ['Historical'] * len(annual) + ['Projected'] * len(proj_df)
                full_df['monthly_cost'] = full_df['price'] * usage_kwh
                full_df['pct_change'] = full_df['price'].pct_change() * 100
                full_df['pct_change'] = full_df['pct_change'].round(1)

                # Charts
                col1, col2 = st.columns(2)
                with col1:
                    fig_price = px.line(full_df, x='year', y='price', color='type', title="Electricity Price Trend ($ per kWh)")
                    st.plotly_chart(fig_price, use_container_width=True)
                with col2:
                    fig_cost = px.line(full_df, x='year', y='monthly_cost', color='type', title="Your Projected Monthly Bill ($)")
                    st.plotly_chart(fig_cost, use_container_width=True)
                
                st.success(f"✅ Report ready for {utility} in {state}")
                st.write(f"**Current price:** ${current_price:.3f} per kWh")
                st.write(f"**Your estimated monthly usage:** {usage_kwh:.0f} kWh")
                st.write(f"**Avg annual increase:** {(avg_annual_increase-1)*100:.1f}%")

                # ================== PDF (safe encoding - no errors) ==================
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(0, 10, "YOUR 20-YEAR ELECTRICITY COST FORECAST", ln=1, align='C')
                pdf.set_font("Arial", size=12)
                pdf.ln(5)
                pdf.cell(0, 8, f"Prepared by Sunly Home - {date.today().strftime('%B %d, %Y')}", ln=1)
                pdf.cell(0, 8, f"Address: {address} | Utility: {utility} | State: {state}", ln=1)
                pdf.cell(0, 8, f"Average Monthly Bill Today: ${avg_bill:.2f}", ln=1)
                pdf.ln(10)

                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 8, "The truth most homeowners never see:", ln=1)
                pdf.set_font("Arial", size=11)
                pdf.multi_cell(0, 8, "Most people hope rates won't go up. You asked for the numbers. Here they are - based on real EIA data and proven trends. This is exactly how much you will pay if you do nothing.")
                pdf.ln(5)

                pdf.set_font("Arial", 'B', 11)
                pdf.cell(0, 8, "Year | Price ($/kWh) | Monthly Cost ($) | YoY Change (%)", ln=1)
                pdf.set_font("Arial", size=10)
                for _, row in full_df.iterrows():
                    pct_str = "N/A" if pd.isna(row['pct_change']) else f"{row['pct_change']:.1f}%"
                    pdf.cell(0, 8, f"{int(row['year'])} | ${row['price']:.3f} | ${row['monthly_cost']:.2f} | {pct_str}", ln=1)

                current_cost = full_df[full_df['type'] == 'Historical'].iloc[-1]['monthly_cost']
                ten_year_cost = full_df.iloc[-11]['monthly_cost']
                twenty_year_cost = full_df.iloc[-1]['monthly_cost']
                ten_year_rise = ((ten_year_cost / current_cost) - 1) * 100
                twenty_year_rise = ((twenty_year_cost / current_cost) - 1) * 100

                pdf.ln(10)
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 8, "SUMMARY - THE REAL COST OF DOING NOTHING", ln=1)
                pdf.set_font("Arial", size=11)
                pdf.cell(0, 8, f"Next 10 years: Your bill will rise {ten_year_rise:.1f}% -> ${ten_year_cost:.2f}/month", ln=1)
                pdf.cell(0, 8, f"Full 20 years: Cumulative increase of {twenty_year_rise:.1f}% -> ${twenty_year_cost:.2f}/month", ln=1)
                pdf.ln(5)
                pdf.multi_cell(0, 8, "That extra money is a college fund, a rental property down payment, or retirement savings - right now its going to the utility monopoly.")
                pdf.ln(10)

                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 8, "Ready to stop the bleeding and power your home effortlessly?", ln=1)
                pdf.set_font("Arial", size=11)
                pdf.multi_cell(0, 8, "You now have the 20-year forecast. Lets build your exit strategy with Sunly Home. I have an assessment specialist ready to model the highest-performing solar + battery option for your home. If the math doesnt win, you dont switch. Simple as that.")

                pdf_output = io.BytesIO(pdf.output(dest='S').encode('latin-1', errors='replace'))
                st.download_button(
                    label="📥 Download Professional PDF Report",
                    data=pdf_output,
                    file_name=f"Sunly_Home_20_Year_Forecast_{utility.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
        except Exception as e:
            st.error("Something unexpected happened.")
            st.caption(f"Technical detail: {str(e)}")
