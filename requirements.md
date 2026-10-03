# Equipment request requirements

An employee asks for one piece of IT equipment. The system looks up that person and the role's rules, then approves, denies, or sends the case to a human.

Each run takes two inputs, typed separately:

- employee_id: an exact id, such as E101. Tools receive this string unchanged.
- request: one sentence, such as "I need a monitor." The model reads only this sentence to decide which item was asked for.

A request is decided from four facts: employee id, role, one item, and the reason in the sentence.

## Policy rules

Catalog items are monitor and laptop. Anything else is not covered.

The issue date in the file stays a real calendar date. The check uses the date it is run. Next eligible date = issue date plus the replacement period. Before that day the answer is deny. On that day and after, the same record is approve, as long as the person is not already at the maximum.

| Role | Item | Maximum on file | Replacement |
| --- | --- | --- | --- |
| standard | monitor | 1 | every 3 years |
| standard | laptop | 1 | every 4 years |
| manager | monitor | 2 | every 3 years |
| manager | laptop | 1 | every 2 years |

Approve when the item is in that role's catalog and either they do not have one yet, or today is on or after the next eligible date. A refresh is a replacement of the existing item, not an addition, so the maximum count is not exceeded.

Deny when the item is in the catalog but today is still before the next eligible date, or they are already at the maximum.

## Ambiguous cases

Escalate, and call flag_for_human_review, only when the employee id exists and one of these is true:

- The sentence does not name one catalog item.
- The item is not in the catalog, such as a phone or a desk.

An unknown employee id is an error from the tools. The agent reports that it cannot decide. It does not approve, and it does not write a review record.

## People on file

| Id | Name | Role | Tenure | Equipment on file |
| --- | --- | --- | --- | --- |
| E101 | Priya Shah | standard | 2 years | laptop issued 2024-06-01 |
| E102 | Luis Ortega | standard | 5 years | monitor issued 2025-11-01; laptop issued 2023-01-01 |
| E103 | Mina Cho | manager | 6 years | laptop issued 2025-08-01 |
| E104 | Owen Blake | manager | 3 years | laptop issued 2022-01-01; monitor issued 2021-01-01 |

## Four demo requests

| Id | Sentence | Expected result | Why |
| --- | --- | --- | --- |
| E101 | I need a monitor. | Approve | No monitor on file. This does not depend on the date. |
| E102 | I need a monitor. | Deny until 2028-11-01 | Monitor issued 2025-11-01. Standard replacement is 3 years, so the next eligible date is 2028-11-01. Before that day: deny. On that day or later: approve. |
| E103 | I need a new iPhone. | Escalate | Employee exists. A phone is not in the catalog. |
| E104 | My setup is terrible, please sort it out. | Escalate | Employee exists. The sentence names no item. |