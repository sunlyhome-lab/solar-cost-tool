import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from fpdf import FPDF
import io

# Your EIA API key
EIA_API_KEY = oZibXfCF83TebCxAcFdzMQMgWx582meQUK9Lt2Qa  

# Map states to census divisions for AEO projections
CENSUS_DIVISIONS = {
    'AL': 'ESC', 'AK': 'PCN', 'AZ': 'MTN', 'AR': 'WSC', 'CA': 'PCS', 'CO': 'MTN',
    'CT': 'NEW', 'DE': 'SAT', 'FL': 'SAT', 'GA': 'SAT', 'HI': 'PCN', 'ID': 'MTN',
    'IL': 'ENC', 'IN': 'ENC', 'IA': 'WNC', 'KS': 'WSC', 'KY': 'ESC', 'LA': 'WSC',
    'ME': 'NEW', 'MD': 'SAT', 'MA': 'NEW', 'MI': 'ENC', 'MN': 'WNC', 'MS': 'ESC',
    'MO': 'WNC', 'MT': 'MTN', 'NE': 'WNC', 'NV': 'MTN', 'NH': 'NEW', 'NJ': 'MAT',
    'NM': 'MTN', 'NY': 'MAT', 'NC': 'SAT', 'ND': 'WNC', 'OH': 'ENC', 'OK': 'WSC',
    'OR': 'PCN', 'PA': 'MAT', 'RI': 'NEW', 'SC': 'SAT', 'SD': 'WNC', 'TN': 'ESC',
    'TX': 'WSC', 'UT': 'MTN', 'VT': 'NEW', 'VA': 'SAT', 'WA': 'PCN', 'WV': 'SAT',
    'WI': 'ENC', 'WY': 'MTN'
}

# Function to geocode address to state
def get_state_from_address(address):
    geolocator = Nominatim(user_agent="solar_tool")
    try:
        location = geolocator.geocode(address)
        if location:
            state = location.raw['address'].get('state', 'TX')  # Default to TX
            state_abbr = location.raw['address'].get('ISO3166-2-lvl4', '').split('-')[-1]
            return state_abbr or 'TX'
    except:
        pass
    return 'TX'  # Fallback

# Fetch historical prices (10 years back, monthly, residential, state)
def fetch_historical_prices(state):
    url = f"https://api.eia.gov/v2/electricity/retail-sales/data/?api_key={EIA_API_KEY}&frequency=monthly&data[0]=price&facets[stateid][]={state}&facets[sectorid][]=RES&start=2014-01&end=2024-12&sort[0][column]=period&sort[0][direction]=desc"
    response = requests.get(url)
    data = response.json()
    if 'response' in data and 'data' in data['response']:
        df = pd.DataFrame(data['response']['data'])
        df['period'] = pd.to_datetime(df['period'])
        df = df.sort_values('period').tail(120)  # Last 10 years (approx 120 months)
        df['price'] = pd.to_numeric(df['price'])
        return df[['period', 'price']]
    return pd.DataFrame()

# Fetch projected prices (AEO, annual, by census division)
def fetch_projected_prices(division):
    # Use latest AEO (2023 ref case)
    series_id = f"AEO.2023.REF2023.EPRCP_{division}.A"
    url = f"https://api.eia.gov/v2/seriesid/{series_id}?api_key={EIA_API_KEY}"
    response = requests.get(url)
    data = response.json()
    if 'response' in data and 'data' in data['response']:
        df = pd.DataFrame(data['response']['data'])
        df['period'] = pd.to_numeric(df['period'])
        df = df[df['period'] >= 2025].head(10)  # Next 10 years
        df['price'] = pd.to_numeric(df['value'])
        # Adjust by historical avg increase (simple linear)
        return df[['period', 'price']]
    return pd.DataFrame()

# Main app
st.title("Solar Consultant Electricity Cost Forecast Tool")

address = st.text_input("Enter Prospect's Address (e.g., 123 Main St, Lewisville, TX)")
utility = st.text_input("Enter Utility Company (e.g., Oncor)")
bill = st.number_input("Enter Average Monthly Bill ($)", min_value=0.0, value=150.0)

if st.button("Generate Report"):
    state = get_state_from_address(address)
    division = CENSUS_DIVISIONS.get(state, 'WSC')  # Default to TX division

    hist_df = fetch_historical_prices(state)
    if hist_df.empty:
        st.error("Error fetching historical data. Check API key or try again.")
    else:
        # Aggregate to annual for simplicity
        hist_df['year'] = hist_df['period'].dt.year
        hist_annual = hist_df.groupby('year')['price'].mean().reset_index()
        current_price = hist_annual['price'].iloc[-1]

        proj_df = fetch_projected_prices(division)
        if proj_df.empty:
            # Fallback: Project using historical avg annual increase
            hist_increase = (hist_annual['price'].pct_change().mean() + 1)  # Avg multiplier
            last_year = hist_annual['year'].max()
            proj_df = pd.DataFrame({'year': range(last_year + 1, last_year + 11)})
            proj_df['price'] = current_price * (hist_increase ** (proj_df['year'] - last_year))

        # Combine historical and projected
        hist_annual.columns = ['year', 'price']
        proj_df.columns = ['year', 'price']
        full_df = pd.concat([hist_annual, proj_df], ignore_index=True)
        full_df['type'] = ['Historical'] * len(hist_annual) + ['Projected'] * len(proj_df)

        # Calculate costs
        usage_kwh = bill / current_price  # Monthly usage
        full_df['monthly_cost'] = usage_kwh * full_df['price']

        # Charts
        fig_price = px.line(full_df, x='year', y='price', color='type', title='Electricity Price Trend ($/kWh)')
        st.plotly_chart(fig_price)

        fig_cost = px.line(full_df, x='year', y='monthly_cost', color='type', title='Projected Monthly Costs ($)')
        st.plotly_chart(fig_cost)

        # Summary
        st.write(f"**Summary for {utility} at {address} (State: {state})**")
        st.write(f"Current Avg Price: ${current_price:.2f}/kWh")
        st.write(f"Estimated Monthly Usage: {usage_kwh:.0f} kWh")
        st.write(f"10-Year Historical Avg Annual Increase: {(hist_annual['price'].pct_change().mean() * 100):.1f}%")
        st.write("Projections based on EIA forecasts + historical trends.")

        # PDF Download
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Solar Cost Forecast Report", ln=1, align='C')
        pdf.cell(200, 10, txt=f"Address: {address}, Utility: {utility}, Bill: ${bill}", ln=1)
        pdf.cell(200, 10, txt=f"Current Price: ${current_price:.2f}/kWh", ln=1)
        # Add data (simple text)
        for i, row in full_df.iterrows():
            pdf.cell(200, 10, txt=f"{row['year']}: Price ${row['price']:.2f}, Cost ${row['monthly_cost']:.2f} ({row['type']})", ln=1)
        pdf_output = io.BytesIO()
        pdf_output.write(pdf.output(dest='S').encode('latin1'))
        pdf_output.seek(0)
        st.download_button("Download PDF Report", pdf_output, file_name="forecast.pdf", mime="application/pdf")
