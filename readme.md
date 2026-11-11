# Goal Saver: AI savings tracker (PayPal AI Hackathon)

## Setup walkthrough

### 1. Get PayPal sandbox keys
1. Log in at https://developer.paypal.com
2. Go to Apps & Credentials, make sure the **Sandbox** toggle is on.
3. Click **Create App**, name it `GoalSaver`, type Merchant.
4. Copy **Client ID** and click **Show** to copy the **Secret**.

### 2. Put keys in `.env` (never upload this file)
1. Copy `.env.example` to a new file named `.env`
2. Fill it in:
```
PAYPAL_CLIENT_ID=your_client_id
PAYPAL_SECRET=your_secret
GEMINI_API_KEY=your_gemini_key  (free: aistudio.google.com)
APP_URL=http://localhost:8501
```
`APP_URL` is where PayPal sends the buyer after paying.
- Running on your laptop: `http://localhost:8501`
- After deploying (Render): your Render link, e.g. `https://goal-saver.onrender.com`

The PayPal API address (`https://api-m.sandbox.paypal.com`) is already in the code. Do not change it.

### 3. Run
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### 4. Test payment
Use the sandbox **personal** test account from Developer Dashboard > Testing Tools > Sandbox Accounts to log in and pay.

### 5. Deploy on Render
Add the same 4 values under Environment Variables (not in GitHub). Start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

## Note
Educational only. Not financial advice.