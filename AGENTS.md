# Rhisseth release records

For every new Rhisseth release, create a version-specific Markdown record in
`docs/releases/`. Record the completed work, version, date, publication status,
validation results, known limitations, and links to detailed reports and
sanitized operation logs. After publication, update the record with the actual
Git tag and deployment result. Never describe an unpublished release as
published.

Keep bug reports for published versions in `docs/bug-report/`. A report for
version `vX.Y.Z` describes errors found in that version and identifies the
following fix release separately.

## Mandatory change records

Every change to the game must have its own Markdown change record, regardless
of whether it is developed on `fix/*`, `feature/*`, `release/*`, `hotfix/*`,
`main`, or any other branch. Create the record under `docs/changes/` before the
change is published. Do not rely only on a commit message, an automation log,
chat history, or the cumulative release record.

Name records `YYYY-MM-DD-short-change-name.md`. Each record must include:

- date, intended version/fix number, branch, commit and tag (or explicitly
  state that they have not been created yet);
- request and reason for the change;
- user-visible behaviour before and after;
- affected frontend, backend, database, rules and documentation files;
- database migrations and compatibility impact, or an explicit `none`;
- tests and validation results;
- publication status, target and result;
- backup and rollback information for a published change;
- known limitations and follow-up work;
- links to related bug reports, release records, detailed reports and
  sanitized operation logs.

Update the same record after commit, GitHub publication and VDS deployment so
that it contains the actual commit, tag and validation evidence. Direct or
emergency publication does not waive this requirement: create the record in
the same work session and clearly identify any period when the VDS was ahead
of Git. The version-specific record in `docs/releases/` must link to every
change record included in that release.
