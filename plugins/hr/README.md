# hr

English | [日本語](README.ja.md)

**Japan-specific.** HR and labour admin skills for companies in Japan: the forms, laws and terms are Japanese. Currently one skill, `employee-certificate`, which fills the certificates a company issues to an employee.

## Install

```text
/plugin marketplace add shibamasa-dev/claude-code-plugins
/plugin install hr@shibamasa-plugins
```

Then create your company folder (see Configuration). The skill offers to create the files from templates the first time it needs them.

## Skills

| Skill | Use it for |
|---|---|
| `employee-certificate` | The employment certificate (就労証明書) parents attach to nursery or after-school applications, proof of enrolment (在籍証明), separation certificates (退職証明書) and proof of income (収入証明). The work is done by `skills/employee-certificate/scripts/certfill.py` (Python, standard library only) |

## How employee-certificate works

1. Finds the latest form of whoever asked for the certificate: the requester's notes first, then its own website. It tells you the URL and date before downloading. Most municipalities use the standard layout of the Children and Families Agency, with small changes each year.
2. Maps the form by item label, not by cell address (`certfill.py inspect` and `read`), so last year's mapping still works after a layout change.
3. Fills what it can from your company and employee files and from last year's copy, and tells you what it carried over.
4. Asks, in one list, for what only you know: the certification date, the last three months of the work record, the employment type when it is not plain employment, leave, the children and the facility.
5. Writes a filled copy (`certfill.py fill`) that changes only the target cells, so the form's dropdowns and checkboxes survive, then reads it back (`certfill.py verify`): every value where its label says, nothing else changed.
6. Hands the file to you. Saving the final copy, sealing it and submitting it are yours.

A separation certificate holds only the items the employee asked for (Labour Standards Act, Article 22(3)).

## Configuration

`userConfig` keys, set when you enable the plugin or later with `/plugin`:

| Key | Default | Meaning |
|---|---|---|
| `company_dir` | empty (`~/.claude/company`) | Your company folder |

### Where files go

| What | Where |
|---|---|
| Company details shared by every department plugin | `<company_dir>/company.md` |
| Employees | `<company_dir>/hr/employees/<key>.md` |
| Notes per municipality or requester (form page, deadline, how to submit) | `<company_dir>/hr/municipalities/<name>.md` |
| Copies you keep of issued certificates, with the mapping used | `<company_dir>/hr/issued/<year>/` (optional) |
| Downloaded forms and filled drafts | the working folder, or a folder you name |

The plugin keeps no data of its own: nothing goes to the plugin data directory, and uninstalling removes nothing of yours. The company folder sits outside every plugin so that other department plugins can read the same `company.md`. File templates are in `skills/employee-certificate/references/data-files.md`.

## Scope: hr and finance

Whoever issues the paper decides where it belongs. Certificates a company issues to its employees, and collecting the employees' year-end adjustment paperwork, belong in `hr`. Bookkeeping and filings with the tax office will belong in a future `finance` plugin.

## Limitations

- `.xlsx` forms only. Save an `.xls` form as `.xlsx` first. A PDF-only or paper form gets a list of values to write by hand.
- Labels are matched exactly (after NFKC normalization and without spaces), then by unique prefix. A municipality that renames an item needs the new label in the mapping; `read` reports it rather than guessing.
- Finding the form depends on the requester's website. When the site needs a login or the current form can't be told apart, the skill asks you for the file.
- It does not seal, sign, print or submit anything.

## Requirements

- Python 3.9 or later (standard library only)

## Tests

```bash
bash plugins/hr/tests/run-all.sh
```

Offline. The fixtures are the official standard and simplified forms of the Children and Families Agency (Public Data License 1.0), kept as published, one copy of the simplified form filled with synthetic values, and synthetic company and employee data; see `tests/fixtures/SOURCE.md`.
