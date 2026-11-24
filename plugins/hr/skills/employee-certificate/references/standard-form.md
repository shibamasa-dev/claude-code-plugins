# The standard employment certificate (就労証明書)

The Children and Families Agency publishes a standard layout of the employment certificate used for nursery and after-school applications, and asks municipalities to use it in principle (Cabinet Office Order No. 84 of 2024). Source page: https://www.cfa.go.jp/policies/hoiku/shugyoshomeisho (the Excel form, a simplified version, and the lists of municipalities that use it and that require a seal).

Most municipalities use it, but each one may add rows (a submission address, its own notes), widen columns or change wording from year to year. That is why fields are located by label: match the items below to whatever the municipality's form prints, and check with `read` before filling.

The Excel file has three sheets: the form, a sheet of dropdown lists, and `記載要領` (how to fill each item). When an item is unclear, read `記載要領` with `inspect FORM --sheet 記載要領`; the municipality's version of that sheet wins over this page.

## Header (the issuer)

| Label | Source | Notes |
|---|---|---|
| `宛` | municipality notes | The addressee, usually the mayor of the municipality the applicant lives in |
| `証明日` | ask | The date of issue, Western calendar |
| `事業所名` | company.md | The legal name of the issuer (the organisation responsible for the certificate) |
| `代表者名` | company.md | The representative, or the person the company authorises to certify |
| `所在地` | company.md | The issuer's address, not the employee's workplace |
| `電話番号` | company.md | Three inputs separated by dashes |
| `担当者名` / `記載者連絡先` | company.md or ask | Who the municipality may call about the certificate |

## Items 1 to 19

| No. | Label | Source | Notes |
|---|---|---|---|
| 1 | `業種` | company.md | One checkbox; `その他（ ）` with text when none fits |
| 2 | `フリガナ` / `本人氏名` / `生年月日` | employee file | The birth date sits in the `本人氏名` row: use `{"item": "本人氏名", "date": ...}` |
| 3 | `雇用(予定)期間等` | employee file | `無期`: start date only. `有期`: start and end (`nth` 1 and 2) |
| 4 | `本人就労先事業所` | employee file | Name and address only when the employee works somewhere other than the issuer's address |
| 5 | `雇用の形態` | employee file, confirm | Officers (`役員`) and the self-employed (`自営業主`, `自営業専従者`, `家族従業者`) are their own options; ask when the file doesn't say |
| 6 | `就労時間(固定就労の場合)` | employee file | Weekday checkboxes (`below` the day), monthly total and breaks, days per month and week, start and end times on weekdays, Saturdays, Sundays and holidays |
| 6 | `就労時間(変則就労の場合)` | employee file | For shift work without fixed hours: monthly or weekly total, days, the main shift |
| 7 | `就労実績` | ask | The last three months: days per month (paid leave counted as worked days) and hours per month (breaks and overtime included). If leave covers those months, the three months before the leave |
| 8 | `産前･産後休業の取得` | ask | Planned or current, with the period |
| 9 | `育児休業の取得` | ask | Planned, current or finished, with the period |
| 10 | `産休・育休以外の休業の取得` | ask | Reason and period |
| 11 | `復職（予定）年月日` | ask | Planned or done, with the date |
| 12 | `育児のための短時間勤務制度利用有無` | ask | Planned or current, period and the shortened hours |
| 13 | `保育士等としての勤務実態の有無` | employee file | Whether the person works as a nursery teacher or similar |
| 14 | `（雇用契約の）満了後の更新の有無` | employee file | Fixed-term contracts only |
| 15 | `入所内定時育休短縮可否` | ask | Whether the leave can end early if a place is offered |
| 16 | `育休延長可否` | ask | Whether the leave can be extended |
| 17 | `単身赴任期間（予定含む）` | ask | Leave the end blank when it is open |
| 18 | `備考欄` | ask | Anything the items above can't carry, for example required early arrival |
| 19 | `保護者記載欄` | ask | Children's names, birth dates, facility, in use or applied for. Written by the guardian; fill it only when the user (who is that guardian) gives the values |

Items 8 to 17 stay blank when they don't apply. Don't tick a box to say "not applicable" unless the form has that option.

## Simplified version

The same page publishes a simplified version (`簡易版`) with the same labels and fewer rows; some municipalities use it or a variant of it. Map it the same way. A spec written for one version usually resolves on the other; run `read` to confirm.
