# Install the packages a maintained pipeline loads, at their current versions ----
# Run from a paper repository's root by the shared check workflow, twice: first with no
# argument, for the maintained code, and then with --deposit once the deposit has been
# fetched, for the deposited scripts that run_all.R reruns as a program. The list is read
# off the code itself, so there is no manifest to keep in sync with it.

library(readr)
library(stringr)
library(purrr)

deposit <- "--deposit" %in% commandArgs(trailingOnly = TRUE)

# Packages that are not on CRAN, and where they live ----
github_sources <- c(
  excheckr = "acoppock/excheckr",
  interference = "szonszein/interference"
)

# Packages the code loads ----
# Only code counts: comments and the prose of a .qmd name retired packages (commarobust,
# maptools) in the course of explaining what replaced them. original/ and
# original_extracted/ hold the deposit, which is scanned only on the --deposit pass.
code_lines <- function(path) {
  lines <- read_lines(path)
  if (str_detect(path, "\\.(qmd|Rmd)$")) {
    fence <- str_detect(lines, "^\\s*```")
    lines <- lines[cumsum(fence) %% 2 == 1 & !fence]
  }
  str_subset(lines, "^\\s*#", negate = TRUE)
}

files <- if (deposit) {
  list.files(c("original_extracted", "original"), pattern = "\\.(R|r|qmd|Rmd)$",
             recursive = TRUE, full.names = TRUE)
} else {
  list.files(".", pattern = "\\.(R|qmd|Rmd)$", recursive = TRUE) |>
    str_subset("^original", negate = TRUE)
}

code <- files |>
  map(code_lines) |>
  unlist() |>
  str_remove("#.*$") |>
  str_remove_all("[\"']")

loaded <- c("library", "require", "requireNamespace") |>
  map(\(call) str_extract_all(code, str_glue("(?<=\\b{call}\\()[A-Za-z][A-Za-z0-9.]*"))) |>
  c(list(str_extract_all(code, "[A-Za-z][A-Za-z0-9.]*(?=::)"))) |>
  unlist() |>
  unique()

# Where each one comes from ----
base_packages <- rownames(installed.packages(priority = "base"))
on_cran <- rownames(available.packages())

from_cran <- loaded |>
  intersect(on_cran) |>
  setdiff(base_packages)
from_github <- github_sources[intersect(names(github_sources), loaded)]
not_found <- setdiff(loaded, c(on_cran, names(github_sources), base_packages))

print(str_glue("{if (deposit) 'Deposit' else 'Maintained code'}: installing ",
               "{length(from_cran)} packages from CRAN and {length(from_github)} from GitHub."))
print(str_glue("Named in the code but on neither list, so not installed: {str_flatten_comma(sort(not_found))}"))

# Installing ----
# The maintained code's packages go in as one install, so a failure stops the check. The
# deposit's go in one at a time, so a package the deposit needs and current CRAN cannot
# build is recorded by the archive rerun as that script's failure, as it would be anywhere.
if (deposit) {
  failed <- c(from_cran, unname(from_github)) |>
    keep(\(pkg) inherits(try(pak::pkg_install(pkg, ask = FALSE)), "try-error"))
  print(str_glue("Deposit packages that failed to install: {str_flatten_comma(failed)}"))
} else {
  pak::pkg_install(c(from_cran, unname(from_github)), ask = FALSE)
}
