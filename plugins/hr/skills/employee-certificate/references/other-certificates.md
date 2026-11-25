# Other certificates

The flow is the same as for the employment certificate: use the requester's form when there is one, fill it with `certfill.py`, ask for what only the person knows, read it back. When the requester has no form, use the company's own template if the user keeps one (`<company folder>/hr/templates/`), otherwise draft a one-page document with only the items below and let the user put it on letterhead. Every certificate carries the issue date, the issuer (name, address, representative) and the seal if the requester wants one.

## Separation certificate (退職証明書)

Labour Standards Act, Article 22 (text on e-Gov: https://laws.e-gov.go.jp/law/322AC0000000049):

- Paragraph 1: when a worker who is leaving or has left asks for a certificate about **the period of employment, the kind of work, the position held, wages, or the reason for leaving** (including the reason for a dismissal), the employer must issue it **without delay**.
- Paragraph 2: a worker given notice of dismissal can ask, before the leaving date, for a certificate of the reason for the dismissal.
- Paragraph 3: the certificate **must not contain items the worker did not ask for**.
- Paragraph 4: no secret marks on it, and no arranging with others to keep the worker from finding work.

So:

1. Ask which of the five items the person asked for, and in what words. Write those items and nothing else: no performance remarks, no other items "for completeness", even when a template has rows for them (leave those rows blank, or remove them in the draft).
2. Take the values from the employee file and payroll records the user gives you; ask for the reason for leaving as the company records it. If the worker disputes it, write what the company records and tell the user; don't decide the dispute.
3. The worker may ask long after leaving (the right lapses after two years, Article 115). Don't refuse because the employee has left.
4. Issuing without delay is the employer's duty: tell the user the date it was requested and the date you prepared it.

A separation certificate is not the same as the separation notice for unemployment benefit (`離職票`), which goes through Hello Work and is out of scope here.

## Proof of enrolment (在籍証明書)

States that the person is employed by the company now (or was, from when to when). Usual items: name, birth date, hire date, position or kind of work, the company. Use the requester's form when it has one (schools, visa applications, landlords often do); otherwise draft one with these items. Add salary or hours only when the requester's form asks for them.

## Proof of income (収入証明 / 給与支払証明書)

Usually the requester's own form (housing, nursery fee assessment, loans) asking for wages paid per month or per year, sometimes with tax and social insurance deducted. Take every amount from payroll records the user provides, for the period the form names; never estimate. If the requester accepts the year-end withholding slip (`源泉徴収票`) instead, say so, since the company already issues it every year.

## Who issues what

Certificates a company issues to an employee, and collecting year-end adjustment paperwork, belong to this `hr` plugin. Bookkeeping and filings with the tax office belong to a future `finance` plugin. When the requester wants a tax filing document rather than a certificate from the employer, say which one and stop.
