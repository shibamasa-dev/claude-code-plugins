---
name: employee-certificate
description: Fills the certificates a Japanese company issues to an employee, mainly the employment certificate (就労証明書) parents attach to nursery or after-school applications, on the municipality's latest Excel form (the standard layout of the Children and Families Agency or a local variant), plus proof of enrolment (在籍証明), separation certificates (退職証明書, only the items asked, per Labour Standards Act Art. 22) and proof of income (収入証明). Finds the latest form, maps cells by item label rather than address, fills them from the user's company and employee files and last year's copy, asks only what the person alone knows, then reads the saved file back. Use whenever someone needs one of these filled, renewed or checked, or in Japanese 「就労証明書を書いて」「就労証明書の作成」「保育園の就労証明」「学童の就労証明」「現況届の就労証明」「在籍証明書を出して」「退職証明書を発行」「収入証明を作って」「給与支払証明書」「去年の就労証明を今年の様式で」.
last_reviewed: 2026-11-24
review_after: 2027-05-24
---

# Employee certificates (Japan)

Fill a certificate the employer issues, on the form of whoever asked for it, without inventing anything. Japan-specific: the forms, laws and terms are Japanese.

The filling is done by `scripts/certfill.py` (Python 3.9+, standard library only). It finds cells by their item label, so last year's mapping still works when the municipality shifts the layout, and it edits only the target cells, so the form's dropdowns and checkboxes survive. Run it as:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/employee-certificate/scripts/certfill.py" <command> ...
```

Read [references/spec-format.md](references/spec-format.md) before writing the first spec of a session.

## Where the data lives

Company folder: `${user_config.company_dir}`. A value that still reads as a `${user_config...}` placeholder, or an empty one, means `~/.claude/company`. Nothing about the company, its people or the municipalities is kept in this plugin.

| File | Holds |
|---|---|
| `<company folder>/company.md` | Company details every department plugin shares: legal name, representative, address, phone, industry |
| `<company folder>/hr/employees/<key>.md` | One employee: name and reading, birth date, hire date, contract type, working hours |
| `<company folder>/hr/municipalities/<name>.md` | Notes per municipality or requester: where the form is, deadline, how to submit |
| `<company folder>/hr/issued/<year>/` | Copies the user kept of earlier certificates, with the spec used to fill them |

Layouts and templates are in [references/data-files.md](references/data-files.md). If a file is missing, say which one and offer to create it from the template with the values the user gives you. Don't create it unasked, and never fill a gap with a plausible guess.

## Steps

1. **Pin down the request.** Which certificate, for which employee, for whom (municipality, school, landlord, the employee), and by when. For a separation certificate, also which items the employee asked for (step 1 of [references/other-certificates.md](references/other-certificates.md)).

2. **Get the latest form and its rules.** Read the requester's notes in `hr/municipalities/` first. Then find the current form on the requester's own website, check the fiscal year or revision date on the page, and tell the user the URL and date before downloading. Ask the user for the file when the site needs a login, has only a PDF or paper form, or you cannot tell which form is current. How to search: [references/data-files.md](references/data-files.md#finding-the-latest-form). A requester with no form of its own: [references/other-certificates.md](references/other-certificates.md). Read the form's own instructions every year as well (the `記載要領` sheet, and any guidance PDF on the same page): rules such as the order of the work-record months, whether hours include breaks, or which certification dates are accepted are set there and can change, and last year's copy may have followed them wrongly.

3. **Map the form.** Run `inspect FORM` and match its items to the standard layout in [references/standard-form.md](references/standard-form.md). Never reuse cell addresses from last year's notes or memory; they drift and are easy to get wrong. Write a spec (JSON) that locates every field by item label and, inside the item, by a nearby text (`right_of`, `left_of`, `below`, `check`). Run `read FORM SPEC`: every field must resolve to the empty input you meant. An error naming candidates means a label repeats; add `nth` or `item_nth` rather than guessing.

4. **Fill in what is known.** Values come from three places, in this order:
   - the company and employee files;
   - last year's copy: run `read LAST_YEAR.xlsx SPEC` with this year's spec (or last year's spec from `hr/issued/`). Carry over values that do not change from year to year (company, name, birth date, hire date, contract type, hours) and show the user what you carried over. Never carry over the work record or the certification date, and when last year's copy and its notes disagree, ask instead of picking one;
   - nothing else. A value with no source is a question for step 5, not a blank you fill with a likely answer.

5. **Ask for what only the person knows**, in one list, and wait for the answers:
   - the certification date (証明日), within the window the requester accepts (some accept any date from a fixed day of the year for a current-status report; say which window applies);
   - the last three months of the work record (就労実績): days and hours per month for the months actually worked (not the pay months), paid leave counted as days, breaks and overtime counted as hours. The standard instructions put the newest month in the first column;
   - the employment type when it is not plain employment: a company's representative director is usually an officer (`役員`), not self-employed (`自営業主`), but the notes rarely say, so ask;
   - leave taken or planned, and short-hours arrangements, if any;
   - the children and the facility, if the form has a guardian section (保護者記載欄), and whether the children's birth years go in the Western or the Japanese calendar when the form doesn't say;
   - text the form came with in an input (a sample sentence in the remarks, a printed addressee): keep it or clear it. Clearing is a field with `"value": ""` and `--overwrite`;
   - anything the employee file leaves open, and anything that differs from last year.

6. **Fill and save.** Run `fill FORM SPEC OUT`. It writes a copy and never changes FORM. It refuses a cell that already holds a value; pass `--overwrite` only when you mean to replace it. Name OUT after the certificate, the employee key and the date, and save it in the folder the user names (default: the working folder).

7. **Read it back.** Run `verify FORM OUT SPEC`. Every check must say `ok`: each value is where its label says, no other cell changed, the dropdowns and merged cells are all still there. Show the user a short table of item → value, and link the file. If a check fails, fix the spec and fill again; never hand over a file that failed.

8. **Hand over.** Saving the final copy, stamping it if the requester wants a seal, and submitting it are the user's job. Remind them of the requester's notes (deadline, submit through the facility, no mail) and suggest keeping the file and its spec in `hr/issued/<year>/` so next year starts from them. If you learned something new about the requester (a new form URL, a deadline), offer to add it to its notes file.

## Cautions

- A certificate is a statement of fact. Writing something false or altering it without the employer's consent can be a crime, as the standard form itself warns. When a value is unclear, ask; don't round it to what the requester probably wants.
- Personal data (the employee's and the children's) stays in the user's files and the filled form. Don't paste it into issues, commits or other tools, and don't put it in URLs or search queries.
- `certfill.py` fills `.xlsx` only. For `.xls`, ask the user to save it as `.xlsx` (Excel or LibreOffice) first; for a PDF-only form, list the values for the user to write by hand.
