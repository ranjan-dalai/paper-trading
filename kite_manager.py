import os
import pandas as pd
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import datetime
import random

load_dotenv()

class KiteManager:
    def __init__(self):
        self.api_key = os.getenv("KITE_API_KEY")
        self.access_token = os.getenv("KITE_ACCESS_TOKEN")
        self.kite = KiteConnect(api_key=self.api_key)
        
        # Set access token if available
        if self.access_token:
            self.kite.set_access_token(self.access_token)

        # Cache instruments to avoid heavy API calls every refresh
        self.instruments_list = None
        self.use_mock = False
        
        if not self.access_token:
            print("Warning: No Access Token found. Switching to Mock Mode.")
            self.use_mock = True
        
    def _fetch_instruments(self):
        """Fetches and caches the master instrument list from Zerodha."""
        if self.use_mock:
            return pd.DataFrame() # Mock implementations don't need this usually

        if self.instruments_list is None:
            try:
                print("Fetching master instrument list... (This happens once)")
                self.instruments_list = pd.DataFrame(self.kite.instruments("NFO"))
            except Exception as e:
                print(f"Error fetching instruments: {e}. Switching to Mock.")
                self.use_mock = True
                return pd.DataFrame()
        return self.instruments_list

    def get_spot_price(self, instrument_symbol="NSE:NIFTY 50"):
        """Fetches the underlying spot price to calculate ATM."""
        if self.use_mock:
            return 24100.0 if "NIFTY" in instrument_symbol else 48000.0

        try:
            quote = self.kite.quote(instrument_symbol)
            return quote[instrument_symbol]['last_price']
        except Exception as e:
            print(f"Error fetching spot price: {e}")
            return 24000.0 # Fallback

    def get_option_chain(self, symbol="NIFTY", expiry_date=None, depth=10):
        """
        Fetches option chain centered around ATM.
        """
        if self.use_mock:
            return self._get_mock_option_chain(symbol, expiry_date)

        # 1. Get Spot Price
        spot_symbol = "NSE:NIFTY 50" if symbol == "NIFTY" else "NSE:NIFTY BANK"
        spot_price = self.get_spot_price(spot_symbol)
        
        # 2. Calculate ATM Strike
        step = 50 if symbol == "NIFTY" else 100
        atm_strike = round(spot_price / step) * step

        # 3. Define Strike Range
        min_strike = atm_strike - (depth * step)
        max_strike = atm_strike + (depth * step)

        # 4. Filter Master Instrument List
        df = self._fetch_instruments()
        
        if df.empty:
            return self._get_mock_option_chain(symbol, expiry_date)

        # Filter 1: Name (e.g., NIFTY) and Segment
        mask_symbol = df['name'] == symbol
        # Filter 2: Expiry
        if isinstance(expiry_date, (datetime.date, datetime.datetime)):
            expiry_date = expiry_date
        else:
            # parsing logic if string
             pass
             
        mask_expiry = df['expiry'] == pd.to_datetime(expiry_date).date()
        # Filter 3: Strike Range
        mask_strike = (df['strike'] >= min_strike) & (df['strike'] <= max_strike)

        filtered_df = df[mask_symbol & mask_expiry & mask_strike].copy()
        
        if filtered_df.empty:
            print("No instruments found for this criteria.")
            return self._get_mock_option_chain(symbol, expiry_date)

        # 5. Fetch Live Quotes for these instruments
        tokens = filtered_df['instrument_token'].tolist()
        try:
            live_data = self.kite.quote(tokens)
        except Exception as e:
            print(f"Error fetching quotes: {e}")
            return self._get_mock_option_chain(symbol, expiry_date)

        # 6. Merge Live Data back into DataFrame
        ltp_list = []
        oi_list = []
        
        for token in filtered_df['instrument_token']:
            data = live_data.get(token, {})
            # Kite sometimes returns quote key as string, sometimes int. 
            # safe fetch logic
            data = live_data.get(str(token)) or live_data.get(int(token)) or {}
            
            ltp_list.append(data.get('last_price', 0))
            oi_list.append(data.get('oi', 0))

        filtered_df['LTP'] = ltp_list
        filtered_df['OI'] = oi_list

        # 7. Pivot/Format for UI (Call vs Put)
        ce_df = filtered_df[filtered_df['instrument_type'] == 'CE'][['strike', 'LTP', 'OI']].set_index('strike')
        pe_df = filtered_df[filtered_df['instrument_type'] == 'PE'][['strike', 'LTP', 'OI']].set_index('strike')
        
        # Join on Strike
        final_chain = ce_df.join(pe_df, lsuffix='_CE', rsuffix='_PE', how='outer').sort_index()
        
        # Rename columns for the UI
        final_chain = final_chain.reset_index()
        final_chain.columns = ['Strike Price', 'CE Price', 'CE OI', 'PE Price', 'PE OI']
        
        return final_chain

    def _get_mock_option_chain(self, symbol, expiry_date):
        base = 24000 if symbol == "NIFTY" else 48000
        step = 50 if symbol == "NIFTY" else 100
        strikes = [base + (i * step) for i in range(-5, 6)]
        
        data = {
            "Strike Price": strikes,
            "CE Price": [100 + i*10 for i in range(len(strikes))],
            "CE OI": [10000 + i*100 for i in range(len(strikes))],
            "PE Price": [150 - i*10 for i in range(len(strikes))],
            "PE OI": [8000 + i*100 for i in range(len(strikes))]
        }
        return pd.DataFrame(data)

    def get_indices(self):
        """Helper to get top bar indices"""
        if self.use_mock:
            # Simulate live fluctuations
            base_nifty = 24100.0
            base_bank = 48100.0
            
            # Fluctuate within +/- 20 points
            nifty_ltp = base_nifty + random.uniform(-10, 20)
            bank_ltp = base_bank + random.uniform(-20, 50)
            
            return {
                "NSE:NIFTY 50": {
                    "last_price": round(nifty_ltp, 2), 
                    "ohlc": {"close": base_nifty}
                },
                "NSE:NIFTY BANK": {
                    "last_price": round(bank_ltp, 2), 
                    "ohlc": {"close": base_bank}
                }
            }
        try:
            return self.kite.quote(["NSE:NIFTY 50", "NSE:NIFTY BANK"])
        except Exception:
            return {
                "NSE:NIFTY 50": {"last_price": 24000.00, "ohlc": {"close": 24000.00}},
                "NSE:NIFTY BANK": {"last_price": 48000.00, "ohlc": {"close": 48000.00}}
            }
