# Hand-written synthetic items (synthetic: true). Written 29 Oct 2026 for SB evals.
# All numbers, UPI IDs, accounts and links are invented. Links use the reserved .example TLD.
# Never dial, pay, or visit anything here.
S = []
def add(text, label, scam_type, modality, language, based_on=None, gold=None, notes=None, edge=None):
    S.append(dict(text=text, label=label, scam_type=scam_type, modality=modality, language=language,
                  based_on=based_on, gold=gold or {}, notes=notes, edge_tags=edge or []))

PR65="https://www.sebi.gov.in/media-and-notifications/press-releases/oct-2026/"  # see sources.md for exact PDFs
NSE_JOINT="https://www.nseindia.com/resources/exchange-communication-press-releases"
HINDU_JUN="https://www.thehindu.com/"  # exact article URL in sources.md

# ---------- Investment / trading (scam) ----------
add("Welcome to 282 Elite Stock Research Group! Our chief analyst shares 3-5 free picks daily. Last week members made 38%. Add the assistant on WhatsApp +91 9000012345 to get your VIP seat.",
    "scam","investment_trading","whatsapp","en",based_on="SEBI PR 27/2025; The Hindu 24 Jun 2026",
    gold={"phoneNumbers":["+919000012345"],"investmentStage":"hook"},edge=["group_invite","assured_returns"])
add("Bhai institutional account khol do, FII quota se IPO allotment 100% guaranteed hai. Normal demat mein nahi milega. App link: https://gtx-institutional.example/download",
    "scam","investment_trading","whatsapp","hinglish",based_on="NSE/BSE joint PR 23 Aug 2024",
    gold={"appLinks":["https://gtx-institutional.example/download"],"investmentStage":"onboarding"},edge=["institutional_fpi_account","ipo_allotment"])
add("Dear member, block deal shares of a Nifty 50 company available at 22% discount today only. Minimum Rs 50,000. Transfer to our clearing account and shares will reflect by T+1. A/C 50200012345678 IFSC HDFC0001234 Beneficiary: Vriddhi Ventures",
    "scam","investment_trading","whatsapp","en",based_on="NSE/BSE joint PR 23 Aug 2024",
    gold={"bankAccounts":["50200012345678"],"ifscCodes":["HDFC0001234"],"beneficiaryNames":["Vriddhi Ventures"],"investmentStage":"deposit"},edge=["block_deal","pay_to_personal_account"])
add("Your profit Rs 15,62,400 is ready. To withdraw you must first pay 20% capital gains tax and a risk-margin fee of Rs 3,12,480 as per SEBI rules. Pay to UPI riskdesk.settle@ybl within 24 hours or the account will be frozen.",
    "scam","investment_trading","telegram","en",based_on="The Hindu 24 Jun 2026; FBI crypto investment fraud page",
    gold={"upiIds":["riskdesk.settle@ybl"],"withdrawalFeeDemands":[{"amount_inr":312480,"reason":"capital gains tax + risk margin"}],"investmentStage":"withdrawal_wall"},edge=["withdrawal_fee_demand","fake_regulator"])
add("Due to platform risk control our old group was removed. Please join our new group for daily quality stock picks: https://chat.whatsapp.example/AbCdEf123",
    "scam","investment_trading","whatsapp","en",based_on="SEBI PR 65/2026 (paraphrase of quoted re-invite)",
    gold={"groupLinks":["https://chat.whatsapp.example/AbCdEf123"],"investmentStage":"hook"},edge=["group_reinvite"])
add("Sir I am SEBI registered advisor, reg no INA000099999, certificate attached. Daily 5-8% return assured, zero loss. Pay Rs 25,000 for Whale membership to atharv.wealth@okicici",
    "scam","investment_trading","whatsapp","en",based_on="TOI 18 Jan 2026; SEBI PR 22/2025",
    gold={"claimedRegNos":["INA000099999"],"upiIds":["atharv.wealth@okicici"],"promisedReturn":"5-8% daily","investmentStage":"credibility"},edge=["fake_registration","assured_returns"])
add("Hello, I'm Anika from Singapore, I trade crypto with my uncle's insider signals. I made 4 lakh this month on BTC contract trading. I can teach you, just register on https://coinvault-pro.example and deposit USDT (TRC20) to TQx9exampleWALLETaddr1234567890ab",
    "scam","crypto_investment","whatsapp","en",based_on="The Tribune 24 Apr 2026 (pig-butchering)",
    gold={"investmentPlatforms":["https://coinvault-pro.example"],"cryptoWallets":["TQx9exampleWALLETaddr1234567890ab"],"cryptoNetworks":["TRC20"],"investmentStage":"onboarding"},edge=["pig_butchering","crypto_transfer"])
add("आदरणीय निवेशक, हमारे VIP ग्रुप में शामिल होकर रोज़ाना 10% लाभ पाएं। सेबी प्रमाणित विशेषज्ञ। अभी जुड़ें: https://vip-share.example/join",
    "scam","investment_trading","sms","hi",based_on="SEBI PR 27/2025",
    gold={"groupLinks":["https://vip-share.example/join"]},edge=["assured_returns","regional"])
add("Unga demat-la IPO allotment confirm aagum, just 2% service charge kattunga. Pre-IPO shares 40% listing gain guaranteed. UPI: preipo.desk@paytm",
    "scam","investment_trading","whatsapp","ta_en",based_on="NSE/BSE joint PR 23 Aug 2024",
    gold={"upiIds":["preipo.desk@paytm"]},edge=["ipo_allotment","regional","assured_returns"])
add("Mee trading account login ID and password share cheyyandi, maa expert mee account lo trades chestaru. Profit lo 30% maaku ivvandi.",
    "scam","investment_trading","whatsapp","te_en",based_on="NSE/BSE joint PR 23 Aug 2024; NSE caution PRs Oct 2026",
    gold={},edge=["credential_request","regional"])
add("[voice transcript] Caller: Sir main Zerodha ke institutional desk se bol raha hoon, aapka profile select hua hai FII sub-account ke liye. Bas ek app install karna hai, link WhatsApp pe bhej raha hoon. Pehle 10,000 daalo, kal 15,000 dikhega.",
    "scam","investment_trading","voice_transcript","hinglish",based_on="SEBI PR 22/2025 (impersonation; 1600 series rule)",
    gold={"impersonatedEntities":["Zerodha"],"investmentStage":"onboarding"},edge=["voice","impersonation","institutional_fpi_account"])
add("Your account in GTS-C Securities shows a balance of Rs 2.31 crore. Withdrawal is blocked due to an audit by the regulator. Pay an audit clearance fee of Rs 25 lakh to unlock. Contact your relationship manager.",
    "scam","investment_trading","whatsapp","en",based_on="TOI 18 Jan 2026; Hyderabad Mail (clear audits)",
    gold={"investmentPlatforms":["GTS-C Securities"],"withdrawalFeeDemands":[{"amount_inr":2500000,"reason":"audit clearance"}],"investmentStage":"withdrawal_wall"},edge=["withdrawal_fee_demand","paper_profits"])
add("We are a recovery agency approved by cyber cell. We can recover the money you lost in the trading scam. Pay a 10% advance processing fee of Rs 45,000 to start the case.",
    "scam","recovery_scam","whatsapp","en",based_on="FBI crypto investment fraud page (recovery scams)",
    gold={"investmentStage":"recovery"},edge=["recovery_scam"])
# ---------- Investment legit look-alikes ----------
add("Your trade confirmation: Bought 10 INFY @ 1,512.40 on NSE. Contract note has been sent to your registered email. - Your broker",
    "legit","none","sms","en",notes="generic broker contract-note alert; no link, no payment ask",edge=["hard_negative","investment_legit"])
add("Pay your SIP instalment of Rs 5,000 via UPI to abcmf.mf@validhdfc. Look for the green thumbs-up icon before paying.",
    "legit","none","sms","en",based_on="SEBI PR 64/2025 (@valid format)",notes="format matches @valid .mf; still verify via SEBI Check",edge=["hard_negative","valid_upi"])
add("NSE alert: Assured returns on stock market investments are prohibited by law. Do not share your trading credentials with anyone.",
    "legit","none","sms","en",based_on="NSE caution press releases, Oct 2026",notes="regulator-style awareness text; must not be flagged",edge=["hard_negative","awareness_message"])
add("Weekly market wrap: Nifty ended 1.2% higher. This is not investment advice. Read our full report on the app.",
    "legit","none","email","en",notes="finfluencer/newsletter style without assured returns or payment ask",edge=["hard_negative","finfluencer_like"])
add("[voice transcript] Caller from 1600xxxxxx: Hello, this is a service call from your broker regarding your pending nomination update. Please complete it in the app under Profile. We will not ask for OTP or password.",
    "legit","none","voice_transcript","en",based_on="SEBI PR 22/2025 (1600 series for service calls)",edge=["hard_negative","voice"])

# ---------- Digital arrest ----------
add("[voice transcript] Caller: This is Inspector Rathore from Mumbai Crime Branch. A parcel in your name with 200 grams MDMA and 5 passports was seized at customs. You are under digital arrest. Do not disconnect, do not tell family. Transfer your funds to the RBI verification account for checking, it will be returned in 2 hours.",
    "scam","digital_arrest","voice_transcript","en",based_on="I4C / PIB advisories on digital arrest",
    gold={"impersonatedEntities":["Mumbai Crime Branch","RBI"]},edge=["voice","digital_arrest","isolation"])
add("[voice transcript] Sir CBI se baat ho rahi hai, aapke Aadhaar se money laundering case register hua hai. Video call pe raho, camera on rakho. Supreme Court ka arrest warrant PDF bhej rahe hain.",
    "scam","digital_arrest","voice_transcript","hinglish",based_on="I4C / PIB advisories on digital arrest",
    gold={"impersonatedEntities":["CBI","Supreme Court"]},edge=["voice","digital_arrest"])
add("TRAI NOTICE: Your mobile number will be blocked in 2 hours due to illegal activity registered against your Aadhaar. Press 9 to speak to the officer.",
    "scam","digital_arrest","voice_transcript","en",based_on="DoT/TRAI advisories on fake disconnection calls",
    gold={"impersonatedEntities":["TRAI"]},edge=["voice","ivr"])
add("Aapke naam pe FedEx parcel mein drugs mila hai, Mumbai cyber police se connect kar rahe hain. Skype ID mumbai.cyber.desk pe video call join karo abhi.",
    "scam","digital_arrest","whatsapp","hinglish",based_on="I4C advisories",
    gold={"socialHandles":["mumbai.cyber.desk"],"impersonatedEntities":["FedEx","Mumbai cyber police"]},edge=["digital_arrest"])
# ---------- Sextortion ----------
add("I have recorded your video call. Pay Rs 30,000 to UPI shreya.help@axl in 1 hour or I will send it to all your Instagram followers and family.",
    "scam","sextortion","whatsapp","en",based_on="I4C cyber safety advisories (sextortion)",
    gold={"upiIds":["shreya.help@axl"]},edge=["sextortion","threat"])
add("[voice transcript] Main Delhi police se DSP bol raha hoon, aapka video YouTube pe upload hua hai aur ladki ne complaint ki hai. Case band karwana hai toh 50,000 dena padega.",
    "scam","sextortion","voice_transcript","hinglish",based_on="I4C advisories (sextortion + police impersonation)",
    gold={"impersonatedEntities":["Delhi police"]},edge=["sextortion","voice","impersonation"])
add("Hi dear, I am lonely, can we do video call? Send me your WhatsApp number 😊",
    "scam","sextortion","telegram","en",notes="early-stage lure; label scam but low-confidence",edge=["early_stage","ambiguous_intent"])
# ---------- Job / task ----------
add("Part time job: Like YouTube videos and earn Rs 150 per like, daily Rs 3,000-8,000. Contact HR on Telegram @hr_priya_jobs",
    "scam","job_task","whatsapp","en",based_on="I4C advisories on task-based job fraud",
    gold={"socialHandles":["@hr_priya_jobs"]},edge=["task_scam"])
add("Congratulations! Aapka selection Amazon work-from-home ke liye hua hai. Registration fee Rs 1,499 bharo UPI: amzn.hr.cell@ibl, joining letter turant milega.",
    "scam","job_task","sms","hinglish",based_on="PIB Fact Check job-scam alerts",
    gold={"upiIds":["amzn.hr.cell@ibl"],"impersonatedEntities":["Amazon"]},edge=["fee_upfront","impersonation"])
add("Tumhi prepaid task complete kela, aata 3 tasks sathi 10,000 deposit kara mag 14,500 withdraw karu shakta.",
    "scam","job_task","telegram","mr_en",based_on="I4C advisories on task-based job fraud",gold={},edge=["task_scam","regional"])
add("Your interview with our HR team is scheduled on 4 Nov at 11:00 AM on Google Meet. Please carry ID proof. No fee is charged at any stage of hiring.",
    "legit","none","email","en",edge=["hard_negative","job_legit"])
# ---------- Customer care / KYC / UPI ----------
add("[voice transcript] Sir main Paytm customer care se, aapka refund atak gaya hai. AnyDesk app install kijiye aur 9 digit code bataiye, hum refund process kar denge.",
    "scam","customer_care","voice_transcript","hinglish",based_on="RBI/NPCI advisories on screen-sharing apps",
    gold={"impersonatedEntities":["Paytm"]},edge=["voice","remote_access"])
add("Dear customer your SBI YONO account will be blocked today. Update PAN immediately: https://sbi-yono-kyc.example/update",
    "scam","kyc_phishing","sms","en",based_on="SBI / PIB Fact Check KYC phishing alerts",
    gold={"phishingLinks":["https://sbi-yono-kyc.example/update"],"impersonatedEntities":["SBI"]},edge=["kyc"])
add("Aapko Rs 5,000 cashback mila hai. Receive karne ke liye UPI PIN daaliye. Request from cashback.offer@ybl",
    "scam","upi_collect","sms","hinglish",based_on="NPCI safety tips (PIN only to pay, never to receive)",
    gold={"upiIds":["cashback.offer@ybl"]},edge=["upi_collect"])
add("Your electricity connection will be disconnected tonight at 9:30 PM because last month bill was not updated. Call officer 9000054321 immediately.",
    "scam","utility_bill","sms","en",based_on="Discom / PIB advisories on fake electricity SMS",
    gold={"phoneNumbers":["9000054321"]},edge=["urgency"])
add("India Post: Your parcel is held due to incomplete address. Update within 12 hours: https://indiapost-redeliver.example",
    "scam","delivery_phishing","sms","en",based_on="PIB Fact Check India Post phishing alerts",
    gold={"phishingLinks":["https://indiapost-redeliver.example"],"impersonatedEntities":["India Post"]},edge=["delivery"])
add("RTO e-Challan: Rs 1,000 pending for your vehicle. Pay now or licence will be suspended. Download mParivahan app: https://mparivahan-challan.example/app.apk",
    "scam","echallan_apk","sms","en",based_on="X reports of fake e-challan APK SMS, Sep-Oct 2026 (see sources.md)",
    gold={"apkLinks":["https://mparivahan-challan.example/app.apk"],"impersonatedEntities":["mParivahan"]},edge=["apk"])
add("আপনার বিদ্যুৎ সংযোগ আজ রাতে বিচ্ছিন্ন হবে। এখনই এই নম্বরে কল করুন 9000067890",
    "scam","utility_bill","sms","bn",based_on="Discom advisories",gold={"phoneNumbers":["9000067890"]},edge=["regional","native_script"])
add("உங்கள் வங்கி கணக்கு இன்று முடக்கப்படும். KYC புதுப்பிக்க இந்த லிங்கை கிளிக் செய்யவும் https://kyc-update-bank.example",
    "scam","kyc_phishing","sms","ta",based_on="Bank KYC phishing advisories",gold={"phishingLinks":["https://kyc-update-bank.example"]},edge=["regional","native_script"])
# ---------- Legit look-alikes ----------
add("123456 is your OTP for login. Do not share it with anyone. Bank will never call to ask for OTP. - XYZ Bank",
    "legit","none","sms","en",edge=["hard_negative","otp"])
add("Rs 2,450.00 debited from A/c XX1234 on 28-10-26 to VPA swiggy@icici. UPI Ref 630112345678. Not you? Call 1800-XXX-XXXX",
    "legit","none","sms","en",edge=["hard_negative","debit_alert"])
add("Your Amazon order #402-1234567-1234567 is out for delivery. Share OTP 4821 only with the delivery agent at your doorstep.",
    "legit","none","sms","en",edge=["hard_negative","delivery","otp"])
add("Aapka order dispatch ho gaya hai, kal tak deliver hoga. Track karein app mein. - Meesho",
    "legit","none","sms","hinglish",edge=["hard_negative","delivery"])
add("Your electricity bill of Rs 1,234 for Oct 2026 is generated. Due date 15-11-2026. Pay via the official app or website.",
    "legit","none","sms","en",edge=["hard_negative","utility"])
add("[voice transcript] Agent: Namaste, main aapke bank se bol rahi hoon, aapke credit card ka statement generate ho gaya hai. Hum aapse koi OTP ya PIN nahi maangenge. Kya main aur madad kar sakti hoon?",
    "legit","none","voice_transcript","hinglish",edge=["hard_negative","voice"])
add("Mom, phone ki battery khatam ho rahi hai, friend ke phone se call karungi raat ko. Khana kha lena.",
    "legit","none","whatsapp","hinglish",edge=["hard_negative","everyday"])
add("Amma, naan train-la irukken, 8 mani ku vandhuduven. Dinner wait pannunga.",
    "legit","none","whatsapp","ta_en",edge=["hard_negative","everyday","regional"])
add("Hi, I'm from your housing society committee. Maintenance for Nov is Rs 3,500; pay at the office or through the society app as usual.",
    "legit","none","whatsapp","en",edge=["hard_negative","payment_request_legit"])
