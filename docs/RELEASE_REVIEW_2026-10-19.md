# Cabinet workflow and catalogue maintenance release review

The owner authorized publishing and upgrading after a fresh verification on
2026-10-19. Full local regression passed: 1008 tests in 242.26 seconds, with
compileall clean. Independent reviews found no release-blocking issue in saved
source binding, project access, artifact restoration or container compatibility.

This release includes the approved 1–12 cabinet independent-group AC interface,
cabinet concept SLD and block arrangement, and a cabinet proposal following the
original report's nine engineering chapters. The existing DC → AC → SLD →
Arrangement → Report Export workflow and direct download interaction remain.
Both proposal branches use the generic Download Technical Proposal button.

Product import now previews normalized values before create-only import; invalid
integer/JSON/boolean fields are reported, duplicate codes do not overwrite
existing records, and nullable numeric fields can be explicitly cleared.

The original container report, five original SLD core files and seven frozen
sizing modules are unchanged. The 13-page cabinet sample was rendered and all
pages inspected; all 21 annual rows and cabinet/group/PCS assignments match its
saved sources. Four A3 drawing pages cover both actual AC Blocks. Report cache
version 1.1.1 retains exact-source and hash checks and rebuilds intact stale
reports through the existing direct-download page.

Existing legacy cabinet AC results must be recalculated to create the approved
independent-group contract. Historical results and drawings are not relabelled
or silently migrated. Dimensioned cabinet site plans and verified installation
distances remain outside this concept release. Automatic container AC candidate
selection remains design-only; offline review scripts do not run on startup.

Local databases, credentials, product-document bodies, generated artifacts,
internal operations records and private deployment configuration are excluded.
Deployment verification and recovery details are recorded locally under the
standing operations runbook.
