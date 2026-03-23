# estimate_idealpoints.R
# ============================================================
# Estimate legislator ideal points from roll call votes
# using W-NOMINATE (20-22대, clean API data)
#
# Prerequisites:
#   install.packages(c("arrow", "dplyr", "tidyr", "wnominate", "pscl"))
#
# Usage:
#   Rscript estimate_idealpoints.R          # All 20-22대
#   Rscript estimate_idealpoints.R --age 22 # Single assembly
# ============================================================

library(arrow)
library(dplyr)
library(tidyr)

# ── Configuration ──────────────────────────────────────────

script_dir <- tryCatch(dirname(sys.frame(1)$ofile), error = function(e) ".")
DATA_DIR <- file.path(script_dir, "data")
PROCESSED <- file.path(DATA_DIR, "processed")
OUTPUT <- file.path(DATA_DIR, "processed")

# Parse args
args <- commandArgs(trailingOnly = TRUE)
target_age <- if ("--age" %in% args) as.integer(args[which(args == "--age") + 1]) else NULL

# ── Load Data ──────────────────────────────────────────────

cat("Loading roll call data...\n")
rc <- read_parquet(file.path(PROCESSED, "roll_calls_all.parquet"))

# Filter to API data only (clean, 20-22대)
rc_api <- rc %>%
  filter(source == "api") %>%
  mutate(term = as.integer(term)) %>%
  filter(!is.na(member_id), !is.na(bill_id))

cat(sprintf("  API votes: %s rows, %d assemblies\n",
            format(nrow(rc_api), big.mark = ","),
            n_distinct(rc_api$term)))

# ── Estimate per assembly ──────────────────────────────────

estimate_nominate <- function(votes_df, age) {
  cat(sprintf("\n========================================\n"))
  cat(sprintf("W-NOMINATE Estimation: %d대\n", age))
  cat(sprintf("========================================\n"))

  sub <- votes_df %>% filter(term == age)
  cat(sprintf("  Votes: %s | Members: %d | Bills: %d\n",
              format(nrow(sub), big.mark = ","),
              n_distinct(sub$member_id),
              n_distinct(sub$bill_id)))

  # Build vote matrix: rows = legislators, columns = bills
  # Values: 1 = yea, 6 = nay, 9 = abstain, NA = missing
  sub <- sub %>%
    mutate(
      vote_num = case_when(
        vote == "찬성" ~ 1L,
        vote == "반대" ~ 6L,
        vote == "기권" ~ 9L,
        vote == "불참" ~ NA_integer_,
        TRUE ~ NA_integer_
      )
    ) %>%
    filter(!is.na(vote_num))

  vote_long <- sub %>%
    distinct(member_id, bill_id, .keep_all = TRUE) %>%
    select(member_id, bill_id, vote_num)

  vote_wide <- vote_long %>%
    pivot_wider(names_from = bill_id, values_from = vote_num)

  member_ids <- vote_wide$member_id
  vote_matrix <- as.matrix(vote_wide[, -1])
  rownames(vote_matrix) <- member_ids

  cat(sprintf("  Vote matrix: %d legislators x %d bills\n",
              nrow(vote_matrix), ncol(vote_matrix)))

  # Filter: keep bills with at least 2.5% minority
  # (unanimous votes don't help identify ideal points)
  minority_pct <- apply(vote_matrix, 2, function(col) {
    valid <- col[!is.na(col) & col != 9]  # exclude abstain/missing
    if (length(valid) == 0) return(0)
    min(mean(valid == 1), mean(valid == 6))
  })
  contested <- minority_pct >= 0.025
  cat(sprintf("  Contested bills (>2.5%% minority): %d / %d (%.1f%%)\n",
              sum(contested), length(contested),
              sum(contested) / length(contested) * 100))

  vote_matrix_filtered <- vote_matrix[, contested]

  # Filter: keep legislators with at least 20 valid votes on contested bills
  valid_votes <- apply(vote_matrix_filtered, 1, function(row) {
    sum(!is.na(row) & row != 9)
  })
  active <- valid_votes >= 20
  cat(sprintf("  Active legislators (>=20 contested votes): %d / %d\n",
              sum(active), length(active)))

  vote_matrix_final <- vote_matrix_filtered[active, ]

  # Create rollcall object
  if (!requireNamespace("pscl", quietly = TRUE)) {
    cat("  ERROR: pscl package required. install.packages('pscl')\n")
    return(NULL)
  }
  library(pscl)

  rc_obj <- rollcall(
    vote_matrix_final,
    yea = 1, nay = 6, missing = 9,
    notInLegis = NA,
    legis.names = rownames(vote_matrix_final),
    desc = sprintf("Korean National Assembly %d대", age)
  )

  cat(sprintf("  rollcall object: %d legislators x %d votes\n",
              rc_obj$n, rc_obj$m))

  # Run W-NOMINATE (1D)
  if (!requireNamespace("wnominate", quietly = TRUE)) {
    cat("  ERROR: wnominate package required. install.packages('wnominate')\n")
    return(NULL)
  }
  library(wnominate)

  cat("  Running W-NOMINATE (1D)...\n")
  result <- tryCatch(
    wnominate(rc_obj, dims = 1, polarity = 1, minvotes = 20, lop = 0.025),
    error = function(e) {
      cat(sprintf("  W-NOMINATE error: %s\n", e$message))
      NULL
    }
  )

  if (is.null(result)) return(NULL)

  # Extract ideal points
  scores <- data.frame(
    member_id = rownames(result$legislators),
    term = age,
    coord1D = result$legislators$coord1D,
    se1D = result$legislators$se1D,
    stringsAsFactors = FALSE
  )

  # Add legislator metadata
  member_meta <- votes_df %>%
    filter(term == age) %>%
    distinct(member_id, member_name, party) %>%
    group_by(member_id) %>%
    slice(1) %>%
    ungroup()

  scores <- scores %>%
    left_join(member_meta, by = "member_id")

  cat(sprintf("  Ideal points estimated for %d legislators\n", nrow(scores)))
  cat(sprintf("  Range: [%.3f, %.3f]\n", min(scores$coord1D, na.rm = TRUE),
              max(scores$coord1D, na.rm = TRUE)))

  # Summary by party
  party_summary <- scores %>%
    group_by(party) %>%
    summarise(
      n = n(),
      mean_coord = mean(coord1D, na.rm = TRUE),
      sd_coord = sd(coord1D, na.rm = TRUE),
      .groups = "drop"
    ) %>%
    arrange(mean_coord)

  cat("\n  Party ideal point means:\n")
  for (i in seq_len(nrow(party_summary))) {
    cat(sprintf("    %s: %.3f (SD=%.3f, N=%d)\n",
                party_summary$party[i],
                party_summary$mean_coord[i],
                party_summary$sd_coord[i],
                party_summary$n[i]))
  }

  # Save
  outpath <- file.path(OUTPUT, sprintf("ideal_points_%d.csv", age))
  write.csv(scores, outpath, row.names = FALSE)
  cat(sprintf("\n  Saved: %s\n", basename(outpath)))

  return(scores)
}

# ── Run ────────────────────────────────────────────────────

ages <- if (!is.null(target_age)) target_age else c(20, 21, 22)

all_scores <- list()
for (age in ages) {
  scores <- estimate_nominate(rc_api, age)
  if (!is.null(scores)) {
    all_scores[[as.character(age)]] <- scores
  }
}

# Combine and save
if (length(all_scores) > 0) {
  combined <- bind_rows(all_scores)
  outpath <- file.path(OUTPUT, "ideal_points_all.csv")
  write.csv(combined, outpath, row.names = FALSE)
  cat(sprintf("\nCombined ideal points: %s (%d legislators)\n",
              basename(outpath), nrow(combined)))
}

cat("\nDone.\n")
