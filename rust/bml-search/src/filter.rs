//! Passages search should not show: reference lists, funding and
//! competing-interest statements (the spec's "garbage results" anti-goal).
//! A heuristic on the chunk text, as a pure function.

use std::sync::LazyLock;

use regex::Regex;

/// How many reference signals make a passage a reference list.
pub const REFERENCE_SIGNALS: usize = 3;

/// A passage that opens as a funding, interests or acknowledgements
/// statement: a heading ("Funding:", "Competing interests.") or "This study
/// was funded by" — not any sentence that merely starts with "Funding".
static STATEMENT: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"(?i)^\s*((funding|competing interests?|conflicts? of interest|declarations? of interest|acknowledge?ments?)(\s+(statement|information|sources?))?\s*[:.]|(this|the) (work|study|research|trial) was (supported|funded) by)",
    )
    .expect("valid")
});
/// A DOI, with or without `doi:`.
static DOI: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\b10\.\d{4,9}/\S+").expect("valid"));
/// A year in brackets then a volume: `(2022) 27:`, `(2017). 16(3)`.
static YEAR_VOLUME: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\(\d{4}\)\s*[.:;,]?\s*\d+").expect("valid"));
/// Volume(issue):pages, `56(9):37-44`.
static PAGES: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\d+\(\d+\):\s*\d+\s*[-–]\s*\d+").expect("valid"));
/// `et al.`, counted only outside an in-text citation's `(… et al., 2025)`.
static ET_AL: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"et al\.(,\s*\d{4}[a-z]?\))?").expect("valid"));
/// A numbered entry: `5. Mcintyre RS,`, `10. Badawy Y.,`.
static NUMBERED: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(^|\s)\d{1,3}\.\s+[A-Z][a-z]+\s+[A-Z]{1,3}\.?[,\s]").expect("valid")
});

/// Whether `passage` is a reference list or a funding, interests or
/// acknowledgements statement rather than content.
#[must_use]
pub fn is_boilerplate(passage: &str) -> bool {
    if STATEMENT.is_match(passage) {
        return true;
    }
    let dois = DOI.find_iter(passage).count();
    let et_al = ET_AL
        .captures_iter(passage)
        .filter(|c| c.get(1).is_none())
        .count();
    // A bibliography always has a hard signal (a DOI, a page range or a
    // year-volume); narrative citations ("Cuijpers et al. found…") have none.
    let hard = dois + YEAR_VOLUME.find_iter(passage).count() + PAGES.find_iter(passage).count();
    let signals = hard + dois + et_al + NUMBERED.find_iter(passage).count();
    hard > 0 && signals >= REFERENCE_SIGNALS
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reference_list_is_boilerplate() {
        // Real chunks from the demo library, 2026-11-15.
        for passage in [
            "Mol Psychiatr. (2022) 27:1286–99. doi: 10.1038/s41380-021-01381-x  5. Mcintyre RS, \
             Alsuwaidan M, Baune BT, Berk M, Demyttenaere K, Goldberg JF, et al. Treatment-resistant \
             depression: definition, prevalence, detection, management",
            "10. Badawy Y., Spector A., Li Z., and Desai R., \"The Risk of Depression in the \
             Menopausal Stages: A Systematic Review and Meta‐Analysis,\" Journal of Affective \
             Disorders 357 (2024): 126–133, 10.1016/J.JAD.2024.04.041.  11. Sharm",
            "World Psychiatry. (2017). 16(3):287-298. doi:10.1002/wps.20472  38. J Linardon, \
             P Cuijpers, et al. The efficacy of app-supported smartphone interventions for mental \
             health problems: a meta-analysis of randomized controlled tria",
            "An assessment of sedentary time among undergraduate students at a Canadian university. \
             Int J Exerc Sci. (2017). 10(8):1116-1129. doi:10.70252/cddk5126  15 R Beiter, R Nash, \
             et al. The prevalence and correlates of depression, an",
            "China Sport Science and Technology. (2020). 56(9):37-44  10 J. Song, Z. Z. Liu, et al. \
             Effects of Aerobic Exercise, Traditional Chinese Exercises, and Meditation on \
             Depressive Symptoms of College Student: A Meta‐Analysis of Ran",
        ] {
            assert!(is_boilerplate(passage), "{passage}");
        }
    }

    #[test]
    fn funding_statement_is_boilerplate() {
        assert!(is_boilerplate(
            "Funding: This work was supported by the National Health and Medical Research \
             Council (grant 2009876)."
        ));
        assert!(is_boilerplate(
            "Competing interests: The authors declare no competing interests."
        ));
        assert!(is_boilerplate(
            "This study was funded by the Wellcome Trust (grant 222222/Z/20/Z). The funder had \
             no role in study design."
        ));
    }

    #[test]
    fn findings_are_not_boilerplate() {
        for passage in [
            "Vigorous exercise is the most effective intensity for treating depression, which \
             differs from our TCC study’s findings, which indicate that our intervention may yield \
             better results for depressive symptoms (Li et al., 2025).",
            "Given the increasing attention on psilocybin for psychiatric diagnoses like depression \
             (Haikazian et al., 2023), we included it in our search terms but identified no \
             eligible studies.",
            "Postpartum care gaps are especially concerning because more than half of \
             pregnancy-related deaths occur during or after delivery, and many are considered \
             preventable with timely recognition and management.6",
            "We randomised 120 adults with moderate depression to exercise or usual care.",
            // A review's discussion: narrative citations, no bibliography.
            "Cuijpers et al. found larger effects for CBT, Furukawa et al. reported similar \
             response rates, and Linardon et al. showed that apps helped less.",
            "Cuijpers et al. (2020) and Li et al. [12] pooled 45 trials; (Furukawa et al. 2021) \
             reached the same conclusion for remission.",
            "Funding for community mental health services fell during the study period, which \
             may explain the lower uptake.",
        ] {
            assert!(!is_boilerplate(passage), "{passage}");
        }
    }
}
