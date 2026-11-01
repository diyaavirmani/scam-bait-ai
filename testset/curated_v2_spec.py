# Hand-curated v2 additions (Task 7). Each X row: (post_id, exact_extract, scam_type, modality, channel, extra_tags, note)
# exact_extract MUST be a substring of the post text (HTML-unescaped, whitespace-collapsed); verified by append_realset.py.
# All rows are label=scam (scammer-authored words: quoted msg, direct spam, or reported call/threat clause).
X = [
# ---- sextortion (threat text only; no explicit content) ----
("1403924996028698628","tunhari video viral kar denge agr paise nahi diye to","sextortion","threat_reported","voice_call",[],"Hindi indirect quote of caller threat"),
("1257239091919433728","you tube channel se baat Kar rahe hai aap video viral Kar denge pure Desh me nai Karna hai to AC pe paise dalo","sextortion","threat_reported","voice_call",["typo_slang"],"fake YouTube impersonation threat"),
("1421107243026554880","main youtube office me kaam krta hun aur tmhara video viral kar dunga agar paise nhi bheje to","sextortion","threat_reported","voice_call",[],"threat clause only; surrounding context and phones excluded"),
("1532425565893894144","if you not sending money your video will be viral social media","sextortion","threat_reported","whatsapp",["typo_slang"],"reported threat"),
("2089387844158849202","we will make your video viral","sextortion","threat_reported","voice_call",["short"],"reported threat; reporter says no video existed"),
("1948639467209679053","this call is from Delhi cyber crime branch New Delhi","sextortion","call_script_reported","voice_call",["fake_police_followup"],"fake police follow-up after video-call accusation"),
("1708385490288992689","Paisa do nahi to video viral kr denge","sextortion","threat_reported","whatsapp",["short"],"after fake FB profile video call"),
("1446154994873290755","agr paisa nhi doge to ye video viral kar denge","sextortion","threat_reported","voice_call",["short"],"first-person account"),
("1412860528964227072","ydi paisa nhi denge to viral kr denge","sextortion","threat_reported","whatsapp",["short"],"FB profile -> video call modus"),
("1740667103437591006","paisey bhejo nhi to jel me dldung","sextortion","threat_reported","voice_call",["short","fake_police_followup"],"second caller threat after recorded video call"),
("1628405149130723329","mera video YouTube pr viral kr diya jayega","sextortion","threat_reported","voice_call",["short"],"reported threat"),
# ---- UPI collect / QR ----
("2112489975812178012","I'm from the Army. I'll buy your sofa. Scan this QR and enter UPI PIN to receive the advance.","upi_collect_qr","quoted_scam_msg","whatsapp",[],"advisory_quote: awareness post example"),
("2111076442054230114","Scan this QR, you'll receive ₹5,000.","upi_collect_qr","quoted_scam_msg","unknown",["short"],"advisory_quote: awareness post example (OLX buyer)"),
("1425117478993031170","Click on pay, enter rs 1, and enter your UPI pin","upi_collect_qr","call_script_reported","voice_call",["short"],"direct quote of caller"),
("1335797807446327298","XYZ scan it to receive this amount","upi_collect_qr","quoted_scam_msg","whatsapp",["short"],"quoted WhatsApp text; XYZ = placeholder in original"),
("1638550005446479872","you have to scan the QR code and make 1₹ payment","upi_collect_qr","call_script_reported","voice_call",["short"],"direct speech"),
("1328351734922571777","scan this QR code to receive Rs 5 and then they will transfer balance amount","upi_collect_qr","call_script_reported","voice_call",[],"indirect speech (fake relative)"),
("1304096968508022785","scan and then enter UPI pin in order to receive money","upi_collect_qr","call_script_reported","voice_call",[],"indirect speech"),
("1442742929567535104","enter UPI pin to receive this money","upi_collect_qr","call_script_reported","voice_call",["short"],"indirect speech; UPI collect link"),
("1693914598506910036","scan the QR code to receive the remaining balance","upi_collect_qr","call_script_reported","voice_call",["short"],"indirect speech"),
("1678314769869340672","scan QR code and dial UPI pin to receive money","upi_collect_qr","call_script_reported","voice_call",["short"],"indirect speech (OLX)"),
("1824668441388650920","scan and put my pin to receive 2 rupees first","upi_collect_qr","call_script_reported","voice_call",["short"],"indirect speech (OLX)"),
("1461608978488586240","scan his QR code from @WhatsApp using paytm import photo feature to receive payment","upi_collect_qr","call_script_reported","whatsapp",[],"indirect speech (OLX)"),
("1409067876741357573","put the UPI pin to receive the cashback","upi_collect_qr","call_script_reported","voice_call",["short"],"indirect speech"),
("1242849986204667905","because of lockdown ixigo is making refund through upi","upi_collect_qr","call_script_reported","voice_call",["short"],"indirect speech; then asked to enter UPI PIN on a link"),
# ---- loan-app harassment ----
("1563023888208265216","Xyz person you are seeing in this photo is a fraud and he has taken a loan from our company and said that he will pay.","loan_app_harassment","quoted_scam_msg","whatsapp",[],"quoted message"),
("1481675845894737921","somebody has taken a loan and he has given your number as a reference","loan_app_harassment","quoted_scam_msg","whatsapp",[],"indirect quote of WhatsApp msg"),
("1335481221929811969","This person has taken a loan and has given your number in reference, it has verified and changed your number.","loan_app_harassment","quoted_scam_msg","whatsapp",[],"pasted message"),
("1333980627989790721","DEAR SIR MAM I AM FROMRUPEEBAZZAR Legal DEPARTMENT, ONE OF YOUR FAMILY MEMBER OR FRINDS HAS TAKEN A LOAN AND GAVE US YOUR NUMBER IN References","loan_app_harassment","quoted_scam_msg","sms",["typo_slang"],"pasted message; trailing name/number excluded"),
("1776546941012427218","2100liya hee to 6000repement Karo nhi to parshonal photo video viral kar denge","loan_app_harassment","threat_reported","voice_call",["typo_slang"],"Hindi reported threat"),
("1599111324755427328","make the payment imidate,otherwise we will send the naked photo to your contact list","loan_app_harassment","threat_reported","whatsapp",["typo_slang"],"threat clause only (no explicit content)"),
("1967870380233855141","repay the loan or we will send nude pics to contact list","loan_app_harassment","threat_reported","whatsapp",["short"],"reported threat (unsolicited 7-day loan)"),
("1605910041152065537","I will send dirty posts to your contacts","loan_app_harassment","threat_reported","voice_call",["short"],"reported threat (unsolicited credit)"),
# ---- e-challan ----
("1968643951985877110","Dear Vehicle Owner Pay your Challan No: VA190R0E58D3E061E9 online for continued services Ignore if already done Click A red signal violation recorded against your vehicle Password- https://t.co/yrPlvse3QF -action has been documented CABLEs","e_challan","quoted_scam_msg","sms",["link_redacted_tco"],"quoted spam SMS"),
("2042201919704469763","Traffic Violation by Your vehicle number XX Have Been Found Verify and Photographic Evidence click here: link","e_challan","quoted_scam_msg","sms",[],"reporter redacted number/link"),
("2013853454070874594","Your vehicle has been recorded for a traffic violation. Please click the link to resolve this matter and avoid legal risks.","e_challan","quoted_scam_msg","sms",[],"quoted SMS"),
("2009201717179760803","Your vehicle was identified for a traffic violation","e_challan","quoted_scam_msg","sms",["short"],"advisory_quote: CA awareness post quoting SMS"),
# ---- digital arrest / courier-customs ----
("1828439524638130641","some parcel has been sent by you from Delhi to Thailand and has been seized by Delhi customs. It has illegal things and if it doesn't belong to you then video call us and share your aadhar details","digital_arrest","call_script_reported","voice_call",[],"caller posed as Delhi cyber crime"),
("1664499623795519491","The Customs department has claimed that there are some illegal items & it seems your Aadhar ID has been used.","courier_fedex_drugs","call_script_reported","voice_call",[],"direct quote of agent"),
("1765970474713137446","your parcel has been seized by customs due some illegal things contains in it","courier_fedex_drugs","call_script_reported","voice_call",["typo_slang"],"indirect speech"),
("1674448506323623937","your consignment which was going to Taiwan from Mumbai is hold by Mumbai customs and they found some illegal things","courier_fedex_drugs","call_script_reported","voice_call",[],"indirect speech"),
# ---- romance (direct romance-bait spam; non-India unless noted) ----
("1891671729879040220","Hello dear i am single and I'm looking for a serious relationship if you are interested you can text me 💕","romance_pig_butchering","direct_spam_post","x_post",["emoji"],"bot reply template (one kept of ~19 identical)"),
("2055578972763619778","I am Single looking for a serious relationship, if you are interested please text me on WhatsApp +1 (530) 775‑9208","romance_pig_butchering","direct_spam_post","x_post",["non_india_locale"],"direct spam"),
("2086133411157045557","This is my username on my telegram please follow me I am looking for a serious relationship I am single and looking for a serious relationship follow me and message me on my telegram","romance_pig_butchering","direct_spam_post","x_post",[],"direct spam"),
("2031086097678152016","Hello dear nice meeting you I'm prince eze from Belgium and I'm a trader and an investor in cryptocurrency trading! I guess you have heard about cryptocurrency trade. Text me private","romance_pig_butchering","direct_spam_post","x_post",["non_india_locale"],"pig-butchering style opener"),
("1636087011923705856","Hello dear, I am 65yr widower medical doctor, very honest and trustworthy man settled in Agra looking for longterm relationship preferably. If interested kindly revert back with your face photograph and WhatsApp number. Thanks","romance_pig_butchering","direct_spam_post","x_post",[],"India; unsolicited mass replies (2 identical)"),
("1594773768932626442","hi dear dr Reem engineer ahmed searching fr a loving wife in Europe or Saudi if ready fr a man let’s talk thanks are you ready to marry ? You didn’t answer !! I am fr marriage only when ready call me Telegram","romance_pig_butchering","direct_spam_post","x_post",["non_india_locale","typo_slang"],"direct spam"),
# ---- job / task ----
("1699541309479178347","Life changing opportunity","job_task","direct_spam_post","x_post",[],"FULL"),
("1665922860542738432","I am HR Laila laghari from PUBLICIS (INDIA).","job_task","direct_spam_post","x_post",[],"FULL"),
("1722908862972608843","One mobile phone, one part time job at home, get Rs.300 to Rs.10,000 per day easily","job_task","direct_spam_post","x_post",[],"FULL"),
("1705905010205483161","If you need a part-time job, please contact us","job_task","direct_spam_post","telegram",[],"FULL"),
("1685003057665310720","Work from home job ..","job_task","direct_spam_post","x_post",[],"FULL"),
("1811657263683166640","Our company is now in need of an online branding position","job_task","direct_spam_post","x_post",["truncated"],"FULL"),
("1647293886187073536","Hi, I am the Human Resources Manager at Big Daddy Platform.","job_task","direct_spam_post","telegram",["emoji"],"FULL"),
("1642780791515275264","Earn from mobile in your spare time","job_task","direct_spam_post","x_post",["emoji"],"FULL"),
("1631967722967011328","Top most Achiver Daily income 40","job_task","direct_spam_post","x_post",["typo_slang"],"FULL; joining-fee"),
("1693231709482066282","Part time job & full time job available","job_task","direct_spam_post","x_post",[],"FULL"),
("1703089533255041242","DM ME","job_task","direct_spam_post","x_post",["emoji","short"],"FULL"),
("1678985282669117440","If you want a daily income with part time work","job_task","direct_spam_post","x_post",[],"FULL"),
("2074852658280804734","Hello, this is .....(,name). We are recruiting part-time staff","job_task","quoted_scam_msg","whatsapp",["truncated"],"FULL; pasted template"),
("1958437361479516308","We're hiring part-time online professionals.","job_task","direct_spam_post","whatsapp",[],"FULL"),
("1954134864065659229","Earn INR 620–1000 DAILY!","job_task","direct_spam_post","x_post",["emoji"],"FULL"),
("1929713988247462099","I am a HR Assistant from HUSTLE MARKETERS SCALING BUSINESSES ONLINE, India. The reason for contacting you is that our company is offering a part time online work from home job where you can earn","job_task","quoted_scam_msg","whatsapp",["truncated"],"received on WhatsApp"),
("1843222394300989783","Looking for : Freelancers/ Part timers","job_task","direct_spam_post","x_post",[],"FULL"),
("1802866435750085023","Struggling with single salary","job_task","direct_spam_post","x_post",["emoji"],"FULL"),
# ---- investment / trading ----
("1857963099313107149","Daily 3-5! Sure shot calls","investment_trading","direct_spam_post","telegram",[],"FULL; variants deduped"),
("1940055968227684770","Jackpot call","investment_trading","direct_spam_post","x_post",["emoji"],"FULL; 2X 3X guaranteed"),
("1872245754045337800","Banknifty premium group","investment_trading","direct_spam_post","telegram",["emoji"],"FULL; 100% accuracy"),
("2015720290568007766","Join our telegram chennal","investment_trading","direct_spam_post","telegram",["emoji"],"FULL; 90% accuracy"),
("1667243785238003712","Join our FREE telegram channel","investment_trading","direct_spam_post","telegram",[],"FULL; 20k-30k daily"),
("1674989066327298048","50k+ Profit","investment_trading","direct_spam_post","telegram",["emoji"],"FULL; sure shot"),
("1496303250882105346","Join the winning team where you can earn over $10.000 to $60.000 weekly guaranteed (Return on Investment). If interested, Dm @AkierraMolina she’s an expert trader and has been my account manager for years, she will help you make the right decision on the stock market.","investment_trading","direct_spam_post","x_post",["non_india_locale"],"account-manager recovery/ROI spam"),
("1486201646963208192","I will teach you to double your money.","investment_trading","direct_spam_post","telegram",["non_india_locale"],"FULL; Kenya"),
("2039614903229768074","8+ years of Forex trading experience | International portfolio management with 30% profit sharing | Delivering exceptional returns for investors Contact: ALGATAM@YAHOO.com | WhatsApp: 00966508857887","investment_trading","direct_spam_post","whatsapp",["non_india_locale"],"repeated 4x; one kept"),
]
# "FULL" note => use the whole post (cleaned: leading @mentions and trailing hashtags/links stripped); extract is only an anchor that must be present.

# News / advisory rows (verified by curl on 2026-10-29 IST against the live page)
NEWS = [
 dict(text="We are finding a very big loan fraud. Police are finding Ramesh Singh (name changed). He has taken a loan and gave your number as a guarantor.",
      scam_type="loan_app_harassment", modality="quoted_scam_msg", channel="sms", date="2020-05-04",
      source_url="https://inc42.com/buzz/digital-lenders-get-aggressive-as-loan-recovery-stalls-in-pandemic/", origin="news_quote",
      license="News article excerpt (Inc42), quoted for internal research/eval only; do not redistribute", note="message allegedly sent by Moneed; name changed by Inc42"),
 dict(text="Your Challan No. is …for vehicle number… having challan amount as Rs 500. For online payment of e-challan visit echallanparivahan.in. You can also contact RTO office for disposal of challan, Regards, RTO.",
      scam_type="e_challan", modality="quoted_scam_msg", channel="sms", date="2025-11-25",
      source_url="https://timesofindia.indiatimes.com/city/kolkata/articleshow/125570472.cms", origin="advisory_quote",
      license="News article excerpt (Times of India), quoted for internal research/eval only; do not redistribute", note="Kolkata Police cyber cell template ('will read something like this')"),
 dict(text="You are under [digital] arrest",
      scam_type="digital_arrest", modality="call_script_reported", channel="voice_call", date="2024-09-17",
      source_url="https://www.indiatoday.in/india-today-insight/story/why-indians-are-falling-easy-prey-to-digital-arrest-2601475-2024-09-17", origin="news_quote",
      license="News article excerpt (India Today), quoted for internal research/eval only; do not redistribute", note="caller's words to Lucknow doctor; [digital] is India Today's insertion"),
]
# Kaggle nikhilchauhan02 (CC BY 4.0) rows whose text matched the cited source page at fuzzy score >= 0.95 (ext/kaggle_verify.json)
KAGGLE_IDX = {728:"kyc_bank_pan",1792:"utility_disconnect",2474:"utility_disconnect",2800:"utility_disconnect",2274:"kyc_bank_pan",104:"courier_indiapost",2922:"job_task",1403:"job_task",1586:"kyc_bank_pan",1928:"lottery_kbc"}
for _t in ["The police will be coming in five minutes to arrest you. All police stations have been alerted",
           "I will try to talk and persuade them not to put you in physical custody. But you have to be in digital custody",
           "Take a deep breath and relax. You have not committed a murder. You have just laundered money."]:
    NEWS.append(dict(text=_t, scam_type="digital_arrest", modality="call_script_reported", channel="video_call", date="2024-11-18",
      source_url="https://www.bbc.com/news/articles/cdrdyxk4k4ro", origin="news_quote",
      license="News article excerpt (BBC News), quoted for internal research/eval only; do not redistribute", note="scammer lines to Lucknow doctor quoted by BBC"))
