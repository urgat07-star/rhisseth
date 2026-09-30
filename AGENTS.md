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

## Rhisseth synchronization reports

Every Markdown report created by `tools/rhisseth-sync.ps1` under
`reports/Git-sync/` must include the current Git commit when `HEAD` exists:
the full commit SHA and its subject. If the repository has no commit, the
report must explicitly state that a commit has not been created. This applies
to every `rhisseth-sync` command that writes a report, not only `status` or
GitHub publication commands.

Menu item 5 / `pull-vds` must export both the sanitized project files and all
database content editable through the Rhisseth administration UI: hexes,
military units with costs and upgrade links, resource catalogues, additional
building catalogues and placements, and general templates. The import branch
must contain `data/snapshots/editable-database.json` and a separate commit.
Secrets, users, sessions, wallets, inventories and battle history must never
be included. Deployment applies the reviewed snapshot only after migrations.
