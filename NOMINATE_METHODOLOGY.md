# DW-NOMINATE for the Korean National Assembly: Methodology Note

**Working document** | Last updated: 2026-03-22
**Project**: Korean Bill Lifecycle Master Database
**Author**: Kyusik Yang (NYU)

---

## 1. Why DW-NOMINATE for the Korean National Assembly

Estimating comparable legislator ideal points across multiple Korean National Assembly (KNA) sessions is essential for studying ideological polarization, party system change, and the institutional determinants of legislative behavior over time. Static scaling methods such as W-NOMINATE produce ideal points that are internally consistent within a single legislative session but are not directly comparable across sessions. The estimated coordinates from the 20th Assembly and those from the 22nd Assembly sit on different latent scales, making it impossible to answer straightforward questions about whether parties have moved apart, whether individual legislators have shifted ideologically, or whether the KNA as a whole has become more polarized.

DW-NOMINATE (Dynamic Weighted NOMINAL Three-Step Estimation) addresses this limitation by pooling roll call data across sessions and exploiting **bridging legislators** - members who serve in multiple assemblies - to anchor a common ideological space. In the U.S. Congress, where this method was developed, the large number of incumbents who win reelection provides ample bridging observations. The Korean context presents both a challenge and an opportunity: reelection rates are lower than in the U.S. Congress, but the number of bridging legislators across recent assemblies remains sufficient for identification.

The Korean party system poses an additional challenge that makes dynamic scaling particularly valuable. Korean parties undergo frequent mergers, splits, and name changes. What was the Grand National Party (한나라당) became the Saenuri Party (새누리당), then the Liberty Korea Party (자유한국당), then the United Future Party (미래통합당), and finally the People Power Party (국민의힘) - all within a decade. On the progressive side, the Democratic Party has similarly undergone multiple rebranding cycles. Simple party-label-based measures of ideology cannot capture within-party heterogeneity or accommodate these transformations. Roll-call-based ideal points estimated through DW-NOMINATE provide a continuous, member-level measure that is invariant to party labels.

Our data infrastructure covers the 20th through 22nd Assemblies (2016-present) with clean API-sourced member-level roll call votes, yielding approximately 2.4 million individual vote observations. Across these three assemblies, we identify 218 bridging legislators: 126 who serve in both the 20th and 21st, 151 who bridge the 21st and 22nd, and 68 who appear in all three sessions. This bridging density is sufficient for DW-NOMINATE to anchor a common scale across at least three recent assemblies.

---

## 2. Literature Review

### 2.1 The NOMINATE Framework

The foundational work on spatial voting models for legislatures is Poole and Rosenthal's NOMINATE family of estimators. Poole and Rosenthal (1985) introduced the original NOMINATE procedure, which recovers legislator ideal points and bill parameters from binary roll call matrices using a random utility framework. Poole and Rosenthal (1997) extended this into a comprehensive analysis of the U.S. Congress, demonstrating that a single liberal-conservative dimension accounts for the vast majority of roll call voting patterns. Their later volume (Poole and Rosenthal 2007) refined the methodology and introduced the DW-NOMINATE variant, which uses bridging legislators to place ideal points on a common scale across congresses. The key innovation is that a legislator serving in multiple congresses provides identification across those sessions: by assuming that legislators' ideal points follow a smooth trajectory (modeled as a random walk), DW-NOMINATE can align the latent scales.

### 2.2 NOMINATE Applications to the Korean National Assembly

Hix and Jun represent the earliest systematic application of spatial voting models to the KNA. In a London School of Economics working paper (Hix and Jun 2006) and the subsequent journal article (Hix and Jun 2009), they applied W-NOMINATE to roll call votes from the 16th and 17th Assemblies. Their results demonstrated that Korean legislative voting is predominantly structured along a single ideological dimension, though they noted a secondary dimension related to regional (영남 vs. 호남) cleavages. Jun and Hix (2010) extended this analysis to examine how mixed-member electoral systems shape legislative behavior, using NOMINATE ideal points from the 16th and 17th Assemblies to show that legislators elected from single-member districts and those elected from proportional representation lists exhibit different voting patterns.

남윤민 and 마인섭 (2019) applied W-NOMINATE to the 20th Assembly, providing the most recent static ideal point estimates for a complete KNA session using the classical NOMINATE approach. Their analysis in 의정논총 confirmed the dominance of the government-opposition dimension but was limited to a single assembly.

### 2.3 Alternative Approaches

Several scholars have explored alternatives to NOMINATE for the Korean context. Hahn et al. (2014) applied Bayesian Item Response Theory (IRT) models to roll call votes from the 18th Assembly, publishing their results in the Korean Journal of Applied Statistics (응용통계연구). The Bayesian IRT approach offers several advantages over NOMINATE, including direct estimation of uncertainty around ideal point estimates and more flexible modeling of abstention behavior. However, like W-NOMINATE, their single-assembly application does not address cross-session comparability.

이갑윤 and 이현우 (2011) analyzed partisan voting patterns in the 17th Assembly, providing descriptive context on the extent to which KNA members vote along party lines. Rich (2014) offered a comparative analysis of party voting cohesion in mixed-member systems, situating the Korean case within the broader literature on how electoral institutions shape legislative unity. Jung (2023) examined how electoral margins influence party loyalty in the 20th Assembly, contributing to our understanding of the mechanisms that produce the high levels of party discipline observed in ideal point estimates.

Han (2022) took a different approach entirely, using NLP-based methods to estimate ideal points from bill text and legislator-text associations across the 17th through 20th Assemblies. This text-based approach sidesteps the problem of unanimous votes that plagues roll-call-based methods in the Korean context, since it does not rely on voting variation for identification.

Most recently, Lee, Kim, and Jin (2026) applied a Latent Space Item Response Model (LSIRM) to roll call data from the 17th Assembly, demonstrating that a unidimensional NOMINATE model may miss meaningful issue-specific variation in legislator positions. Their approach embeds both legislators and bills in a shared latent space, allowing bill-specific deviations from a legislator's general ideological position. This critique is particularly relevant for the Korean case, where the small number of contested votes may not all align on a single dimension.

### 2.4 Summary of Existing Work

| Study | Method | Assemblies | Key finding |
|-------|--------|------------|-------------|
| Hix and Jun (2006, 2009) | W-NOMINATE | 16th-17th | 1D dominant; 2D reflects regional cleavage |
| Jun and Hix (2010) | W-NOMINATE | 16th-17th | SMD vs. PR list members differ in voting |
| 이갑윤 and 이현우 (2011) | Descriptive | 17th | High partisan voting in the KNA |
| Hahn et al. (2014) | Bayesian IRT | 18th | IRT feasible for Korean roll calls |
| Rich (2014) | Comparative | Cross-national | Party cohesion in mixed-member systems |
| 남윤민 and 마인섭 (2019) | W-NOMINATE | 20th | Government-opposition dimension dominant |
| Han (2022) | NLP-based | 17th-20th | Text-based ideal points as alternative |
| Jung (2023) | W-NOMINATE + regression | 20th | Electoral margins predict party loyalty |
| Lee, Kim, and Jin (2026) | LSIRM | 17th | 1D model may miss issue-specific variation |

A gap is evident: no published study applies DW-NOMINATE (or any dynamic scaling method) to create comparable ideal point estimates across multiple KNA sessions. Individual assemblies have been studied in isolation, but the party system transformations that make cross-session comparison so valuable also make it methodologically demanding. This project fills that gap.

---

## 3. Data Infrastructure

### 3.1 Roll Call Votes

Our roll call data come from two sources, consolidated into a unified dataset (`roll_calls_all.parquet`).

**API votes (20th-22nd Assemblies).** We collect member-level voting records from the 열린국회정보 Open API endpoint `nojepdqqaweusdfbi`, which provides individual legislator votes (찬성/반대/기권/불참) for each bill that reached a plenary vote. This yields approximately 2.4 million member-vote observations across three assemblies. The API data are clean: each record includes a standardized member identifier (`member_id`), bill identifier (`bill_id`), vote category, party affiliation, and assembly number. Vote coding follows the pscl convention: Yea = 1, Nay = 6, Abstain = 9, Not in Legislature = NA.

**Historical votes (16th-19th Assemblies).** For earlier assemblies where the API does not provide member-level votes, we rely on two supplementary sources: (a) inline votes parsed from plenary session transcripts (회의록), where the presiding officer reads member names aloud by vote category, and (b) appendix votes extracted from PDF attachments to plenary records. The `consolidate_votes.py` pipeline merges these three sources. Coverage for the 18th and 19th Assemblies remains incomplete due to inconsistent transcription practices and the difficulty of parsing PDF appendices at scale.

### 3.2 Bridging Legislators

We identify bridging legislators as members who cast votes in multiple assemblies. Across the 20th through 22nd Assemblies:

| Bridge | Count | Description |
|--------|-------|-------------|
| 20th and 21st | 126 | Members serving in both assemblies |
| 21st and 22nd | 151 | Members serving in both assemblies |
| All three (20th-22nd) | 68 | Members serving in all three assemblies |
| **Total unique bridges** | **218** | Members appearing in 2+ assemblies |

These 218 bridging legislators represent approximately 23% of the total unique members across the three assemblies. For comparison, the U.S. Congress typically has 85-90% reelection rates, providing far denser bridging. However, Monte Carlo simulations in the NOMINATE literature suggest that even modest numbers of bridges (on the order of 50-100 per pair of sessions) are sufficient for reliable scale alignment.

### 3.3 Known Data Limitations

1. **18th-19th Assembly votes are incomplete.** The 열린국회정보 API (`ncocpgfiaoituanbr`) does not return individual member votes for assemblies prior to the 20th. We rely on parsed 회의록, which have gaps.

2. **16th-17th Assembly data are limited to contested votes.** The earlier transcripts yield fewer total votes, and the fraction of these that are contested (i.e., useful for ideal point estimation) is small.

3. **The record.assembly.go.kr portal is scheduled for an April 2026 update** that may expose individual-level vote data for the 16th-19th Assemblies via a new API. If realized, this would substantially expand our time coverage.

4. **Historical data present a "성명은 끝에 실음" problem.** In some plenary transcripts, particularly from the 16th and 17th Assemblies, member names are listed at the end of the session record rather than inline with each vote. Parsing these cases requires matching name lists to vote categories, introducing potential errors.

---

## 4. Methodological Choices

### 4.1 Comparison of Scaling Methods

We considered four approaches for estimating ideal points, each with distinct trade-offs.

**W-NOMINATE** (Poole, Rosenthal, and Lewis). The standard method for estimating ideal points from a single roll call matrix. Produces well-validated estimates within a single assembly but does not yield cross-session comparability. Each assembly's ideal points sit on an arbitrary latent scale.

**DW-NOMINATE** (Poole and Rosenthal 2007). Extends W-NOMINATE by pooling votes across sessions and using bridging legislators to anchor a common scale. Models each legislator's ideal point as a linear trend across sessions. This is our primary approach for cross-assembly comparison.

**Bayesian IRT** (e.g., Clinton, Jackman, and Rivers 2004; implemented in R packages `pscl` and `idealstan`). Offers posterior distributions over ideal points, providing direct uncertainty quantification. Can handle missing data and abstentions more flexibly than NOMINATE. We plan to use Bayesian IRT as a robustness check, following Hahn et al. (2014) for the Korean context.

**LSIRM** (Lee, Kim, and Jin 2026). Embeds legislators and bills in a shared latent space, allowing bill-specific deviations from a legislator's general position. This addresses the concern that a single dimension may be insufficient, particularly when different policy domains activate different coalitions. We treat this as a diagnostic tool rather than a primary estimator, given that the method is newer and less established in the literature.

### 4.2 Polarity Identification

NOMINATE and IRT models are identified only up to a reflection (the scale can be flipped). We anchor the scale by designating a known conservative legislator as having a positive ideal point. In practice, we select a senior member of the People Power Party (or its predecessor party) who is widely recognized as ideologically conservative. The `polarity` argument in the `wnominate()` and `dwnominate()` functions takes the row index of this anchor legislator.

### 4.3 Vote Filtering

**Lopsidedness filter.** Votes where fewer than 2.5% of participants are in the minority contribute negligible information for ideal point estimation while adding noise. We exclude these near-unanimous votes. In the Korean context, this threshold is consequential: a large fraction of plenary votes are unanimous or nearly so due to high party discipline and the practice of scheduling only consensus bills for floor votes. For the 22nd Assembly, approximately 1,286 bills reached a floor vote out of over 17,000 introduced; among those, many passed with overwhelming majorities.

**Minimum vote threshold.** Legislators who participate in fewer than 20 contested votes are excluded from estimation. This threshold balances including as many legislators as possible against the risk of unreliable estimates from sparse data.

### 4.4 Dimensionality: 1D vs. 2D

The existing literature on the KNA generally finds that a single dimension (government-opposition) captures the dominant structure of legislative voting. Hix and Jun (2009) noted a secondary dimension reflecting regional loyalties, and Lee, Kim, and Jin (2026) argued that issue-specific variation exists. We begin with a one-dimensional model and examine the fit diagnostics (classification success, eigenvalue ratios) to assess whether a second dimension is warranted. If the APRE (Aggregate Proportional Reduction in Error) increases substantially with a second dimension, we estimate 2D models as a supplement.

### 4.5 Scale Alignment for Bridging

The DW-NOMINATE procedure handles scale alignment internally by requiring that bridging legislators' ideal points follow a linear trend across sessions. The R `dwnominate` package implements this by taking a list of `rollcall` objects (one per session, from the `pscl` package) and matching legislators by their row names across sessions. We construct session-specific rollcall objects with consistent member identifiers (using the `member_id` field from the API) so that the bridging identification is automatic.

For assemblies that cannot be linked via DW-NOMINATE (e.g., if 18th-19th data remain too sparse), we can apply a post-hoc linear alignment: estimate W-NOMINATE separately for each session, then use the bridging legislators' scores to fit an affine transformation (shift and stretch) that maps one session's scale onto another's. This approach is less principled than full DW-NOMINATE but provides a pragmatic fallback.

---

## 5. Known Challenges for the Korean Application

### 5.1 High Party Discipline and Unanimous Voting

The most fundamental challenge is that Korean legislators vote with their parties at very high rates. Rich (2014) documented that party voting unity scores in the KNA are among the highest in democratic legislatures with mixed-member electoral systems. This means that most floor votes are lopsided or unanimous, leaving few contested votes to discriminate among legislators. Even within the set of contested votes, the variation may primarily reflect party defection on a handful of salient issues rather than continuous ideological positioning.

This has practical consequences: the number of usable roll calls after applying the lopsidedness filter may be quite small. If only 200-400 contested votes are available per assembly (a plausible range given the data), the precision of individual ideal point estimates will be lower than what is typical in U.S. Congressional applications, where thousands of contested votes are available.

### 5.2 Party Name Changes and Mergers

Korean parties frequently change names, merge, and split, as noted in Section 1. The major conservative party underwent five name changes between the 17th and 22nd Assemblies:

| Assembly | Conservative party | Progressive party |
|----------|-------------------|-------------------|
| 17th (2004-2008) | 한나라당 (Grand National Party) | 열린우리당 (Uri Party) |
| 18th (2008-2012) | 한나라당 (Grand National Party) | 민주당 (Democratic Party) |
| 19th (2012-2016) | 새누리당 (Saenuri Party) | 민주통합당/새정치민주연합 |
| 20th (2016-2020) | 자유한국당 (Liberty Korea Party) | 더불어민주당 (Democratic Party) |
| 21st (2020-2024) | 미래통합당/국민의힘 (PPP) | 더불어민주당 |
| 22nd (2024-) | 국민의힘 (PPP) | 더불어민주당 |

Roll-call-based ideal points are agnostic to party labels, which is an advantage. However, party-level summaries require a harmonization table that tracks these transitions. Furthermore, mid-session party switches and the creation of splinter parties (e.g., 바른정당 in the 20th Assembly, 개혁신당 in the 22nd) complicate the assignment of party affiliations to ideal point estimates.

### 5.3 Data Availability for Historical Assemblies

As documented in our DATA_AVAILABILITY.md, the 열린국회정보 API provides member-level votes only for the 20th Assembly onward. For the 16th-19th Assemblies, we depend on parsed plenary transcripts, which have uneven coverage:

- **16th-17th Assemblies**: Hix and Jun's (2006, 2009) data covered these assemblies, but their original dataset is not publicly available. Our own parsing from 회의록 text is ongoing.
- **18th-19th Assemblies**: The most significant gap. Individual member votes are largely unavailable through the current API. The record.assembly.go.kr portal update (expected April 2026) may resolve this.

### 5.4 Dimensionality Concerns

Lee, Kim, and Jin (2026) raised a substantive critique: a one-dimensional NOMINATE model may impose an artificial structure on Korean legislative voting. In their LSIRM analysis of the 17th Assembly, they found that certain bills deviate substantially from the primary ideological dimension, particularly on issues where cross-cutting coalitions form (e.g., regional development, specific industry regulation). This suggests that treating the first NOMINATE dimension as "ideology" may be an oversimplification, and that researchers should exercise caution in interpreting the substantive meaning of the recovered dimension.

### 5.5 Electronic Voting and Recording Practices

The KNA transitioned to electronic voting at different points for different types of decisions. Plenary votes on bills are recorded electronically from the 17th Assembly onward (with some exceptions), but committee votes are generally not recorded at the individual level. This means our ideal point estimates are based exclusively on plenary floor votes, missing within-committee deliberation that may reveal different preference structures.

---

## 6. Our Approach and Preliminary Results

### 6.1 Implementation

Our pipeline proceeds in three steps:

1. **W-NOMINATE per assembly** (`estimate_idealpoints.R`). For each of the 20th, 21st, and 22nd Assemblies, we estimate a one-dimensional W-NOMINATE model using the `wnominate` R package. The rollcall matrix is constructed from API vote data, with the lopsidedness filter set at 2.5% and the minimum vote threshold at 20 contested votes. Polarity is anchored by the first legislator in the matrix (to be replaced with a named conservative anchor in subsequent runs).

2. **DW-NOMINATE across assemblies** (`estimate_dwnominate.R`). We pool the three assemblies into a list of `rollcall` objects, mapping the 20th, 21st, and 22nd Assemblies to congress numbers 1, 2, and 3. The `dwnominate` R package identifies bridging legislators by matching `member_id` row names across sessions and estimates ideal points on a common scale.

3. **Validation and diagnostics**. We examine bridging legislator score stability (mean absolute shift, correlation across terms) and compare party-level distributions to verify face validity.

### 6.2 Preliminary Results

The DW-NOMINATE estimation across the 20th-22nd Assemblies produces 936 legislator-term observations (after excluding legislators with insufficient contested votes). Key diagnostics:

- **Bridging stability**: The correlation of ideal points for bridging legislators across adjacent assemblies provides a measure of scale consistency. High correlations (above 0.85) indicate that the bridging alignment is working as intended.
- **Party separation**: The major conservative and progressive parties should be clearly separated on the first dimension, with smaller parties (e.g., Justice Party / 정의당) occupying positions consistent with their known ideological orientations.
- **Classification accuracy**: The APRE and GMP (Geometric Mean Probability) from the NOMINATE output provide overall measures of fit.

These results are preliminary and should be interpreted with caution pending further validation, particularly on polarity anchoring and the treatment of small parties.

### 6.3 Planned Robustness Checks

- **Bayesian IRT** using the `pscl` package's `ideal()` function or the `idealstan` package, which handles abstentions explicitly.
- **Varying the lopsidedness threshold** (1%, 2.5%, 5%) to assess sensitivity.
- **2D estimation** to check whether a second dimension captures meaningful variation.
- **Comparison with Han (2022) NLP-based estimates** for the overlapping assemblies (17th-20th) to assess convergent validity across methods.

---

## 7. Future Directions

### 7.1 Expanding Temporal Coverage

The most immediate priority is extending coverage backward from the 20th Assembly. The record.assembly.go.kr portal is scheduled for an update in April 2026, which may expose individual-level roll call data for the 16th-19th Assemblies through a new or revised API. If these data become available, we can extend the DW-NOMINATE estimation to cover the 16th through 22nd Assemblies (2000-present), providing a quarter-century of comparable ideal point estimates for the KNA.

Even without the portal update, we continue to parse plenary transcripts (회의록) for the 16th-17th Assemblies. The 17th Assembly data, in particular, would allow direct comparison with Hix and Jun's (2009) W-NOMINATE estimates and extend our bridging chain back one additional session.

### 7.2 Issue-Specific Ideal Points

Following Lee, Kim, and Jin's (2026) LSIRM approach, we plan to estimate issue-specific ideal points by classifying bills into policy domains (using committee assignment as a proxy) and either estimating separate NOMINATE models per domain or fitting a multidimensional model that allows domain-specific loadings. This would address the concern that a single dimension conflates distinct policy cleavages.

### 7.3 Integration with Bill Lifecycle Data

The ideal point estimates are designed to integrate with the broader Korean Bill Lifecycle Master Database. With both a bill's legislative trajectory (committee referral, amendment, floor vote outcome) and the estimated ideal points of its sponsors and committee members, we can analyze questions such as:

- Do bills proposed by ideologically extreme legislators face longer processing times?
- Does the distance between a bill's sponsor and the median committee member predict committee-stage failure?
- How does ideological polarization at the chamber level affect the rate of bill passage across assemblies?

### 7.4 Public Dataset Release

We aim to produce a public dataset of Korean legislative ideal points modeled on the Voteview project (voteview.com) for the U.S. Congress. This "Korean Voteview" would include:

- Legislator-term-level ideal point estimates (1D and 2D)
- Confidence intervals / posterior distributions
- Party affiliations with harmonized labels across assemblies
- Roll call vote matrices in standard format
- Bill-level parameters (midpoint and spread)

Releasing these data would lower the barrier for researchers studying Korean legislative politics and facilitate replication and extension of our analysis.

---

## References

Hahn, Kwonsang, Jaeyong Lee, Yung-Seop Lee, and Jaeho Song. 2014. "국회 기명투표 분석을 위한 베이지안 요인분석 모형." *응용통계연구* 27 (7): 1115-1126.

Han, Jeehoon. 2022. "Estimating Ideal Points of South Korean National Assembly Members Using Natural Language Processing." *Journal of East Asian Studies* 22 (3): 457-480.

Hix, Simon, and Hae-Won Jun. 2006. "Party Behaviour in the Parliamentary Arena: The Case of the Korean National Assembly." Working Paper, London School of Economics.

Hix, Simon, and Hae-Won Jun. 2009. "Party Behaviour in the Parliamentary Arena: The Case of the Korean National Assembly." *Party Politics* 15 (6): 667-694.

Jun, Hae-Won, and Simon Hix. 2010. "Electoral Systems, Political Career Paths and Legislative Behavior: Evidence from South Korea's Mixed-Member System." *Japanese Journal of Political Science* 11 (2): 153-171.

Jung, Wooseok. 2023. "Electoral Margins, Party Loyalty, and Legislative Behavior: Evidence from the Korean National Assembly." *Party Politics* 29 (5): 877-889.

Lee, Dongjin, Jaesung Kim, and Ick Hoon Jin. 2026. "Uncovering the Latent Structure of Legislative Voting: A Latent Space Item Response Model Approach." arXiv:2603.01081.

남윤민, 마인섭. 2019. "20대 국회 표결의 이념적 특성 분석: W-NOMINATE를 이용하여." *의정논총* 14 (2): 5-32.

이갑윤, 이현우. 2011. "17대 국회의 정당 투표 분석." *한국정치학회보* 45 (1): 75-98.

Poole, Keith T., and Howard Rosenthal. 1985. "A Spatial Model for Legislative Roll Call Analysis." *American Journal of Political Science* 29 (2): 357-384.

Poole, Keith T., and Howard Rosenthal. 1997. *Congress: A Political-Economic History of Roll Call Voting*. New York: Oxford University Press.

Poole, Keith T., and Howard Rosenthal. 2007. *Ideology and Congress*. 2nd ed. New Brunswick, NJ: Transaction Publishers.

Rich, Timothy S. 2014. "Party Voting Cohesion in Mixed Member Systems: Evidence from Korea and Japan." *Legislative Studies Quarterly* 39 (1): 113-135.
