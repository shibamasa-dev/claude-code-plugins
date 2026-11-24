# Changelog

Changes to the hr plugin. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the `version` in plugin.json.

## [0.1.0] - 2026-11-24

### Added
- First release, Japan-specific: the `employee-certificate` skill for the certificates a company issues to an employee (the employment certificate for nursery and after-school applications, proof of enrolment, separation certificates, proof of income)
- `certfill.py` (Python 3.9+, standard library only): `inspect`, `read`, `fill` and `verify` an `.xlsx` form by item label instead of cell address. It edits only the target cells, so the form's dropdowns and checkboxes survive, and refuses ambiguous labels, prefilled cells (without `--overwrite`), printed labels (always), fields without a value, impossible dates, formula cells and workbooks that declare a DTD. Writes OUT only once it is complete
- `company_dir` setting: the company folder (default `~/.claude/company`) that holds the company, employee and requester files outside the plugin
