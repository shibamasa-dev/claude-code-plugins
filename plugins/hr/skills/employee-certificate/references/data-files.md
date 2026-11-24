# The user's data files

Everything about the company, its employees and the requesters lives in the company folder on the user's side (`company_dir`, default `~/.claude/company`), never in the plugin. Uninstalling the plugin leaves the folder alone. The files are Markdown with one `key: value` per line, so the user can read and edit them; keep the keys below and add others freely.

```text
<company folder>/
├── company.md                    shared by every department plugin
└── hr/
    ├── employees/<key>.md        one per employee; <key> is any short id the user picks
    ├── municipalities/<name>.md  one per municipality or other requester
    └── issued/<year>/            filled certificates the user decided to keep, each with its spec
```

Create a file only when the user agrees, with values the user gives you. Write `[TODO: ...]` for what they don't know yet rather than a guess.

## company.md

```markdown
# Company
legal_name:
representative_title:
representative_name:
postal_code:
address:
phone:
industry:          # one option of item 1 of the standard form, or "other: <text>"
contact_name:      # who requesters may call about certificates
contact_phone:
```

Other department plugins read the same file, so keep it to company-wide facts.

## hr/employees/&lt;key&gt;.md

```markdown
# Employee
name:
name_kana:
birth_date:              # YYYY-MM-DD
hire_date:               # YYYY-MM-DD
contract: indefinite     # or fixed: <start> to <end>, renewal: yes / likely / no / undecided
employment_type:         # as item 5 of the standard form prints it
workplace_name:          # only when it differs from company.md
workplace_address:
schedule: fixed          # or shift
weekdays:                # e.g. Mon Tue Wed Thu Fri
hours_weekday:           # e.g. 09:00-18:00, break 60
hours_saturday:
hours_sunday_holiday:
monthly_hours:
days_per_month:
days_per_week:
nursery_teacher: no
notes:
```

Monthly work records (item 7), leave and children are not kept here: they change every time, so they are asked for each certificate.

## hr/municipalities/&lt;name&gt;.md

One file per requester: a municipality, a school, a landlord.

```markdown
# <requester>
addressee:           # what goes after 宛 on the form
form_page:           # the page the form is downloaded from
form_checked:        # YYYY-MM-DD and the revision or fiscal year shown on that page
seal: required / not required / unknown
submit: through the facility / by the applicant / online / by mail
deadline:
certification_date:  # which dates are accepted, e.g. within 3 months of the application
work_record:         # the requester's rules, e.g. newest month first, hours include breaks
notes:               # anything else: original only, no mail, extra sheets
```

### Looking up the notes

1. List `hr/municipalities/` and pick the file for the requester. Names are what the user calls the requester; when unsure, show the list and ask.
2. Read it before searching the web: `form_page` is the place to look first, and `form_checked` tells you whether last year's form may already be replaced.
3. Tell the user about `seal`, `submit` and `deadline` at hand-over.
4. When you learn something new, offer to update the file; write only what the user confirms.

## Finding the latest form

1. Start from `form_page` in the notes. If it is gone or there are no notes, search the requester's own website for the form name and the year, for example `<municipality> 就労証明書 <fiscal year>`. Use only the requester's official domain (for a municipality, usually under `lg.jp` or the city's own domain) or the Children and Families Agency page.
2. Check that the form is for the right fiscal year or admission period and look for the revision date on the page. Several forms on one page (new application, current-status report `現況届`, after-school club) are different forms: ask which one when unsure.
3. Before downloading, tell the user the URL, the file name and why you think it is current. Save it in the working folder and never edit the downloaded file itself.
4. If the page offers only a PDF or paper form, or the municipality has not adopted the standard layout (the agency's page lists which have), say so: fill by hand from a list of values instead.

## issued/&lt;year&gt;/

The user keeps final copies here if they want to. Store the spec next to each filled file (`<file>.spec.json`): next year it is the starting mapping, and `read` with it on this file gives the values to carry over. The spec holds personal values; keep it only in this folder.
