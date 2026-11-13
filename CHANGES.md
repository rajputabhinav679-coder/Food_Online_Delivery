# Changes in this corrected package

- Kept the object-oriented Streamlit application and existing dashboards.
- Kept the configurable Cafe Owner login; the owner email/password are read from
  Streamlit Secrets or environment variables instead of hard-coded credentials.
- Order notification flow is explicitly e-mail based:
  - New customer order -> configured Cafe Owner e-mail.
  - Cafe Owner confirms -> all active Delivery Boy accounts with e-mail addresses.
- Delivery Boy confirmation e-mail now includes customer contact number and
  delivery address, as well as the ordered food and payment information.
- Fixed newline formatting in the customer order receipt.
- Cafe Owner email panel shows the actual notification recipients, provides a
  test-mail button, and displays SENT / FAILED / SKIPPED logs.
- No SMS or WhatsApp integration is included. SMS would require a separate
  provider account/API.
- The real `.streamlit/secrets.toml` file is intentionally not included.

## Update 6 (customer order numbers)
- Customer dashboard ab har customer ke apne hisaab se order number dikhata hai: customer ka pehla order #1, doosra #2 ...
  (pehle poore system ka number dikhta tha, isliye naye customer ko bhi #10 dikhta tha).
- Customer ko jaane wali receipt mail aur status pop-up me bhi wahi customer wala number aata hai.
- Cafe owner aur delivery boy ko abhi bhi poore system ka number dikhta hai (jaise #11). Ek hi order ka number customer ke liye #2 aur cafe ke liye #11 ho sakta hai.
- LOGIN_AND_NOTIFICATIONS_SETUP.txt se owner ka plain-text password hata diya gaya (password sirf .streamlit/secrets.toml me hai).

## Update 7
- Naam me ek se zyada space (jaise "Ram  Kumar") allowed nahi: registration, delivery boy banate waqt aur checkout me.
  Naam ke aage-peeche ka space automatically hat jaata hai; do words ke beech sirf ek space chalta hai.
- Password eye icon se dikhane par 5 second baad apne aap hide ho jaata hai (`auto_hide_passwords` in ui/navigation.py;
  app.py me call hota hai). Time badalne ke liye `auto_hide_passwords(5)` ka number badlo.
- Saari .py files ki extra lines hata di gayi (khali lines, ==== wali comment lines, bracket me tuti hui lines jodkar,
  SQL ko clause-wise chhota karke). Code ka kaam bilkul same hai (7371 -> 4500 lines).

## Update 8 (Forgot Password + Change Password)
- **Change Password**: login ke baad sidebar me "Change Password" (current + new + confirm). Sabhi roles ke liye.
- **Forgot Password**: login page par "Forgot password?" / "Forgot Password" tab. Registered email par 6-digit OTP jaata hai
  (10 minute valid, 5 galat try ke baad band, 1 minute me ek hi OTP). OTP database me hash karke rakha jaata hai.
  Email registered ho ya na ho, screen par same message aata hai (koi pata nahi laga sakta kaun registered hai).
- Password badalne par account ke saare saved sessions band ho jaate hain aur "password changed" security mail jaati hai.
- Password rule: 6 se 64 characters (`validate_password` in utils/validators.py).
- Owner password ab sirf pehli baar account banate waqt secrets.toml se aata hai. Pehle har start par secrets wala
  password wapas set ho jaata tha, to app me badla hua password restart par ud jaata. Password bhool jaao aur email setup na ho
  to secrets.toml me `[auth] reset_cafe_password = true` ek baar lagakar restart karo.
- Code se hard-coded default owner password hata diya gaya (password ab sirf secrets.toml / environment se).

## Update 9 (OTP by SMS)
- Forgot Password me ab "📧 Registered E-mail" ya "📱 Registered Mobile (SMS)" chunna padta hai.
  Mobile chunne par OTP us account ke registered mobile number par SMS se jaata hai (Fast2SMS OTP route).
- Customer ko koi 2-step verification / App password nahi karna. Wo sirf cafe ke sender Gmail (email OTP ke liye) par lagta hai.
- SMS ke liye `.streamlit/secrets.toml` me `[sms] api_key` bharo (Fast2SMS: KYC + Rs.100 wallet recharge chahiye).
- Safety: ek ghante me max 30 SMS, ek account ko 1 minute me ek OTP, SMS log me number masked (98******09).
- Ek hi mobile number do accounts par ho to SMS reset nahi hota (email se karo).

## Update 10 (Forgot Password only for admin)
- Forgot Password (email / SMS OTP) ab sirf Cafe Owner (admin) ke liye hai. Customer aur Delivery Boy ko OTP nahi jaata;
  login ke baad wo "Change Password" use kar sakte hain. Forgot Password page par ye likha dikhta hai.
- Badalna ho to `config/app_config.py` me `FORGOT_PASSWORD_ROLES = ("cafe",)` me "customer", "delivery_boy" jod do.
- Owner ke SMS OTP ke liye `.streamlit/secrets.toml` me `[auth] cafe_phone = "10-digit number"` bharna zaroori hai (abhi khaali hai).

## Update 11 (names in CAPITAL letters)
- Teeno dashboards (Customer, Cafe Owner, Delivery Boy) aur sidebar me user ka naam hamesha BADE AKSHARON me, ek space ke saath dikhta hai
  ("  ram     kumar " -> "RAM KUMAR"). Customer ka naam cafe/delivery dashboard me, delivery boy ka naam customer/cafe me aur feedback me bhi aise hi dikhta hai.
- Naye registration / delivery boy / checkout name ab database me bhi capital letters me save hote hain (`validate_name`).
  Purane accounts ka naam waise hi rehta hai, par screen par capital me dikhta hai (`display_name` in utils/validators.py).

## Update 12 (report download)
- Daily aur Monthly report ab Excel (.xlsx) me download hoti hai, columns ki width apne aap badi hoti hai, isliye date "########" nahi dikhti.
  (CSV me Excel ka default column chhota hota hai, isliye date ### dikhti thi.) `openpyxl` requirements.txt me jod diya gaya.

## Update 13 (security: items 1, 2, 4, 8)
1. **Salted password hash**: password ab PBKDF2-SHA256 (600000 rounds, random salt) se save hota hai. Purane SHA-256 hash wale
   accounts bina kuch kiye chalte hain aur login karte hi apne aap naye hash me badal jaate hain.
2. **Login lockout**: 5 galat password ke baad us email se login 15 minute ke liye band (sahi password bhi nahi chalta).
   Unknown email par bhi wahi hota hai. Screen par "Too many wrong attempts. Try again after N minute(s)." dikhta hai.
4. **Delivery boys ko customer ki details nahi**: confirm mail aur "Available Orders" me sirf food, amount aur area ("CITY - PIN") dikhta hai.
   Customer ka naam, mobile aur poora address order accept karne ke baad hi (My Deliveries me) dikhta hai. Cafe owner ki mail me address/mobile rehta hai.
8. **Owner password reset**: Cafe dashboard -> "Customers" tab (naya) aur "Delivery Boys" tab me "Reset password". Temporary password banta hai
   (sirf ek baar dikhta hai), user ke purane sessions band hote hain aur agle login par naya password chunna padta hai.

## Update 14 (removed features + fixes)
- **Forgot Password poori tarah hata diya**: login page ka tab/button, OTP (email + SMS), SMS service, `[sms]` setting, OTP database table.
- **Owner ka "Reset password"** aur "Customers" tab hata diya, saath me "temporary password / naya password chuno" wali screen bhi.
  (Ab password sirf login ke baad "Change Password" se badalta hai.)
- **Order Management se "Order Email Notifications (setup & log)" panel hata diya.** Email notifications (naya order, confirm, receipt) pehle jaisi chalti hain.
- **Excel error theek**: "No module named openpyxl" ab nahi aata. Report ki Excel file ab Python ke apne modules se banti hai (kuch install nahi karna),
  `openpyxl` requirements se hata diya.
- **Helpline 9263747538** teeno dashboards me upar dikhta hai (tap karke call). Number badalna ho to `config/app_config.py` me `HELPLINE_NUMBER`.
- Password ka salted hash, 5-galat-try lockout, delivery boys ko customer ki details na dikhna, naam capital me, wagairah pehle jaisa hi hai.

## Update 15 (bug fixes, text, clean-up, tests)
**Bugs theek kiye**
1. Order ke time daam aur availability menu se dobara padhi jaati hai. Daam badla ho to customer ko batata hai ("price changed ... cart updated") aur naye daam par dobara order karna padta hai.
2. Unavailable ya delete hua item order nahi hota; saaf message aata hai ("Not available now: ...").
3. Status sirf aage badhta hai (peeche nahi). OUT FOR DELIVERY / DELIVERED tabhi jab Delivery Boy ne order accept kiya ho.
4. Delivery Boys ko mail sirf ek baar jaati hai (jab order PLACED se aage badhta hai).
5. Database WAL mode me (aur 30 second wait): "database is locked" ka khatra kam.
**Text**
6. Raw code ("CASH_ON_DELIVERY", "OUT_FOR_DELIVERY", "PLACED", "Role: DELIVERY_BOY") ki jagah "Cash on Delivery (COD)", "Out for Delivery", "Placed", "Delivery Boy".
7. Ek jaisi spelling: Email, Delivery Boy, Cafe Owner, Food Online Cafe, rupee ₹ (mail me bhi). "his/him" hata kar neutral shabd. Name ke message se "(A-Z)" hata.
8. Text size: `ui/styles.py` me ek jagah (BASE_FONT_REM, SMALL_FONT_REM, LABEL_FONT_REM, METRIC_FONT_REM). Number badal kar chhota/bada karo.
**Faltu code hataya**: purane session functions + user_sessions table, purane monthly graph functions, api/ folder, session_manager, unused models, unused packages (requests, plotly, cookies-manager).
**Tests**: `tests/test_app.py` (18 tests). Chalane ke liye project folder me:  python -m unittest discover -s tests -v   (kuch install nahi karna).
