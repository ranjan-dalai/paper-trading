import streamlit as st
import time
import pandas as pd
import pytz
from datetime import datetime, timedelta
from kite_manager import KiteManager
from wallet_manager import WalletManager

# --- CONFIGURATION ---
st.set_page_config(page_title="PaperTrading Sim", layout="wide")
REFRESH_RATE = 5 # seconds

# --- INIT MANAGERS ---
# We use @st.cache_resource for the KiteManager to persist connection/instruments across reruns
@st.cache_resource
def get_kite_manager():
    return KiteManager()


# --- LOGIN SYSTEM ---
if 'username' not in st.session_state:
    st.session_state.username = None

def login():
    st.title("🔐 PaperTrading Login")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Enter Username (Case Sensitive)")
            submitted = st.form_submit_button("Login / Register")
            if submitted and username:
                st.session_state.username = username
                st.rerun()

if not st.session_state.username:
    login()
    st.stop() # Stop execution here if not logged in

# --- MAIN APP (LOGGED IN) ---
username = st.session_state.username
kite = get_kite_manager()
# Initialize wallet for specific user
wallet = WalletManager(username)

# Header with Logout
st.sidebar.markdown(f"User: **{username}**")
if st.sidebar.button("Logout"):
    st.session_state.username = None
    st.session_state.positions = [] # Clear positions from session
    st.rerun()

st.sidebar.divider()
if st.sidebar.button("⚠️ Reset Account", key="reset_acc", type="primary"):
    wallet.reset_account()
    st.sidebar.success("Account Reset!")
    time.sleep(1)
    st.rerun()


# --- MARKET HOURS LOGIC ---
def is_market_open():
    tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(tz)
    # Market: 09:15 to 15:30
    start = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    if now.weekday() > 4: return False # Weekend
    return start <= now <= end

# --- SIDEBAR ---
st.sidebar.title("Configuration")
# Expiry Selector - In real app, we'd fetch actual expiry dates from instruments
# Here we just pick next upcoming Thursdays roughly or let user pick date
today = datetime.now().date()
# Find next thursday
days_ahead = (3 - today.weekday() + 7) % 7
next_thursday = today + timedelta(days=days_ahead)
expiry_date = st.sidebar.date_input("Select Expiry Date", next_thursday)

auto_refresh = st.sidebar.checkbox("Auto-Refresh (5s)", value=True)

# --- HEADER METRICS ---
st.title("PaperTrading - Option Chain Simulator")

col1, col2, col3, col4 = st.columns(4)
indices = kite.get_indices() 

market_status = "LIVE 🟢" if is_market_open() else "CLOSED 🔴"

# Metrics
# Metrics
nifty_data = indices.get('NSE:NIFTY 50', {})
bank_data = indices.get('NSE:NIFTY BANK', {})

nifty_val = nifty_data.get('last_price', 0)
nifty_close = nifty_data.get('ohlc', {}).get('close', nifty_val)
nifty_change = nifty_val - nifty_close

bank_val = bank_data.get('last_price', 0)
bank_close = bank_data.get('ohlc', {}).get('close', bank_val)
bank_change = bank_val - bank_close

col1.metric("NIFTY 50", f"{nifty_val:.2f}", f"{nifty_change:.2f}")
col2.metric("BANK NIFTY", f"{bank_val:.2f}", f"{bank_change:.2f}")
col3.metric("Wallet Balance", f"₹{wallet.get_balance():,.2f}")
# We will render P&L after fetching data
pnl_placeholder = col4.empty()
pnl_placeholder.metric("Day P&L", f"₹{wallet.get_realized_pnl():,.2f}")

st.info(f"Market Status: **{market_status}**")


# --- POSITIONS SECTION ---
pos_placeholder = st.empty()
if st.session_state.positions:
    with pos_placeholder.container():
        with st.expander("Active Positions", expanded=True):
             st.info("Fetching latest prices... (This will update momentarily)")



# --- OPTION CHAIN TABLE ---
st.subheader(f"Option Chain - NIFTY - Expiry: {expiry_date}")

# Fetch Data
with st.spinner("Fetching Option Chain..."):
    df = kite.get_option_chain("NIFTY", expiry_date)

if df.empty:
    st.warning("No Option Chain Data Available. Check Expiry or Connectivity.")
else:
    # --- CUSTOM GRID UI ---
    # Header: OI | LTP | STRIKE | LTP | OI
    # Custom CSS for compact look
    st.markdown("""
        <style>
        div[data-testid="column"] {
            text-align: center;
        }
        div.stButton > button:first-child {
            width: 100%;
            border-radius: 5px;
            border: 1px solid #4CAF50;
        }
        </style>
        """, unsafe_allow_html=True)

    header = st.columns([1.5, 1.5, 3, 1.5, 1.5])
    header[0].markdown("**CE OI (L)**")
    header[1].markdown("**CE LTP**")
    header[2].markdown("**STRIKE**")
    header[3].markdown("**PE LTP**")
    header[4].markdown("**PE OI (L)**")

    expiry_str = expiry_date.strftime("%d%b").upper()
    
    # Calculate ATM for highlighting
    # We fetch spot again or assume it from header logic. Safer to fetch fresh or reuse if simple.
    # But optimal usage: Re-use nifty_val from header if available, else fetch.
    current_spot = nifty_val # From header fetching
    atm_strike = round(current_spot / 50) * 50

    for index, row in df.iterrows():

        c = st.columns([1.5, 1.5, 3, 1.5, 1.5])
        
        strike = int(row['Strike Price'])
        ce_price = row['CE Price']
        pe_price = row['PE Price']
        ce_oi = f"{row['CE OI']/100000:.1f}" # Convert to Lakhs
        pe_oi = f"{row['PE OI']/100000:.1f}"

        # CE Data
        c[0].markdown(f":blue[{ce_oi}]")
        c[1].markdown(f"**{ce_price}**")

        # CENTER: STRIKE BUTTON (POPOVER)
        # Highlight ATM
        label = f"{strike} ({expiry_str})"
        btn_type = "primary" if strike == atm_strike else "secondary"
        
        # We can't easily style the individual button color without more CSS hacks, 
        # but we can add an indicator.
        if strike == atm_strike:
            label = f"📍 {strike} ({expiry_str})"
            # Add a visual separator or background? 
            # Streamlit columns don't support bg color directly without custom html.
            # We will rely on the verifyable indicator icon.
        
        with c[2].popover(label, use_container_width=True):

            st.markdown(f"### Trade {expiry_str} **{strike}**")
            
            # Instrument Selection (Outside form for immediate update)
            # Use columns to make it compact
            p_col1, p_col2 = st.columns(2)
            inst_type_sel = p_col1.radio(
                "Instrument", 
                ["CE", "PE"], 
                horizontal=True, 
                key=f"inst_{strike}",
                label_visibility="collapsed"
            )
            
            # Determine values based on selection
            if inst_type_sel == "CE":
                active_price = ce_price
                full_inst = f"{strike} CE"
            else:
                active_price = pe_price
                full_inst = f"{strike} PE"
                
            p_col2.metric("LTP", f"₹{active_price}")
            
            # Trade Form
            with st.form(key=f"trade_form_{strike}"):
                qty = st.number_input("Qty (Lot: 50)", min_value=50, step=50, value=50, key=f"qty_{strike}")
                action = st.radio("Action", ["BUY", "SELL"], horizontal=True, key=f"act_{strike}")
                
                # Submit
                total_val = qty * active_price
                submit_txt = f"{action} at ₹{total_val:,.2f}"
                if st.form_submit_button(submit_txt, use_container_width=True):
                    success, msg = wallet.execute_trade(
                        action,
                        full_inst,
                        qty,
                        active_price
                    )
                    if success:
                        st.success("Order Executed!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
                    
        # PE Data
        c[3].markdown(f"**{pe_price}**")
        c[4].markdown(f":blue[{pe_oi}]")

    # --- UPDATE P&L WITH LIVE PRICES ---
    # Construct LTP dict from the dataframe we just iterated
    current_prices = {}
    for index, row in df.iterrows():
        s = int(row['Strike Price'])
        current_prices[f"{s} CE"] = row['CE Price']
        current_prices[f"{s} PE"] = row['PE Price']
        
    total_pnl = wallet.update_pnl_heatmap(current_prices)
    
    # Update the Metric at the top
    pnl_placeholder.metric("Day P&L", f"₹{total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")

    # --- REFRESH POSITIONS TABLE ---
    # Render the positions table into the placeholder we defined earlier
    if st.session_state.positions:
        with pos_placeholder.container():
            with st.expander("Active Positions", expanded=True):
                 # Convert to DF for clearer display & manipulation
                 pos_df = pd.DataFrame(st.session_state.positions)
                 
                 if not pos_df.empty:
                    # CSV Download Button (Top Right of Expander)
                    csv = pos_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📄 Export CSV",
                        data=csv,
                        file_name='open_positions.csv',
                        mime='text/csv',
                        key='download_pos'
                    )

                 # Custom Header
                 h_col = st.columns([3, 1, 2, 2, 2, 2, 1.5]) 
                 h_col[0].markdown("**Instrument**")
                 h_col[1].markdown("**Type**")
                 h_col[2].markdown("**Qty**")
                 h_col[3].markdown("**Avg**")
                 h_col[4].markdown("**LTP**")
                 h_col[5].markdown("**P&L**")
                 h_col[6].markdown("**Action**")

                 # Show recent trades first (Reverse order)
                 # We can't just reverse the list in-place as it affects session state.
                 # We create a reversed view.
                 reversed_positions = list(reversed(st.session_state.positions))

                 for i, pos in enumerate(reversed_positions):
                     # p_col = st.columns([3, 1, 2, 2, 2, 2, 1.5])
                     p_container = st.container()
                     p_col = p_container.columns([3, 1, 2, 2, 2, 2, 1.5])
                     
                     inst = pos['instrument']
                     p_type = pos['type']
                     qty = pos['qty']
                     avg = pos['avg_price']
                     ltp = pos.get('current_price', avg) # Fallback to avg if 0
                     pnl = pos.get('unrealized_pnl', 0.0)
                     
                     p_col[0].text(inst)
                     p_col[1].text(p_type)
                     p_col[2].text(qty)
                     p_col[3].text(f"{avg:.2f}")
                     p_col[4].text(f"{ltp:.2f}")
                     
                     pnl_color = "green" if pnl >= 0 else "red"
                     p_col[5].markdown(f":{pnl_color}[{pnl:.2f}]")
                     
                     # Close Button
                     # Use 'inst' in key to be safe, 'i' is just row index in this view
                     if p_col[6].button("Close", key=f"close_btn_{inst}"):
                         success, msg = wallet.execute_trade(
                             "SELL",
                             inst,
                             qty, # Close full quantity
                             ltp
                         )
                         if success:
                             st.success(f"Closed {inst}")
                             time.sleep(0.5)
                             st.rerun()
                         else:
                             st.error(msg)
                     
                     st.divider()




# --- AUTO REFRESH LOOP ---
if auto_refresh:
    time.sleep(REFRESH_RATE)
    st.rerun()
