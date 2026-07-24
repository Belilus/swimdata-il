# SwimData-IL — מדריך הגשה / Submission guide

**סטודנט:** Asaf Belilus  
**קורס:** ניהול נתונים, אוניברסיטת בן-גוריון, אביב 2026  
**מרצה:** Yuval Moskovitch  
**משקל:** 40%

## קישור לריפו

**https://github.com/Belilus/swimdata-il**

> הריפו פרטי (`private`). לצורך בדיקה — הוסיפו את המרצה/בודק כ-collaborator,
> או הפכו ל-public לפני ההגשה.

## מה מוגש

| פריט | מיקום |
|------|--------|
| דוח (≤5 עמודים) | [`report/report.md`](report/report.md) |
| הצעת פרויקט | [`proposal/proposal.md`](proposal/proposal.md) |
| סכימת DB + SQL | [`sql/`](sql/) |
| קוד ETL + אפליקציה | [`src/`](src/) |
| מפת מושגי קורס | [`docs/course-concept-map.md`](docs/course-concept-map.md) |
| הדגמה (2 דקות) | [`DEMO.md`](DEMO.md) |

## הרצה מקומית (פקודה אחת)

```bash
git clone https://github.com/Belilus/swimdata-il.git
cd swimdata-il
python3 -m pip install -r requirements.txt

# הורידו את PDFי התחרות מ-loglig (קישורים ציבוריים ב-ISA) ל-samples/:
#   results_youth_south_summer2026.pdf
#   startlist_youth_south_summer2026.pdf
#   results_seniors_winter2025.pdf

bash build.sh
open web/dashboard.html          # דשבורד (בונוס)
python3 src/app.py               # אפליקציית שאילתות (דרישת הקורס)
```

`build.sh` מייצר: DB מנורמל (4,770 שחיות), דשבורד, `docs/sample-query-output.txt`
(מקומי בלבד — לא ב-git), ו-`swimedge_bundle.json` (הדגמת תאימות ל-SwimEdge).

## פרטיות

שמות שחיינים (כולל קטינים) **לא** נשמרים ב-git. רק קוד, סכימה, דוחות, ו-PDF תקנון
ללא נתונים אישיים. הנתונים נבנים מחדש מ-PDF ציבוריים של איגוד השחייה.

## קשר ל-SwimEdge (בונוס, לא תלות)

הפרויקט עצמאי לחלוטין. [`docs/swimedge-sync.md`](docs/swimedge-sync.md) מתעד
שהסכימה מתכנסת למוצר SwimEdge (פרויקט נפרד). שיטת הפרסור הגיאומטרית ממנה נולדה
הועתקה ל-SwimEdge; שם נוספו מאז results ingestion מלא (`IndividualResultRow`,
`MeetResultsImportService`) — מחוץ לסקופ הקורס.
