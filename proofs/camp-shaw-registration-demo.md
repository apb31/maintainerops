# Camp Shaw registration-flow proof of work

> Fresh synthetic demo created specifically for the Camp Shaw application. This is **not** presented as prior client work.

## Goal

Create a simple, mobile-first camper registration path that can start as an information-collection form and expand to payment only after the exact rules are confirmed.

## Proposed first paid milestone

**US$95 / 1 business day after staging access + field list are agreed**

Deliverables:

- One responsive registration path on WordPress staging
- Required-field validation
- Guardian confirmation email
- Admin notification email
- Clean submission export (CSV or plugin-native export)
- One correction against agreed acceptance cases

Payment processing is intentionally excluded from the first milestone until the existing gateway/plugin and refund/registration rules are confirmed.

## UX flow

1. Choose camp session / camper type
2. Enter camper + guardian details
3. Review required consents
4. Optional payment step (later milestone if needed)
5. Confirmation + admin notification

## Low-risk implementation approach

Use the site's existing WordPress stack first. Depending on what is already installed, Gravity Forms, Fluent Forms, WPForms, or an equivalent form tool can handle the initial flow without introducing a new paid dependency. Custom PHP/JS should only be added where the existing stack cannot meet the agreed behavior cleanly.

## Wireframe

```text
+------------------------------------------------------+
| CAMP REGISTRATION                                    |
| Clear next step, minimal first screen                |
|                                                      |
| [ Camp session v ]   [ Camper age group v ]          |
|                                                      |
| Guardian name                                        |
| [____________________________________________]       |
|                                                      |
| Guardian email                                       |
| [____________________________________________]       |
|                                                      |
| Anything we should know? (optional)                  |
| [____________________________________________]       |
| [____________________________________________]       |
|                                                      |
| [ Continue ]                                         |
+------------------------------------------------------+
```

## Acceptance cases for the first milestone

- Required fields cannot be skipped.
- Invalid email format is rejected before submission.
- Valid test submission appears once in the admin/export view.
- Guardian receives one confirmation email.
- Admin receives one notification email.
- Layout remains usable on a narrow mobile viewport.
- No payment is charged in the first milestone unless separately agreed.

## Homepage follow-on

After the registration pilot, the homepage refresh can be scoped from Camp Shaw's existing design draft and current theme/builder. A bounded second milestone would cover implementation, responsive checks, and agreed revisions rather than committing to an undefined full redesign upfront.
