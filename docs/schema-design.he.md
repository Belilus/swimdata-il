<div dir="rtl">

# תכנון הסכימה והנימוקים

גרסה באנגלית: [`schema-design.md`](schema-design.md)

ה־DDL הקנוני: [`sql/01_schema.sql`](../sql/01_schema.sql). מערכת היעד: **PostgreSQL** (אומת מקצה לקצה על DuckDB דרך `run_pipeline.py`).

הסבר עומק נוסף על כל טבלה: [`sql/README.he.md`](../sql/README.he.md).

## 1. מיחס רחב אחד ל־BCNF

כל PDF מקור הוא למעשה יחס רחב אחד. לדוגמה, גיליון התוצאות הוא:

<div dir="ltr">

```
RESULT_FLAT(event_no, distance, stroke, gender, age, heat, lane,
            last_name, first_name, birth_year, club_name, time, status, fina)
```

</div>

היחס הזה כפולי וחשוף לאנומליות: שם המועדון חוזר בכל שורת שחיין (אנומליית עדכון — משנים שם מועדון, נוגעים במאות שורות), תכונות המשחה חוזרות בכל שורת תוצאה, ואי אפשר לרשום מסלול במקצה לפני שיש זמן (אנומליית הכנסה). התלויות הפונקציונליות הן:

- `federation_code → club_name_he, club_name_en`
- `event_id → distance, stroke, gender, age_group, round`
- `(event_id, heat_no) → heat`
- `(heat_id, lane) → entry` וגם `entry_id → seed_time`
- `entry_id → result (place, time, status, fina)`
- `swimmer_id → last/first name (he/en), birth_year, club`

פירוק לפי התלויות האלה כך ש**כל דטרמיננטה היא מפתח** נותן את סכימת BCNF למטה (8 טבלאות ליבה + 2 נחיתה + 1 ערכים). כל עובדה נשמרת פעם אחת.

## 2. הטבלאות

| טבלה | גרעין (מהי שורה אחת) | מפתחות | הערות |
|-------|-------|--------|-------|
| `ref_stroke` | סגנון אחד | PK `stroke_code` | טבלת ערכים; יעד FK מ־`event` |
| `club` | מועדון אחד | PK `club_id`, **UNIQUE `federation_code`** | קוד האיגוד = עוגן פתרון הזהויות |
| `club_name_variant` | איות אחד שנצפה | PK `variant_id`, UNIQUE `(club_id, spelling, lang)` | שובל ביקורת לאיחוד כפילויות |
| `swimmer` | אדם אחד | PK `swimmer_id`, UNIQUE `(last_en, first_en, birth_year, club_id)` | מיושב על פני משחים |
| `competition` | אליפות אחת | PK `competition_id` | תאריכים, בריכה (LCM/SCM), עיר |
| `event` | שורת תוכנייה אחת | PK `event_id`, UNIQUE `(competition, distance, stroke, gender, age, round)` | FK → competition, ref_stroke |
| `heat` | מקצה אחד | PK `heat_id`, UNIQUE `(event_id, heat_no)` | FK → event |
| `entry` | מסלול רשום (זינוק) | PK `entry_id`, UNIQUE `(heat_id, lane)` | FK → heat, swimmer; `seed_time_ms` יכול להיות ריק (`NT`) |
| `result` | תוצאה במים | PK `result_id`, **UNIQUE `entry_id`** | FK → entry; זמן או סטטוס |

שרשרת הקינון במשפט אחד: תחרות מכילה משחים, משחה מכיל מקצים, מקצה מכיל רישומים למסלול, רישום מייצר תוצאה אחת. השחיין שייך למועדון. למועדון יש הרבה איותים שנצפו.

## 3. אילוצי שלמות (ולמה)

- **מפתחות ראשיים** על כל טבלה; **שבעה מפתחות זרים** אוכפים שלמות הפניה (אין תוצאה בלי רישום, אין רישום בלי מקצה/שחיין, וכו').
- **`UNIQUE (heat_id, lane)`** — מסלול אחד מחזיק שחיין אחד במקצה.
- **`UNIQUE result.entry_id`** — שחייה אחת מייצרת תוצאה אחת בדיוק (1:1).
- **אילוצי תחום `CHECK`** — `distance_m` ב־`{25,50,100,200,400,800,1500}`, `gender` ב־`{Girls,Boys,Mixed}`, `status` ב־`{DNS,DSQ,DNF,NS,SCR,WD}`, `birth_year` בטווח **1930–2020** (כולל מאסטרס; בנתונים יש יליד 1985), זמנים ונקודות חיוביים.
- **`CHECK` בין עמודות (כלל הערך החסר):** `result` דורש `final_time_ms IS NOT NULL OR status IS NOT NULL` — תוצאה היא תמיד זמן או סטטוס, אף פעם לא ריקה.

הגרסה האנגלית כותבת בטעות `[1990,2020]`. הסכימה האמיתית ב־`01_schema.sql` היא `BETWEEN 1930 AND 2020`.

## 4. בחירת אינדקסים (לפי עומס העבודה)

ראו [`sql/05_indexes_explain.sql`](../sql/05_indexes_explain.sql). מסווג לפי ששת ממדי Server1:

| אינדקס | מפתח חיפוש | סיווג | משרת |
|-------|-----------|----------------|--------|
| `idx_result_time` | `final_time_ms` | משני, לא מקובץ, צפוף, עמודה אחת, עץ B+ | דירוג Q1/Q4, `ORDER BY time LIMIT` |
| `idx_swimmer_name` | `(last, first, birth_year)` | משני, לא מקובץ, צפוף, **מורכב (הסדר חשוב)**, עץ B+ | חיפוש שחיין באפליקציה (קידומת) |
| `idx_result_fina` | `fina_points` | עץ B+ משני | "השחיות הטובות בתחרות" |
| `idx_entry_swimmer`, `idx_entry_heat`, `idx_heat_event`, `idx_event_lookup` | עמודות FK | עץ B+ משני | מאפשרים צירוף לולאה מקוננת עם אינדקס (Server4) |

זמנים נשמרים כ־**אלפיות שנייה שלמות** כדי שהאינדקסים יהיו קומפקטיים והמיון מדויק; העיצוב האנושי `mm:ss.hh` קורה רק בתצוגה `v_fmt`.

## 5. החלטות שכדאי להגן עליהן בפגישה

1. **זהות מועדון = קוד האיגוד, לא השם.** השמות מלוכלכים (ארבעה איותים של "מכבי"); הקוד המספרי מרשימת הזינוק יציב וניטרלי לשפה.
2. **פיצול `entry` (רשום) מ־`result` (שחו).** ממodel בכנות "נרשם אבל DNS", ומשאיר זינוק מול גמר כשתי עובדות ממדרגה ראשונה.
3. **טבלת ביקורת `club_name_variant`.** פתרון זהויות צריך להיות *שקוף והפיך*, לא קופסה שחורה — אפשר להראות בדיוק איזה איות מופה לאן.
4. **טבלאות הנחיתה כולן `TEXT`.** ערכים מלוכלכים (`NT`, `DQ / SW 4.4`, שמות מועדון שנשברו) נוחתים בלי ליפול; הניקוי והטיפוס קורים ב־`03_transform.sql`.
5. **גשר המקורות הוא `LEFT JOIN`, לא `RIGHT JOIN`.** התוצאות הן העובדה הרשמית; רשימת הזינוק מעשירה. 29 שורות בלי התאמה נשמרות עם `NULL`. `RIGHT JOIN` היה מכניס נרשמים בלי שורת תוצאות — מחוץ לגרעין הטעינה.

</div>
