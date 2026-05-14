# CURRENT_CONFIG_REFERENCE

Authority caveat: CURRENT_WORKSPACE_REFERENCE_ONLY_NOT_RUNTIME_AUTHORITY

| Config | Required | Exists | Parse Status | SHA256 | Notes |
| --- | --- | --- | --- | --- | --- |
| config/aurora/domains.yaml | required | True | PARSED_MAPPING | cf3a9dbea58b573be8cfb30993e0ab9daf6cb05ebf12610fe8aa7aceebf5b962 | Decision-making domain config including LOW_VOL gate thresholds. |
| config/aurora/trading.yaml | required | True | PARSED_MAPPING | 82831ed38641795e082f5145262b1ae55a5075e50bcd6ba57fe7d14fe753fbbc | Trading mode and execution envelope config. |
| config/aurora/strategies.yaml | required | True | PARSED_MAPPING | 23984d9512aa93a218abfa91c3c85046f7513afccf2eab51bfd2b271122a21be | Strategy routing and enablement config. |
| config/aurora/strategies/aurora.yaml | required | True | PARSED_MAPPING | 9e3e7f44a68c899471693ce6e928f7df4eecc21a23441bdd6762f8975e9615be | Aurora strategy config surface. |
| config/aurora/strategies/md_amr.yaml | required | True | PARSED_MAPPING | 390979c1d75881c98080de96f2eeccec92af295505b7cc2bc3d67c44ce1d06d7 | MD AMR strategy config surface. |
| config/aurora/strategies/mean_reversion.yaml | required | True | PARSED_MAPPING | d2393c2fe243ee73c6d93266a7a1ffdd141dc5b2fc246f5804b3afb3ccc7acbb | Mean reversion strategy config surface. |
| config/aurora/regime.yaml | required | True | PARSED_MAPPING | e2d9cb49d02f74cbe1122c0157aee9e6493ad8e2b392e311646f3ef04ecf2396 | Regime detector config. |
| config/aurora/observability.yaml | required | True | PARSED_MAPPING | 5479754806940ed74f7262ac6d8a5d21c7b8511084617fa2011437bbb9cc1f6c | Observability config relevant for future frozen bundles. |
| config/alpha_search.yaml | optional | True | PARSED_MAPPING | 24d41e098dda6c613f2e6faf2dcb4409b62ab7fea78952e92b83d1c191a34494 | Optional alpha search runtime config. |
| config/judge_review.yaml | optional | True | PARSED_MAPPING | a82a911f28b32bc033e29be99ad4ba128511ded8f8a2ede298d423df7857f233 | Optional judge review config. |
| config/judge_simulator.yaml | optional | True | PARSED_MAPPING | e6bade3522d247f1f7b3f65bf89e029e0cb51d4da46cd9e74972d3910bdf8d68 | Optional judge simulator config. |
