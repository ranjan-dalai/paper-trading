import os
from kiteconnect import KiteConnect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv("KITE_API_KEY")
api_secret = os.getenv("KITE_API_SECRET")

if not api_key or not api_secret:
    print("Error: KITE_API_KEY and KITE_API_SECRET must be set in .env file.")
    exit()

kite = KiteConnect(api_key=api_key)

print(f"1. Login to this URL in your browser:\n{kite.login_url()}")
print("\n2. After login, you will be redirected to your Redirect URL.")
print("3. Copy the 'request_token' from the URL parameters.")

request_token = input("\nPaste the request_token here: ").strip()

try:
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    print(f"\nSUCCESS! Your Access Token is:\n{access_token}")
    print("\nCopy this token and paste it into your .env file as KITE_ACCESS_TOKEN=")
except Exception as e:
    print(f"\nError generating session: {e}")
