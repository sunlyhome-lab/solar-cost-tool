import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from fpdf import FPDF
import io
from datetime import date

# ================== YOUR EIA API KEY ==================
EIA_API_KEY = "oZibXfcF83TebCxAcFdzMQMgWx582meQUK9Lt2Qa"
# =====================================================

st.set_page_config(page_title="Solar Cost Forecast", layout="centered")
st.title("🔌 Solar Consultant Electricity Cost Forecast Tool")
st.markdown("**Enter the prospect's details below to see 10 years of past prices + 10 years of projected future costs**")

address = st.text_input("Prospect's Address (street, city, state)", value="2701 Southwood Dr, Champaign, IL 61821")
utility = st.text_input("Utility Company (e.g. Oncor, TXU, CenterPoint)", value="Ameren")
avg_bill = st.number_input("Average Monthly Electric Bill ($)", min_value=10.0, value=170.0, step=5.0)

if st.button("🚀 Generate 20-Year Forecast Report", type="primary"):
    with st.spinner("Fetching real EIA data and building your report..."):
        # Get state from address
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

        # Dynamic dates - 10 years back to today (fixes the previous error)
        today = date.today()
        start_date = f"{today.year - 10}-01-01"
        end_date = today.strftime("%Y-%m-%d")

        # Build EIA API URL (updated format that works in 2026)
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

            # Detailed error messages so we always know exactly what happened
            if response.status_code != 200:
                st.error(f"EIA API connection error ({response.status_code}). Try again in a minute.")
                st.caption(f"Technical detail: {response.text[:300]}")
            elif 'error' in data:
                st.error(f"EIA API error: {data.get('error')}")
            elif not data.get('response', {}).get('data'):
                st.error("No price data found for this state right now. Try a different address or wait 5 minutes.")
            else:
                # Success! Process the data
                df = pd.DataFrame(data['response']['data'])
                df['period'] = pd.to_datetime(df['period'])
                df = df.sort_values('period')
                df['price'] = pd.to_numeric(df['price']) / 100  # EIA gives cents → convert to dollars
                df['year'] = df['period'].dt.year
                annual = df.groupby('year')['price'].mean().reset_index()
                
                current_price = annual['price'].iloc[-1]
                usage_kwh = avg_bill / current_price
                
                # Project 10 years forward using real historical trend
                avg_annual_increase = annual['price'].pct_change().mean() + 1 if len(annual) > 1 else 1.03
                last_year = annual['year'].max()
                future_years = list(range(last_year + 1, last_year + 11))
                future_prices = [current_price * (avg_annual_increase ** i) for i in range(1, 11)]
                
                proj_df = pd.DataFrame({'year': future_years, 'price': future_prices})
                
                full_df = pd.concat([annual, proj_df], ignore_index=True)
                full_df['type'] = ['Historical'] * len(annual) + ['Projected'] * len(proj_df)
                full_df['monthly_cost'] = full_df['price'] * usage_kwh
                
                # Charts
                col1, col2 = st.columns(2)
                with col1:
                    fig_price = px.line(full_df, x='year', y='price', color='type', 
                                      title="Electricity Price Trend ($ per kWh)",
                                      labels={'price': 'Price $/kWh'})
                    st.plotly_chart(fig_price, use_container_width=True)
                with col2:
                    fig_cost = px.line(full_df, x='year', y='monthly_cost', color='type',
                                      title="Your Projected Monthly Bill ($)",
                                      labels={'monthly_cost': 'Monthly Cost $'})
                    st.plotly_chart(fig_cost, use_container_width=True)
                
                st.success(f"✅ Report ready for {utility} in {state}")
                st.write(f"**Current price:** ${current_price:.3f} per kWh")
                st.write(f"**Your estimated monthly usage:** {usage_kwh:.0f} kWh")
                st.write(f"**Historical avg annual increase:** {(avg_annual_increase-1)*100:.1f}%")
                
                # PDF Download
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", 'B', 16)
                pdf.cell(0, 10, "20-Year Electricity Cost Forecast Report", ln=1, align='C')
                pdf.set_font("Arial", size=12)
                pdf.ln(10)
                pdf.cell(0, 8, f"Address: {address}", ln=1)
                pdf.cell(0, 8, f"Utility: {utility}   |   State: {state}", ln=1)
                pdf.cell(0, 8, f"Average Monthly Bill: ${avg_bill:.2f}", ln=1)
                pdf.ln(5)
                pdf.cell(0, 8, "Year | Price ($/kWh) | Monthly Cost ($)", ln=1)
                pdf.set_font("Arial", size=10)
                for _, row in full_df.iterrows():
                    pdf.cell(0, 8, f"{int(row['year'])} | ${row['price']:.3f} | ${row['monthly_cost']:.2f} ({row['type']})", ln=1)
                
                pdf_output = io.BytesIO(pdf.output(dest='S').encode('latin1'))
                st.download_button(
                    label="📥 Download Professional PDF Report",
                    data=pdf_output,
                    file_name=f"Electricity_Forecast_{utility.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )
        except Exception as e:
            st.error("Something unexpected happened. Please try again or send me a screenshot.")
            st.caption(f"Technical detail: {str(e)}")
