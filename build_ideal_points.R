# build_ideal_points.R
# ============================================================
# Build the three ideal point series distributed by this repository.
#
#   1. ideal_points_wnominate.csv   per-assembly W-NOMINATE
#   2. ideal_points_bridged.csv     chained bridging alignment of (1)
#   3. ideal_points_dwnominate.csv  pooled DW-NOMINATE
#
# The three answer different questions and are not interchangeable.
# See CODEBOOK.md, section "Ideal points", before using any of them.
#
# Every output row carries a `vintage` label, and ideal_points_manifest.json
# records the input checksum, the cutoff, the vote dates and matrix sizes per
# term, the settings, the package versions and the output checksums.
#
# `party` is the party at election (members_{term}.parquet, from
# ALLNAMEMBER). The roll-call API's own
# label (POLY_NM) is the party at collection time, rewritten retroactively on
# past votes, and is used only for a member missing from members_{term}.
#
# Prerequisites:
#   install.packages(c("arrow", "dplyr", "tidyr", "pscl", "wnominate",
#                      "jsonlite", "digest"))
#   remotes::install_github("wmay/dwnominate")   # not on CRAN, compiles Fortran
#
# Usage:
#   Rscript build_ideal_points.R              # all three
#   Rscript build_ideal_points.R --skip-dw    # skip the slow pooled estimation
#   Rscript build_ideal_points.R --input data/_build/roll_calls_all.parquet \
#       --members-dir data/_build --out data/_build/ideal_points --cutoff 20260312
#
# Arguments (each also accepts --name=value):
#   --input PATH        roll calls (default data/processed/roll_calls_all.parquet)
#   --members-dir DIR   directory with members_{term}.parquet (default data/processed)
#   --out DIR           output directory (default data/processed)
#   --cutoff YYYYMMDD   drop votes taken after this date (default: no cutoff)
#   --vintage LABEL     vintage label (default: "v" + date of the last vote used)
#   --skip-dw           skip the pooled DW-NOMINATE estimation
# ============================================================

suppressMessages({
  library(arrow)
  library(dplyr)
  library(tidyr)
  library(pscl)
  library(wnominate)
})

args <- commandArgs(trailingOnly = TRUE)
SKIP_DW <- "--skip-dw" %in% args

KNOWN_ARGS <- c("--skip-dw", "--input", "--members-dir", "--out", "--cutoff", "--vintage")
unknown <- setdiff(sub("=.*$", "", args[startsWith(args, "--")]), KNOWN_ARGS)
if (length(unknown)) stop("unknown argument(s): ", paste(unknown, collapse = ", "))

arg_value <- function(flag, default) {
  hit <- grep(paste0("^", flag, "(=|$)"), args)
  if (!length(hit)) return(default)
  if (grepl("=", args[hit[1]])) return(sub(paste0("^", flag, "="), "", args[hit[1]]))
  if (hit[1] == length(args)) stop(sprintf("%s needs a value", flag))
  args[hit[1] + 1]
}

INPUT       <- arg_value("--input", "data/processed/roll_calls_all.parquet")
MEMBERS_DIR <- arg_value("--members-dir", "data/processed")
OUT         <- arg_value("--out", "data/processed")
CUTOFF      <- arg_value("--cutoff", NA_character_)
VINTAGE     <- arg_value("--vintage", NA_character_)
if (!is.na(CUTOFF) && !grepl("^[0-9]{8}$", CUTOFF)) stop("--cutoff must be YYYYMMDD")
dir.create(OUT, recursive = TRUE, showWarnings = FALSE)

MIN_MINORITY <- 0.025   # a vote counts as contested if >=2.5% are in the minority
MIN_VOTES    <- 20      # a legislator is active with >=20 contested votes
REF_TERM     <- 20      # bridging alignment expresses every term in these units
TERMS        <- c(20, 21, 22)
DW_SEED      <- 20260718

# Blocs for the party-distance statistics, the sign checks and party_bloc.
# Labels are the party at election, so the lists hold the names the parties
# carried at the 2016, 2020 and 2024 elections (새누리당 is the 2012-2017
# name of 자유한국당) and the satellite list parties of 2020 and 2024
# (미래한국당, 국민의미래, 더불어시민당, 더불어민주연합).
CONSERVATIVE <- c("국민의힘", "미래통합당", "자유한국당", "미래한국당",
                  "새누리당", "국민의미래")
LIBERAL      <- c("더불어민주당", "더불어시민당", "더불어민주연합")

# Polarity anchors, one named legislator per term. Each fit is oriented so
# that the anchor has a positive coordinate on every dimension. Anchoring on
# a name instead of a row position keeps the sign, including the sign of the
# second dimension, independent of the input row order. 추경호 (G152611B,
# 대구 달성군) was elected for 새누리당 (20th), 미래통합당 (21st) and
# 국민의힘 (22nd). He served the 20th and 21st in full and left the 22nd in
# 2026 (last recorded vote 2026-04-28), with 59 contested yea/nay votes there,
# so later 22nd votes cannot drop him below MIN_VOTES. His second-dimension
# coordinate is close to zero in the 21st and 22nd, so the sign of wnom2d_dim2
# there rests on a legislator near the middle of that dimension.
POLARITY_ANCHOR <- c("20" = "G152611B", "21" = "G152611B", "22" = "G152611B")

anchor_index <- function(ids, t) {
  a <- which(ids == POLARITY_ANCHOR[[as.character(t)]])
  if (length(a) != 1) {
    stop(sprintf("polarity anchor %s is not among the scaled legislators of the %dth Assembly",
                 POLARITY_ANCHOR[[as.character(t)]], t))
  }
  a
}

# ── Load ───────────────────────────────────────────────────
cat(sprintf("Loading roll call data from %s...\n", INPUT))
rc <- read_parquet(INPUT)

api_all <- rc %>%
  # api rows plus the LIKMS supplement for members the member-level API omits
  filter(source %in% c("api", "likms", "likms_absent"), term %in% TERMS) %>%
  mutate(term = as.integer(term))
if (!is.na(CUTOFF)) {
  n_before <- nrow(api_all)
  api_all <- api_all %>% filter(substr(date, 1, 8) <= CUTOFF)
  cat(sprintf("  cutoff %s: %d of %d API rows kept\n", CUTOFF, nrow(api_all), n_before))
}

api <- api_all %>%
  mutate(
    vote_num = case_when(
      vote == "찬성" ~ 1L,
      vote == "반대" ~ 6L,
      vote == "기권" ~ 9L,
      TRUE ~ NA_integer_
    )
  ) %>%
  filter(!is.na(vote_num), !is.na(member_id), !is.na(bill_id)) %>%
  # pivot_wider orders legislators and votes by first appearance, and the
  # estimates depend on that order, so fix it explicitly.
  arrange(term, date, bill_id, member_id) %>%
  mutate(vote_id = paste(term, bill_id, sep = "_"))

if (is.na(VINTAGE)) VINTAGE <- paste0("v", max(substr(api$date, 1, 8)))
cat(sprintf("  vintage %s\n", VINTAGE))

# ── Member metadata ────────────────────────────────────────
# Name and roll-call party per member-term, taken from the member's latest vote
rc_meta <- api %>%
  group_by(member_id, term) %>%
  summarise(member_name = last(member_name), party_rc = last(party),
            n_rc_party = n_distinct(party), .groups = "drop")
if (any(rc_meta$n_rc_party > 1)) {
  cat(sprintf("  note: %d member-terms carry more than one roll-call party label\n",
              sum(rc_meta$n_rc_party > 1)))
}

members <- bind_rows(lapply(TERMS, function(t) {
  path <- file.path(MEMBERS_DIR, sprintf("members_%d.parquet", t))
  if (!file.exists(path)) {
    warning(sprintf("%s not found: the %dth Assembly keeps the roll-call party", path, t))
    return(NULL)
  }
  m <- read_parquet(path)
  data.frame(member_id = m$mona_cd, term = as.integer(t), party_elected = m$party,
             stringsAsFactors = FALSE)
}))
if (!nrow(members)) {
  members <- data.frame(member_id = character(), term = integer(),
                        party_elected = character())
}
if (anyDuplicated(members[c("member_id", "term")])) {
  stop("member metadata has more than one row per (member_id, term)")
}

member_meta <- rc_meta %>%
  left_join(members, by = c("member_id", "term")) %>%
  mutate(party = coalesce(party_elected, party_rc))
party_fallback <- member_meta %>% group_by(term) %>%
  summarise(n = sum(is.na(party_elected)), .groups = "drop")
for (i in seq_len(nrow(party_fallback))) {
  cat(sprintf("  %dth: party at election for %d members, roll-call party fallback for %d\n",
              party_fallback$term[i],
              sum(member_meta$term == party_fallback$term[i]) - party_fallback$n[i],
              party_fallback$n[i]))
}
member_meta <- member_meta %>% dplyr::select(member_id, term, party, member_name)
if (anyDuplicated(member_meta[c("member_id", "term")])) {
  stop("member metadata has more than one row per (member_id, term)")
}

# Party bloc labels, carried on every output file for convenience.
party_bloc <- function(party) {
  dplyr::case_when(
    party %in% CONSERVATIVE ~ "conservative",
    party %in% LIBERAL ~ "liberal",
    party %in% c("정의당", "진보당", "기본소득당", "사회민주당") ~ "progressive",
    party == "조국혁신당" ~ "rebuilding",
    party %in% c("개혁신당", "새로운미래") ~ "centrist",
    party %in% c("민생당", "열린민주당") ~ "liberal_minor",
    TRUE ~ "independent"
  )
}


build_rollcall <- function(term_num, label_ids = TRUE) {
  sub <- api %>% filter(term == term_num)
  vw <- sub %>%
    distinct(member_id, vote_id, .keep_all = TRUE) %>%
    dplyr::select(member_id, vote_id, vote_num) %>%
    pivot_wider(names_from = vote_id, values_from = vote_num)
  mat <- as.matrix(vw[, -1]); rownames(mat) <- vw$member_id

  minority <- apply(mat, 2, function(col) {
    v <- col[!is.na(col) & col != 9]
    if (!length(v)) return(0)
    min(mean(v == 1), mean(v == 6))
  })
  mat <- mat[, minority >= MIN_MINORITY, drop = FALSE]
  active <- apply(mat, 1, function(r) sum(!is.na(r) & r != 9)) >= MIN_VOTES
  mat <- mat[active, , drop = FALSE]

  cat(sprintf("  %dth: %d legislators x %d contested votes\n",
              term_num, nrow(mat), ncol(mat)))
  # Look the party up within the term (positions from a term subset must not
  # index the full vector).
  mm_t <- member_meta[member_meta$term == term_num, ]
  rollcall(mat, yea = 1, nay = 6, missing = 9, notInLegis = NA,
           legis.names = rownames(mat),
           legis.data = data.frame(
             ID = rownames(mat),
             party = match(mm_t$party[match(rownames(mat), mm_t$member_id)],
                           sort(unique(member_meta$party))),
             stringsAsFactors = FALSE),
           desc = sprintf("%dth Korean National Assembly", term_num))
}

# ============================================================
# 1. Per-assembly W-NOMINATE
# ============================================================
# Each assembly is scaled on its own. The recovered configuration is
# identified only up to a reflection, so the sign of the axis is arbitrary
# and is fixed here by anchoring on a named conservative legislator. Scores
# are comparable WITHIN an assembly and NOT across assemblies.

cat("\n[1/3] Per-assembly W-NOMINATE\n")
rc_list <- list()
wnom_scores <- list()
term_log <- list()

for (t in TERMS) {
  rcobj <- build_rollcall(t)
  rc_list[[as.character(t)]] <- rcobj

  anchor <- anchor_index(rownames(rcobj$votes), t)

  # Two fits. The one-dimensional fit is the series the analysis uses, because
  # the quantities of interest are defined on a single dimension. The
  # two-dimensional fit is retained because its second dimension is what users
  # comparing configurations will want, and because its eigenvalues feed the
  # dimensionality diagnostics.
  fit  <- wnominate(rcobj, dims = 1, polarity = anchor, verbose = FALSE)
  fit2 <- wnominate(rcobj, dims = 2, polarity = c(anchor, anchor), verbose = FALSE)

  sc <- data.frame(
    member_id = rownames(fit$legislators),
    term = t,
    wnom_1d = fit$legislators$coord1D,
    stringsAsFactors = FALSE
  )
  sc2 <- data.frame(
    member_id = rownames(fit2$legislators),
    wnom2d_dim1 = fit2$legislators$coord1D,
    wnom2d_dim2 = fit2$legislators$coord2D,
    stringsAsFactors = FALSE
  )
  sc <- dplyr::left_join(sc, sc2, by = "member_id")

  # Orient to the Voteview convention: positive = conservative, negative =
  # liberal. Without this the sign is whatever the anchor happened to produce.
  sc <- sc %>% left_join(member_meta %>% filter(term == t) %>%
                           dplyr::select(member_id, party), by = "member_id")
  if (mean(sc$wnom_1d[sc$party %in% CONSERVATIVE], na.rm = TRUE) <
      mean(sc$wnom_1d[sc$party %in% LIBERAL], na.rm = TRUE)) {
    sc$wnom_1d <- -sc$wnom_1d
    cat(sprintf("    (%dth: flipped to positive = conservative)\n", t))
  }
  if (mean(sc$wnom2d_dim1[sc$party %in% CONSERVATIVE], na.rm = TRUE) <
      mean(sc$wnom2d_dim1[sc$party %in% LIBERAL], na.rm = TRUE)) {
    sc$wnom2d_dim1 <- -sc$wnom2d_dim1
    sc$wnom2d_dim2 <- -sc$wnom2d_dim2
  }
  wnom_scores[[as.character(t)]] <- sc %>% dplyr::select(-party)

  cat(sprintf("    APRE 1D = %.3f, 2D = %.3f | eigenvalues > 1: %d\n",
              fit$fits["apre1D"], fit2$fits["apre2D"],
              sum(fit2$eigenvalues > 1, na.rm = TRUE)))

  dates <- substr(api_all$date[api_all$term == t], 1, 8)
  term_log[[as.character(t)]] <- list(
    term = t,
    first_vote_date = min(dates), last_vote_date = max(dates),
    recorded_votes = length(unique(api_all$bill_id[api_all$term == t])),
    legislators = nrow(rcobj$votes), contested_votes = ncol(rcobj$votes),
    polarity_anchor = POLARITY_ANCHOR[[as.character(t)]],
    party_fallback_members = sum(party_fallback$n[party_fallback$term == t]),
    apre_1d = unname(fit$fits["apre1D"]), apre_2d = unname(fit2$fits["apre2D"]))
}

wnom <- bind_rows(wnom_scores) %>%
  left_join(member_meta, by = c("member_id", "term")) %>%
  mutate(party_bloc = party_bloc(party), vintage = VINTAGE) %>%
  dplyr::select(member_id, member_name, party, party_bloc, term,
                wnom_1d, wnom2d_dim1, wnom2d_dim2, vintage)

write.csv(wnom, file.path(OUT, "ideal_points_wnominate.csv"), row.names = FALSE)
cat(sprintf("  wrote ideal_points_wnominate.csv (%d rows)\n", nrow(wnom)))

# ============================================================
# 2. Chained bridging alignment
# ============================================================
# Put every assembly into the units of the reference assembly by regressing,
# for the legislators who serve in both, the earlier term's already-aligned
# score on the later term's raw score. The fitted line is then applied to the
# whole later term. Alignment chains forward: 21st onto 20th, 22nd onto the
# aligned 21st.
#
# This is an affine map, so it corrects both the arbitrary sign and the
# arbitrary scale, but it assumes that bridging legislators do not move on
# average. Where they do move, that movement is absorbed into the mapping.

cat("\n[2/3] Chained bridging alignment\n")

bridged <- wnom %>% mutate(bridged_1d = NA_real_)
bridged$bridged_1d[bridged$term == REF_TERM] <- bridged$wnom_1d[bridged$term == REF_TERM]

alignment_log <- data.frame()
for (t in c(21, 22)) {
  prev <- t - 1
  ids <- intersect(bridged$member_id[bridged$term == prev],
                   bridged$member_id[bridged$term == t])
  a <- bridged %>% filter(term == prev, member_id %in% ids) %>% arrange(member_id)
  b <- bridged %>% filter(term == t,    member_id %in% ids) %>% arrange(member_id)
  stopifnot(identical(a$member_id, b$member_id))

  fit <- lm(a$bridged_1d ~ b$wnom_1d)
  slope <- unname(coef(fit)[2]); intercept <- unname(coef(fit)[1])

  idx <- bridged$term == t
  bridged$bridged_1d[idx] <- intercept + slope * bridged$wnom_1d[idx]

  cat(sprintf("  %dth onto %dth: %d bridging legislators, slope %+.4f, intercept %+.4f, R2 %.4f\n",
              t, prev, length(ids), slope, intercept, summary(fit)$r.squared))
  alignment_log <- rbind(alignment_log, data.frame(
    term = t, reference_term = prev, n_bridging = length(ids),
    slope = slope, intercept = intercept, r_squared = summary(fit)$r.squared))
}
alignment_log$vintage <- VINTAGE

write.csv(bridged %>% dplyr::select(member_id, member_name, party, party_bloc, term,
                                    wnom_1d, bridged_1d, vintage),
          file.path(OUT, "ideal_points_bridged.csv"), row.names = FALSE)
write.csv(alignment_log, file.path(OUT, "ideal_points_bridging_params.csv"),
          row.names = FALSE)
cat(sprintf("  wrote ideal_points_bridged.csv (%d rows) and the alignment parameters\n",
            nrow(bridged)))

# ============================================================
# 3. Pooled DW-NOMINATE
# ============================================================
# Estimate all three assemblies jointly, with bridging legislators anchoring
# a single scale. IMPORTANT: dwnominate represents each legislator's
# trajectory as a polynomial in the term index and requires at least five
# sessions to fit even a linear one. With three assemblies it admits only a
# constant, so every legislator receives ONE position covering all terms.
# Cross-term change in a party mean is therefore entirely compositional here.

dw_seconds <- NA_real_
if (SKIP_DW) {
  cat("\n[3/3] Pooled DW-NOMINATE: skipped (--skip-dw)\n")
} else {
  cat("\n[3/3] Pooled DW-NOMINATE\n")
  if (!requireNamespace("dwnominate", quietly = TRUE)) {
    stop("dwnominate is not installed. See the header of this script.")
  }
  library(dwnominate)
  dw_start_time <- Sys.time()

  # Starting values: with fewer than five sessions dwnominate cannot build
  # common-space starts on its own, so scale one pooled matrix in which each
  # legislator appears once and all three assemblies' votes are stacked.
  pooled <- api %>%
    distinct(member_id, vote_id, .keep_all = TRUE) %>%
    dplyr::select(member_id, vote_id, vote_num) %>%
    pivot_wider(names_from = vote_id, values_from = vote_num)
  pmat <- as.matrix(pooled[, -1]); rownames(pmat) <- pooled$member_id
  keep <- apply(pmat, 2, function(col) {
    v <- col[!is.na(col) & col != 9]
    length(v) > 0 && min(mean(v == 1), mean(v == 6)) >= MIN_MINORITY
  })
  pmat <- pmat[, keep, drop = FALSE]
  pmat <- pmat[apply(pmat, 1, function(r) sum(!is.na(r) & r != 9)) >= MIN_VOTES, , drop = FALSE]
  cat(sprintf("  pooled starting matrix: %d legislators x %d votes\n",
              nrow(pmat), ncol(pmat)))

  cons_all <- member_meta %>% filter(party %in% CONSERVATIVE) %>% pull(member_id)
  pooled_rc <- rollcall(pmat, yea = 1, nay = 6, missing = 9, notInLegis = NA,
                        legis.names = rownames(pmat),
                        legis.data = data.frame(
                          ID = rownames(pmat),
                          party = as.integer(rownames(pmat) %in% cons_all),
                          stringsAsFactors = FALSE))
  p_anchor <- anchor_index(rownames(pmat), REF_TERM)
  start_fit <- wnominate(pooled_rc, dims = 2,
                         polarity = c(p_anchor, p_anchor), verbose = FALSE)

  polarity <- sapply(TERMS, function(t) {
    anchor_index(rownames(rc_list[[as.character(t)]]$votes), t)
  })

  set.seed(DW_SEED)
  fit <- dwnominate(unname(rc_list), id = "ID", start = start_fit,
                    dims = 1, model = 0, polarity = polarity)

  dw <- fit$legislators %>%
    mutate(term = as.integer(session) + 19L) %>%
    dplyr::select(member_id = ID, term, dwnom_1d = coord1D) %>%
    left_join(member_meta, by = c("member_id", "term"))

  ref <- dw %>% filter(term == 20)
  if (mean(ref$dwnom_1d[ref$party %in% CONSERVATIVE], na.rm = TRUE) <
      mean(ref$dwnom_1d[ref$party %in% LIBERAL], na.rm = TRUE)) {
    dw$dwnom_1d <- -dw$dwnom_1d
    cat("  (flipped to positive = conservative)\n")
  }

  write.csv(dw %>% mutate(party_bloc = party_bloc(party), vintage = VINTAGE) %>%
              dplyr::select(member_id, member_name, party, party_bloc, term, dwnom_1d,
                            vintage),
            file.path(OUT, "ideal_points_dwnominate.csv"), row.names = FALSE)
  cat(sprintf("  wrote ideal_points_dwnominate.csv (%d rows)\n", nrow(dw)))
  saveRDS(fit, file.path(OUT, "dwnominate_fit.rds"))
  dw_seconds <- as.numeric(difftime(Sys.time(), dw_start_time, units = "secs"))
  cat(sprintf("  pooled estimation took %.0f seconds\n", dw_seconds))
}

# ============================================================
# Comparison
# ============================================================
cat("\n", strrep("=", 72), "\n", sep = "")
cat("INTER-PARTY DISTANCE UNDER EACH SERIES\n")
cat(strrep("=", 72), "\n\n")

gap <- function(df, col) {
  sapply(TERMS, function(t) {
    a <- mean(df[[col]][df$term == t & df$party %in% CONSERVATIVE], na.rm = TRUE)
    b <- mean(df[[col]][df$term == t & df$party %in% LIBERAL], na.rm = TRUE)
    abs(a - b)
  })
}
g1 <- gap(wnom, "wnom_1d"); g2 <- gap(bridged, "bridged_1d")
cat("  term   per-assembly   bridged")
if (!SKIP_DW) cat("   pooled DW") ; cat("\n")
for (i in 1:3) {
  cat(sprintf("   %2d      %.3f        %.3f", TERMS[i], g1[i], g2[i]))
  if (!SKIP_DW) cat(sprintf("      %.3f", gap(dw, "dwnom_1d")[i]))
  cat("\n")
}
cat(sprintf("\n  growth 20th to 22nd:  %+.1f%%       %+.1f%%",
            100 * (g1[3] - g1[1]) / g1[1], 100 * (g2[3] - g2[1]) / g2[1]))
if (!SKIP_DW) {
  g3 <- gap(dw, "dwnom_1d")
  cat(sprintf("     %+.1f%%", 100 * (g3[3] - g3[1]) / g3[1]))
}
cat("\n\n  The per-assembly series is renormalized within each term, so it reports\n")
cat("  much larger growth than either series that holds a scale fixed across\n")
cat("  terms. Do not compare per-assembly scores across assemblies.\n")

writeLines(capture.output(sessionInfo()),
           file.path(OUT, "ideal_points_sessioninfo.txt"))

# ============================================================
# Manifest
# ============================================================
sha256_file <- function(path) digest::digest(file = path, algo = "sha256")
pkg_version <- function(p) {
  if (requireNamespace(p, quietly = TRUE)) as.character(packageVersion(p)) else NA
}
script_path <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
git_head <- tryCatch(
  suppressWarnings(system2("git", c("rev-parse", "HEAD"), stdout = TRUE, stderr = FALSE)),
  error = function(e) NA_character_)
if (!length(git_head) || !is.null(attr(git_head, "status"))) git_head <- NA_character_
dw_remote_sha <- if (requireNamespace("dwnominate", quietly = TRUE)) {
  d <- packageDescription("dwnominate")
  if (is.null(d$RemoteSha)) NA_character_ else d$RemoteSha
} else NA_character_

outputs <- c("ideal_points_wnominate.csv", "ideal_points_bridged.csv",
             "ideal_points_bridging_params.csv",
             if (!SKIP_DW) c("ideal_points_dwnominate.csv", "dwnominate_fit.rds"),
             "ideal_points_sessioninfo.txt")
members_files <- file.path(MEMBERS_DIR, sprintf("members_%d.parquet", TERMS))

manifest <- list(
  vintage = VINTAGE,
  cutoff = CUTOFF,
  created = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z"),
  script = list(path = if (length(script_path)) script_path[1] else NA_character_,
                sha256 = if (length(script_path)) sha256_file(script_path[1]) else NA_character_,
                git_head = git_head[1]),
  input = list(path = INPUT, sha256 = sha256_file(INPUT),
               api_rows_after_cutoff = nrow(api_all), scaled_rows = nrow(api)),
  members = lapply(members_files, function(p) {
    list(path = p, sha256 = if (file.exists(p)) sha256_file(p) else NA_character_)
  }),
  settings = list(min_minority = MIN_MINORITY, min_votes = MIN_VOTES,
                  ref_term = REF_TERM, conservative = CONSERVATIVE, liberal = LIBERAL,
                  polarity_anchor = as.list(POLARITY_ANCHOR),
                  row_order = c("term", "date", "bill_id", "member_id"),
                  party = "party at election (members_{term}.party), roll-call party fallback",
                  skip_dw = SKIP_DW),
  seeds = list(dwnominate = DW_SEED),
  terms = unname(term_log),
  bridging = alignment_log,
  dwnominate_seconds = dw_seconds,
  r_version = R.version.string,
  packages = lapply(setNames(nm = c("arrow", "dplyr", "tidyr", "pscl", "wnominate",
                                    "dwnominate", "jsonlite", "digest")), pkg_version),
  dwnominate_remote_sha = dw_remote_sha,
  outputs = lapply(setNames(nm = outputs), function(f) sha256_file(file.path(OUT, f)))
)
jsonlite::write_json(manifest, file.path(OUT, "ideal_points_manifest.json"),
                     auto_unbox = TRUE, pretty = TRUE, na = "null", digits = NA)
cat(sprintf("\n  wrote ideal_points_manifest.json (vintage %s)\n", VINTAGE))
cat("\nDone.\n")
