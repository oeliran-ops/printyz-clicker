# PRINTYZ Clicker Studio

מחולל פרמטרי לקליקרים מכאניים (מתגי MX) בהדפסת תלת־ממד — עברית ואנגלית, הדפסה מרובת צבעים ל־Bambu Lab A1 + AMS.

## התקנה (Windows)
דרוש **Python 3.13** (או 3.12). ‏Python 3.14 עדיין לא נתמך על ידי ספריית התלת־ממד.
הסביבה נוצרת מחוץ ל־OneDrive כדי שלא יסונכרנו מאות MB של ספריות:
```
py -3.13 -m venv $env:LOCALAPPDATA\PRINTYZ\ClickerV2\.venv
$py = "$env:LOCALAPPDATA\PRINTYZ\ClickerV2\.venv\Scripts\python.exe"
& $py -m pip install -r requirements.txt
& $py -m pip install -e .
```
ב־Terminal חדש מגדירים שוב את `$py` לפני שאר הפקודות.

## הפעלת התוכנה (ממשק גרפי)
```
& $py -m printyz_clicker.ui
```

## שימוש משורת הפקודה
```
& $py -m printyz_clicker build --text "שלום" --keychain top
& $py -m printyz_clicker build --text Daniel --layout grid --rows 2 --cols 3 --cap-color "#1E5BD8" --legend-color "#FFD400"
& $py -m printyz_clicker build --text WASD --layout wasd --mode raised --keycap thocky
```
הפלט נשמר ב־`Projects/<שם>/`: קובץ פרויקט JSON, ותיקיית `Exports` עם STL, STEP, ‏3MF, דוח בדיקות ותמונות תצוגה.

## בדיקות
```
& $py -m pytest -q
```
ראו `docs/ARCHITECTURE.md` לסטטוס מול האפיון.
