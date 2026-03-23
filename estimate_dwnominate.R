# estimate_dwnominate.R
# ============================================================
# DW-NOMINATE estimation for 20-22대 Korean National Assembly
#
# Pools roll call votes across assemblies, using bridging
# legislators (재선 의원) to anchor a common ideological scale.
#
# Prerequisites:
#   install.packages(c("arrow", "dplyr", "tidyr", "dwnominate", "pscl"))
#
# Usage:
#   Rscript estimate_dwnominate.R
# ============================================================

library(arrow)
library(dplyr)
library(tidyr)
library(pscl)

# Check for dwnominate
if (!requireNamespace("dwnominate", quietly = TRUE)) {
  cat("Installing dwnominate...\n")
  install.packages("dwnominate", repos = "https://cloud.r-project.org",
                   lib = "~/Library/R/arm64/4.4/library", quiet = TRUE)
}
library(dwnominate)

DATA_DIR <- "data/processed"

# ── 1. Load and prepare data ──────────────────────────────

cat("Loading roll call data...\n")
rc <- read_parquet(file.path(DATA_DIR, "roll_calls_all.parquet"))

api <- rc %>%
  filter(source == "api", term %in% c(20, 21, 22)) %>%
  mutate(
    term = as.integer(term),
    vote_num = case_when(
      vote == "찬성" ~ 1L,
      vote == "반대" ~ 6L,
      vote == "기권" ~ 9L,
      vote == "불참" ~ NA_integer_,
      TRUE ~ NA_integer_
    )
  ) %>%
  filter(!is.na(vote_num), !is.na(member_id), !is.na(bill_id))

cat(sprintf("  Total votes: %s\n", format(nrow(api), big.mark = ",")))

# ── 2. Build congress indicator ────────────────────────────
# DW-NOMINATE needs a "congress" number for each vote
# Map: 20대=1, 21대=2, 22대=3

api <- api %>%
  mutate(congress = term - 19L)  # 20->1, 21->2, 22->3

# Create unique vote ID across assemblies
api <- api %>%
  mutate(vote_id = paste(term, bill_id, sep = "_"))

cat(sprintf("  Members: %d | Bills: %d | Congresses: %d\n",
            n_distinct(api$member_id),
            n_distinct(api$vote_id),
            n_distinct(api$congress)))

# ── 3. Check bridging legislators ─────────────────────────

member_congresses <- api %>%
  group_by(member_id) %>%
  summarise(congresses = list(sort(unique(congress))), .groups = "drop") %>%
  mutate(n_congresses = lengths(congresses))

bridge <- member_congresses %>% filter(n_congresses >= 2)
cat(sprintf("\n  Bridging legislators: %d / %d (%.1f%%)\n",
            nrow(bridge), nrow(member_congresses),
            nrow(bridge) / nrow(member_congresses) * 100))

# ── 4. Build vote matrix per congress ─────────────────────
# DW-NOMINATE expects a list of rollcall objects, one per congress

build_rollcall <- function(votes_df, congress_num) {
  sub <- votes_df %>% filter(congress == congress_num)

  vote_wide <- sub %>%
    distinct(member_id, vote_id, .keep_all = TRUE) %>%
    select(member_id, vote_id, vote_num) %>%
    pivot_wider(names_from = vote_id, values_from = vote_num)

  mat <- as.matrix(vote_wide[, -1])
  rownames(mat) <- vote_wide$member_id

  # Filter contested votes (>2.5% minority)
  minority <- apply(mat, 2, function(col) {
    v <- col[!is.na(col) & col != 9]
    if (length(v) == 0) return(0)
    min(mean(v == 1), mean(v == 6))
  })
  mat <- mat[, minority >= 0.025, drop = FALSE]

  # Filter active legislators (>=20 contested votes)
  active <- apply(mat, 1, function(r) sum(!is.na(r) & r != 9)) >= 20
  mat <- mat[active, , drop = FALSE]

  cat(sprintf("  Congress %d (%d대): %d legislators x %d contested votes\n",
              congress_num, congress_num + 19, nrow(mat), ncol(mat)))

  rollcall(mat, yea = 1, nay = 6, missing = 9, notInLegis = NA,
           legis.names = rownames(mat),
           desc = sprintf("%d대 Korean NA", congress_num + 19))
}

cat("\nBuilding rollcall objects...\n")
rc_list <- lapply(1:3, function(c) build_rollcall(api, c))

# ── 5. Run DW-NOMINATE ────────────────────────────────────

cat("\nRunning DW-NOMINATE (1D, 3 congresses)...\n")
cat("  This may take a few minutes...\n\n")

dw_result <- tryCatch(
  dwnominate(rc_list, dims = 1, polarity = rep(1, 3)),
  error = function(e) {
    cat(sprintf("DW-NOMINATE error: %s\n", e$message))
    NULL
  }
)

if (is.null(dw_result)) {
  cat("DW-NOMINATE failed. Exiting.\n")
  quit(status = 1)
}

# ── 6. Extract results ────────────────────────────────────

cat("\nExtracting results...\n")

# Get legislator metadata for labeling
member_meta <- api %>%
  distinct(member_id, member_name, party, term) %>%
  group_by(member_id) %>%
  summarise(
    member_name = first(member_name),
    parties = paste(unique(party), collapse = "/"),
    terms = paste(sort(unique(term)), collapse = ","),
    .groups = "drop"
  )

# Extract scores from each congress
all_scores <- list()
for (c in 1:3) {
  leg <- dw_result$legislators[[c]]
  scores <- data.frame(
    member_id = rownames(leg),
    term = c + 19L,
    coord1D = leg$coord1D,
    stringsAsFactors = FALSE
  )
  all_scores[[c]] <- scores
}

scores <- bind_rows(all_scores)
scores <- scores %>% left_join(member_meta, by = "member_id")

cat(sprintf("\nDW-NOMINATE Results: %d legislator-terms\n", nrow(scores)))
cat(sprintf("  Unique legislators: %d\n", n_distinct(scores$member_id)))

# ── 7. Summary by party per assembly ──────────────────────

cat("\n  Party means by assembly (DW-NOMINATE):\n")
party_summary <- scores %>%
  left_join(
    api %>% distinct(member_id, term, party),
    by = c("member_id", "term")
  ) %>%
  mutate(party = coalesce(party.y, party.x, parties)) %>%
  group_by(term, party) %>%
  summarise(n = n(), mean = mean(coord1D, na.rm = TRUE),
            sd = sd(coord1D, na.rm = TRUE), .groups = "drop") %>%
  filter(n >= 3) %>%
  arrange(term, mean)

for (t in c(20, 21, 22)) {
  cat(sprintf("\n  -- %d대 --\n", t))
  sub <- party_summary %>% filter(term == t)
  for (i in seq_len(nrow(sub))) {
    cat(sprintf("    %s: %.3f (SD=%.3f, N=%d)\n",
                sub$party[i], sub$mean[i], sub$sd[i], sub$n[i]))
  }
}

# ── 8. Bridging legislators: score stability ──────────────

cat("\n  Bridging legislator score changes:\n")
bridge_scores <- scores %>%
  filter(member_id %in% bridge$member_id) %>%
  arrange(member_id, term) %>%
  group_by(member_id) %>%
  filter(n() >= 2) %>%
  mutate(shift = coord1D - lag(coord1D)) %>%
  filter(!is.na(shift))

cat(sprintf("    Mean absolute shift: %.3f\n", mean(abs(bridge_scores$shift))))
cat(sprintf("    Median absolute shift: %.3f\n", median(abs(bridge_scores$shift))))
cat(sprintf("    Correlation across terms: %.3f\n",
            {
              wide <- scores %>%
                filter(member_id %in% bridge$member_id) %>%
                select(member_id, term, coord1D) %>%
                pivot_wider(names_from = term, values_from = coord1D, names_prefix = "t")
              if ("t20" %in% names(wide) && "t21" %in% names(wide))
                cor(wide$t20, wide$t21, use = "complete.obs")
              else NA
            }))

# ── 9. Save ───────────────────────────────────────────────

outpath <- file.path(DATA_DIR, "dw_ideal_points_20_22.csv")
write.csv(scores, outpath, row.names = FALSE)
cat(sprintf("\nSaved: %s (%d rows)\n", basename(outpath), nrow(scores)))

cat("\nDone.\n")
