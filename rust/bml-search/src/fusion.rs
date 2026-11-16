//! Weighted reciprocal-rank fusion and the one-hit-per-paper grouping, as
//! pure functions (Rust plan §3.4: vectors weighted 2×).

use std::collections::HashMap;

/// The reciprocal-rank constant: a chunk at rank `r` scores `w / (RRF_K + r)`.
pub const RRF_K: f64 = 60.0;
/// The weight of the vector list (Rust plan §3.4).
pub const VECTOR_WEIGHT: f64 = 2.0;
/// The weight of the word list.
pub const LEXICAL_WEIGHT: f64 = 1.0;

/// Fuse two ranked lists of chunk ids (best first) into `(chunk, score)`,
/// highest score first; ties keep first appearance (vectors before words).
#[must_use]
pub fn fuse(vector: &[i64], lexical: &[i64]) -> Vec<(i64, f64)> {
    let mut order: Vec<i64> = Vec::new();
    let mut scores: HashMap<i64, f64> = HashMap::new();
    for (list, weight) in [(vector, VECTOR_WEIGHT), (lexical, LEXICAL_WEIGHT)] {
        for (rank, id) in list.iter().enumerate() {
            let position = f64::from(u32::try_from(rank + 1).unwrap_or(u32::MAX));
            let entry = scores.entry(*id).or_insert_with(|| {
                order.push(*id);
                0.0
            });
            *entry += weight / (RRF_K + position);
        }
    }
    let mut fused: Vec<(i64, f64)> = order.into_iter().map(|id| (id, scores[&id])).collect();
    // Stable: equal scores keep first appearance.
    fused.sort_by(|a, b| b.1.total_cmp(&a.1));
    fused
}

/// The best chunk of each paper from `scored` (highest score first), as
/// `(paper, chunk, score)` in that order; a chunk of no paper in `paper_of` is
/// skipped.
#[must_use]
pub fn best_per_paper(scored: &[(i64, f64)], paper_of: &HashMap<i64, i64>) -> Vec<(i64, i64, f64)> {
    let mut seen = std::collections::HashSet::new();
    scored
        .iter()
        .filter_map(|(chunk, score)| {
            let paper = *paper_of.get(chunk)?;
            seen.insert(paper).then_some((paper, *chunk, *score))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::*;

    #[test]
    fn vector_rank_counts_double() {
        // Chunk 1 is first among vectors only, chunk 2 first among words only.
        let fused = fuse(&[1, 3], &[2, 4]);
        assert_eq!(fused[0].0, 1, "{fused:?}");
        let one = fused.iter().find(|(id, _)| *id == 1).unwrap().1;
        let two = fused.iter().find(|(id, _)| *id == 2).unwrap().1;
        assert!((one - 2.0 * two).abs() < 1e-12, "{one} {two}");
    }

    #[test]
    fn both_lists_beat_one() {
        let fused = fuse(&[1, 2], &[2, 3]);
        assert_eq!(fused[0].0, 2, "{fused:?}");
    }

    #[test]
    fn fused_scores_are_descending_and_unique() {
        let fused = fuse(&[5, 6, 7], &[7, 8]);
        let ids: Vec<i64> = fused.iter().map(|(id, _)| *id).collect();
        let unique: std::collections::BTreeSet<i64> = ids.iter().copied().collect();
        assert_eq!(unique.len(), ids.len());
        assert!(fused.windows(2).all(|w| w[0].1 >= w[1].1), "{fused:?}");
    }

    #[test]
    fn best_per_paper_keeps_one_row_per_paper() {
        // Chunks 1 and 2 belong to paper 10, chunk 3 to paper 20.
        let paper_of = HashMap::from([(1, 10), (2, 10), (3, 20)]);
        let best = best_per_paper(&[(2, 0.9), (3, 0.5), (1, 0.4)], &paper_of);
        assert_eq!(best, vec![(10, 2, 0.9), (20, 3, 0.5)]);
    }

    #[test]
    fn a_chunk_of_no_known_paper_is_skipped() {
        let paper_of = HashMap::from([(1, 10)]);
        assert_eq!(
            best_per_paper(&[(9, 1.0), (1, 0.5)], &paper_of),
            vec![(10, 1, 0.5)]
        );
    }
}
