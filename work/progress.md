# Progress checkpoint (2026-10-07, post-near-term follow-up run)

- Corrections pipeline COMPLETE: all 18 PARTIAL drafts corrected (v2 audited RESOLVED) and merged into bodies. 14 in pass 3 (commit 6b9b4bd), FUN_68054d4a_consumer + FUN_6800a7ad + FUN_6803aad7 + FUN_68044cbd in this run.
- Post-merge sweep COMPLETE: every merged body re-audited. 9 MATCH. 5 real defects found + fixed by hand (details in BBSIM_SPEC.md status). FUN_68023dd3 PARTIAL = history-attribution false positive. FUN_6800cccc_consumer: model would not converge (7 empty responses); gated by hand.
- Merge tool off-by-one fixed: re/fix3_and_merge_v3.py (bottom-up spans, number prefixes kept). re/merge_v2.py is deprecated.
- ASN tail decode COMPLETE: re/tail_log_decode.md (news pool, 25-byte records, claim rows, Pool-B). Game results live in `fa fa 22` 34-byte lineup records (0x30000..0x6D500) - NOT yet decoded. That is the next anchoring step.
- RE_FINDINGS.md: ASN news-pool section appended. BBSIM_SPEC.md status rewritten.
- Backlog unchanged: FID false matches (3 CSplitterWnd::IsTracking in FUN_6800cccc), round-trip tests, BBSIM cross-check, more PB knob validations. NOT to do: Tier 4, IDEAS.md, pushing the repo.
