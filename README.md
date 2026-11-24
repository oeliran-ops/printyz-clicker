# PRINTYZ Clicker Studio

מחולל פרמטרי לקליקרים מכאניים (מתגי MX) בהדפסת תלת־ממד — עברית ואנגלית, הדפסה מרובת צבעים ל־Bambu Lab A1 + AMS.

## התקנה (Windows)
```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
```

## שימוש (שלב 1 – שורת פקודה)
```
python -m printyz_clicker build --text "שלום" --keychain top
python -m printyz_clicker build --text Daniel --layout grid --rows 2 --cols 3 --cap-color "#1E5BD8" --legend-color "#FFD400"
python -m printyz_clicker build --text WASD --layout wasd --mode raised --keycap thocky
```
הפלט נשמר ב־`Projects/<שם>/`: קובץ פרויקט JSON, ותיקיית `Exports` עם STL, STEP, ‏3MF, דוח בדיקות ותמונות תצוגה.

## בדיקות
```
python -m pytest -q
```
ראו `docs/ARCHITECTURE.md` לסטטוס מול האפיון.
