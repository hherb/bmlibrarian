//! Topic libraries: the preset Europe PMC searches the app offers, and which
//! source a library downloads from (`library_state.topic_id`; null means
//! medRxiv). Spec: `docs/superpowers/specs/2026-11-15-investor-demo-europepmc-design.md`.

use bml_db::LIBRARY_STATE;
use bmlib::db::{execute, fetch_one, Db, Value};
use bmlib::publications::fetchers::europepmc::SEARCH_URL;
use bmlib::transparency::analyzer::encode_query;

use crate::PipelineError;

/// One preset topic: a name, the terms matched in title or abstract, and the
/// paper count measured when the preset was written (shown when offline).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Topic {
    /// Stable id, stored in `library_state.topic_id` and given to `--topic`.
    pub id: &'static str,
    /// The name the app shows.
    pub name: &'static str,
    /// Terms matched in title or abstract (any of them).
    pub terms: &'static [&'static str],
    /// Papers matching on 2026-11-15, the offline fallback count.
    pub stored_count: u32,
}

/// The presets the app offers, in the order it lists them (owner, 2026-11-15).
pub const TOPICS: &[Topic] = &[
    Topic {
        id: "depression-anxiety",
        name: "Depression & anxiety",
        terms: &["depression", "anxiety disorder"],
        stored_count: 8372,
    },
    Topic {
        id: "cardiology",
        name: "Heart failure & cardiology",
        terms: &[
            "heart failure",
            "atrial fibrillation",
            "myocardial infarction",
            "coronary artery disease",
        ],
        stored_count: 5513,
    },
    Topic {
        id: "obesity-glp1",
        name: "Obesity & GLP-1 drugs",
        terms: &["obesity", "GLP-1", "semaglutide", "tirzepatide"],
        stored_count: 5058,
    },
    Topic {
        id: "stroke",
        name: "Stroke",
        terms: &["stroke"],
        stored_count: 5391,
    },
];

/// The first publication year a topic library covers (spec goal 1). It also
/// sets the first day walked back to ([`crate::europepmc_first_day`]); the
/// app's screen 4 names the range (a `bml-app` test checks the text).
pub const TOPIC_FIRST_YEAR: i32 = 2021;
/// The last publication year a topic library covers (see
/// [`TOPIC_FIRST_YEAR`]).
pub const TOPIC_LAST_YEAR: i32 = 2026;

/// Peer-reviewed, open access with full text, in the topic years.
fn quality_filter() -> String {
    format!(
        "OPEN_ACCESS:Y AND HAS_FT:Y AND NOT SRC:PPR \
         AND PUB_YEAR:[{TOPIC_FIRST_YEAR} TO {TOPIC_LAST_YEAR}]"
    )
}

/// Trials, systematic reviews and meta-analyses only (spec goal 1).
const EVIDENCE_TYPES: &str = "(PUB_TYPE:\"Randomized Controlled Trial\" OR \
     PUB_TYPE:\"Systematic Review\" OR PUB_TYPE:\"Meta-Analysis\")";

/// The preset with this id.
#[must_use]
pub fn topic(id: &str) -> Option<&'static Topic> {
    TOPICS.iter().find(|t| t.id == id)
}

/// The Europe PMC search for `topic`, without a date clause.
#[must_use]
pub fn topic_query(topic: &Topic) -> String {
    let terms = topic
        .terms
        .iter()
        .map(|t| format!("TITLE:\"{t}\" OR ABSTRACT:\"{t}\""))
        .collect::<Vec<_>>()
        .join(" OR ");
    format!("{} AND ({terms}) AND {EVIDENCE_TYPES}", quality_filter())
}

/// The URL that asks Europe PMC how many papers `topic` matches (one hit).
#[must_use]
pub fn count_url(topic: &Topic) -> String {
    let query = topic_query(topic);
    let params = [
        ("query", query.as_str()),
        ("format", "json"),
        ("pageSize", "1"),
        ("resultType", "lite"),
    ];
    format!("{SEARCH_URL}?{}", encode_query(&params))
}

/// The `hitCount` of a Europe PMC search answer, when it holds a count.
#[must_use]
pub fn parse_hit_count(body: &str) -> Option<u64> {
    serde_json::from_str::<serde_json::Value>(body)
        .ok()?
        .get("hitCount")?
        .as_u64()
}

/// Where a library downloads its papers from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LibrarySource {
    /// medRxiv, paper by paper (every library from before topics).
    Medrxiv,
    /// A Europe PMC topic search.
    EuropePmc {
        /// The preset's id.
        topic_id: String,
        /// The search, as recorded when the topic was chosen.
        query: String,
    },
}

/// The library's source (`library_state.topic_id`; none recorded is medRxiv).
///
/// # Errors
///
/// The database fails.
pub fn library_source(db: &mut dyn Db) -> Result<LibrarySource, PipelineError> {
    let row = fetch_one(
        db,
        &format!(
            "SELECT topic_id, topic_query FROM {LIBRARY_STATE} \
             WHERE id = 1 AND topic_id IS NOT NULL"
        ),
        &[],
    )?;
    Ok(match row {
        Some(row) => LibrarySource::EuropePmc {
            topic_id: row.get_str("topic_id")?.to_string(),
            query: row.get_str("topic_query")?.to_string(),
        },
        None => LibrarySource::Medrxiv,
    })
}

/// Record `topic` as the library's source. Choosing the topic it already has
/// changes nothing; a library holding another topic, or medRxiv papers, is
/// refused in plain words (one library, one source).
///
/// # Errors
///
/// The database fails, or the library already downloads something else.
pub fn set_topic(db: &mut dyn Db, topic: &Topic) -> Result<(), PipelineError> {
    match library_source(db)? {
        LibrarySource::EuropePmc { topic_id, .. } if topic_id == topic.id => return Ok(()),
        LibrarySource::EuropePmc { topic_id, .. } => {
            let held = self::topic(&topic_id).map_or(topic_id.as_str(), |t| t.name);
            return Err(PipelineError::Other(format!(
                "this library already downloads \"{held}\"; a library holds one topic, \
                 so use another library folder for \"{}\"",
                topic.name
            )));
        }
        LibrarySource::Medrxiv => {}
    }
    if fetch_one(db, "SELECT 1 AS held FROM publications LIMIT 1", &[])?.is_some() {
        return Err(PipelineError::Other(format!(
            "this library already holds medRxiv papers; use another library folder \
             for \"{}\"",
            topic.name
        )));
    }
    execute(
        db,
        &format!(
            "INSERT INTO {LIBRARY_STATE} (id, topic_id, topic_query) VALUES (1, ?, ?) \
             ON CONFLICT (id) DO UPDATE SET topic_id = excluded.topic_id, \
             topic_query = excluded.topic_query"
        ),
        &[
            Value::Text(topic.id.to_string()),
            Value::Text(topic_query(topic)),
        ],
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const SPEC_QUERY: &str = "OPEN_ACCESS:Y AND HAS_FT:Y AND NOT SRC:PPR AND PUB_YEAR:[2021 TO 2026] AND (TITLE:\"depression\" OR ABSTRACT:\"depression\" OR TITLE:\"anxiety disorder\" OR ABSTRACT:\"anxiety disorder\") AND (PUB_TYPE:\"Randomized Controlled Trial\" OR PUB_TYPE:\"Systematic Review\" OR PUB_TYPE:\"Meta-Analysis\")";

    #[test]
    fn depression_query_is_the_spec_query() {
        let depression = topic("depression-anxiety").expect("a preset");
        assert_eq!(topic_query(depression), SPEC_QUERY);
    }

    #[test]
    fn ids_are_unique_and_topics_have_terms() {
        let ids: std::collections::BTreeSet<&str> = TOPICS.iter().map(|t| t.id).collect();
        assert_eq!(ids.len(), TOPICS.len());
        assert_eq!(
            TOPICS.iter().map(|t| t.id).collect::<Vec<_>>(),
            ["depression-anxiety", "cardiology", "obesity-glp1", "stroke"]
        );
        assert!(TOPICS
            .iter()
            .all(|t| !t.terms.is_empty() && t.stored_count > 0));
        assert!(topic("nonsense").is_none());
    }

    #[test]
    fn parse_hit_count_reads_the_field() {
        assert_eq!(
            parse_hit_count(r#"{"version":"6.9","hitCount":8372,"resultList":{}}"#),
            Some(8372)
        );
        assert_eq!(parse_hit_count("not json"), None);
        assert_eq!(parse_hit_count(r#"{"resultList":{}}"#), None);
        assert_eq!(parse_hit_count(r#"{"hitCount":"12"}"#), None);
        assert_eq!(parse_hit_count(r#"{"hitCount":-1}"#), None);
    }

    #[test]
    fn count_url_asks_for_one_record() {
        let url = count_url(topic("stroke").expect("a preset"));
        assert!(url.starts_with("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"));
        assert!(url.contains("pageSize=1"), "{url}");
        assert!(url.contains("format=json"), "{url}");
        assert!(!url.contains(' ') && !url.contains('"'), "unencoded: {url}");
        assert!(url.contains("%22stroke%22"), "{url}");
    }
}
