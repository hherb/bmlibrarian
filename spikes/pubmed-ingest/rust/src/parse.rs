//! A faithful port of `PubMedBulkImporter._parse_article` (ElementTree semantics).
//!
//! Each `<PubmedArticle>` is sliced out of the decompressed file and parsed as a
//! small DOM with roxmltree. The helpers below reproduce ElementTree's `find`,
//! `findall`, `findtext`, `.text` and `.tail` so the output can be diffed
//! against the Python parser field by field. Known quirks of the Python code
//! (keywords searched under `Article`, DOI search reaching into the reference
//! list, retraction corrections searched under `PubmedData`) are reproduced on
//! purpose: this spike measures speed, so both sides must do the same work.

use memchr::memmem;
use roxmltree::{Document, Node};
use serde_json::{Map, Value, json};

const ARTICLE_OPEN: &[u8] = b"<PubmedArticle>";
const ARTICLE_CLOSE: &[u8] = b"</PubmedArticle>";
const RETRACTED_TYPES: [&str; 2] = ["retracted publication", "retraction of publication"];
const RETRACTION_REF_TYPES: [&str; 2] = ["retractionin", "retractionof"];

/// One parsed article (the fields the Python importer stores).
#[derive(Debug, Clone, Default)]
pub struct Article {
    pub pmid: String,
    pub doi: Option<String>,
    pub title: String,
    pub abstract_md: String,
    pub authors: Vec<String>,
    pub publication: Option<String>,
    pub publication_date: Option<String>,
    pub mesh_terms: Vec<String>,
    pub keywords: Vec<String>,
    pub grants: Vec<Grant>,
    pub publication_types: Vec<String>,
    pub is_retracted: bool,
    pub affiliations: Vec<(String, Vec<String>)>,
}

/// One `<Grant>` entry.
#[derive(Debug, Clone, Default)]
pub struct Grant {
    pub agency: Option<String>,
    pub grant_id: Option<String>,
    pub country: Option<String>,
}

/// Byte ranges of every `<PubmedArticle>…</PubmedArticle>` element in `xml`.
pub fn article_slices(xml: &[u8]) -> Vec<&[u8]> {
    let open = memmem::Finder::new(ARTICLE_OPEN);
    let close = memmem::Finder::new(ARTICLE_CLOSE);
    let mut out = Vec::new();
    let mut pos = 0;
    while let Some(start) = open.find(&xml[pos..]) {
        let start = pos + start;
        let Some(end) = close.find(&xml[start..]) else { break };
        let end = start + end + ARTICLE_CLOSE.len();
        out.push(&xml[start..end]);
        pos = end;
    }
    out
}

/// Parse one article slice; `None` mirrors Python returning `None` (skipped).
pub fn parse_article(slice: &[u8]) -> Result<Option<Article>, String> {
    let text = std::str::from_utf8(slice).map_err(|e| e.to_string())?;
    let doc = Document::parse(text).map_err(|e| e.to_string())?;
    Ok(parse_root(doc.root_element()))
}

fn parse_root(root: Node) -> Option<Article> {
    let medline = find(root, &["MedlineCitation"])?;
    let pmid = findtext(medline, &["PMID"]).filter(|s| !s.is_empty())?.to_string();
    let article = find(medline, &["Article"])?;

    let title = formatted(find(article, &["ArticleTitle"]));
    let abstract_md = abstract_markdown(find(article, &["Abstract"]));

    let mut authors = Vec::new();
    let mut affiliations = Vec::new();
    for author in findall(article, &["AuthorList", "Author"]) {
        let last = child_text_or_empty(author, "LastName");
        let first = child_text_or_empty(author, "ForeName");
        let name = format!("{last} {first}").trim().to_string();
        if !last.is_empty() || !first.is_empty() {
            authors.push(name.clone());
        }
        if name.is_empty() {
            continue;
        }
        let affs: Vec<String> = findall(author, &["AffiliationInfo", "Affiliation"])
            .into_iter()
            .filter_map(|a| et_text(a).filter(|t| !t.is_empty()).map(str::to_string))
            .collect();
        if !affs.is_empty() {
            affiliations.push((name, affs));
        }
    }

    let publication = findtext(article, &["Journal", "Title"]).map(str::to_string);
    let publication_date = extract_date(find(article, &["Journal", "JournalIssue", "PubDate"]));

    let pubmed_data = find(root, &["PubmedData"]);
    let doi = pubmed_data.and_then(|pd| {
        findall(pd, &["ArticleIdList", "ArticleId"])
            .into_iter()
            .find(|id| id.attribute("IdType") == Some("doi"))
            .and_then(|id| et_text(id).map(str::to_string))
    });

    let mesh_terms = texts(findall(medline, &["MeshHeadingList", "MeshHeading", "DescriptorName"]));
    let keywords = texts(findall(article, &["KeywordList", "Keyword"]));

    let mut grants = Vec::new();
    for grant in findall(article, &["GrantList", "Grant"]) {
        let g = Grant {
            agency: findtext(grant, &["Agency"]).map(str::to_string),
            grant_id: findtext(grant, &["GrantID"]).map(str::to_string),
            country: findtext(grant, &["Country"]).map(str::to_string),
        };
        if truthy(&g.agency) || truthy(&g.grant_id) {
            grants.push(g);
        }
    }

    let publication_types = texts(findall(article, &["PublicationTypeList", "PublicationType"]));
    let mut is_retracted = publication_types
        .iter()
        .any(|t| RETRACTED_TYPES.contains(&t.to_lowercase().as_str()));
    if let Some(pd) = pubmed_data {
        for c in findall(pd, &["CommentsCorrectionsList", "CommentsCorrections"]) {
            let ref_type = c.attribute("RefType").unwrap_or("").to_lowercase();
            if RETRACTION_REF_TYPES.contains(&ref_type.as_str()) {
                is_retracted = true;
            }
        }
    }

    Some(Article {
        pmid,
        doi,
        title,
        abstract_md,
        authors,
        publication,
        publication_date,
        mesh_terms,
        keywords,
        grants,
        publication_types,
        is_retracted,
        affiliations,
    })
}

fn truthy(v: &Option<String>) -> bool {
    v.as_deref().is_some_and(|s| !s.is_empty())
}

fn texts(nodes: Vec<Node>) -> Vec<String> {
    nodes
        .into_iter()
        .filter_map(|n| et_text(n).filter(|t| !t.is_empty()).map(str::to_string))
        .collect()
}

/// ElementTree `.text`: the text node before the first child element.
fn et_text<'a>(node: Node<'a, '_>) -> Option<&'a str> {
    node.first_child().filter(|c| c.is_text()).and_then(|c| c.text())
}

/// ElementTree `.tail`: the text node right after this element.
fn et_tail<'a>(node: Node<'a, '_>) -> Option<&'a str> {
    node.next_sibling().filter(|c| c.is_text()).and_then(|c| c.text())
}

fn element_children<'a, 'i>(node: Node<'a, 'i>) -> impl Iterator<Item = Node<'a, 'i>> {
    node.children().filter(Node::is_element)
}

/// ElementTree `findall('.//a/b/c')`: descendants (not self) named `a`, then child path.
fn findall<'a, 'i>(node: Node<'a, 'i>, path: &[&str]) -> Vec<Node<'a, 'i>> {
    let (head, rest) = path.split_first().expect("non-empty path");
    let mut current: Vec<Node> = node
        .descendants()
        .skip(1)
        .filter(|n| n.is_element() && n.tag_name().name() == *head)
        .collect();
    for step in rest {
        current = current
            .into_iter()
            .flat_map(|n| element_children(n).filter(move |c| c.tag_name().name() == *step))
            .collect();
    }
    current
}

/// ElementTree `find('.//a/b')`: the first match in document order.
fn find<'a, 'i>(node: Node<'a, 'i>, path: &[&str]) -> Option<Node<'a, 'i>> {
    if path.len() == 1 {
        return node
            .descendants()
            .skip(1)
            .find(|n| n.is_element() && n.tag_name().name() == path[0]);
    }
    let mut all = findall(node, path);
    // findall's flat_map keeps document order within each ancestor; sort to be safe.
    all.sort_by_key(|n| n.range().start);
    all.into_iter().next()
}

/// ElementTree `findtext('.//a/b')`: text of the first match ("" if empty), None if absent.
fn findtext<'a>(node: Node<'a, '_>, path: &[&str]) -> Option<&'a str> {
    find(node, path).map(|n| et_text(n).unwrap_or(""))
}

/// `elem.findtext('Child', '')` for a direct child.
fn child_text_or_empty<'a>(node: Node<'a, '_>, name: &str) -> &'a str {
    element_children(node)
        .find(|c| c.tag_name().name() == name)
        .map(|c| et_text(c).unwrap_or(""))
        .unwrap_or("")
}

/// Direct-child `findtext(name, default)`.
fn child_findtext<'a>(node: Node<'a, '_>, name: &str, default: &'a str) -> Option<&'a str> {
    match element_children(node).find(|c| c.tag_name().name() == name) {
        Some(c) => Some(et_text(c).unwrap_or("")),
        None => Some(default),
    }
}

/// Port of `_get_element_text_with_formatting`.
pub fn formatted(node: Option<Node>) -> String {
    let Some(node) = node else { return String::new() };
    if element_children(node).next().is_none() {
        return et_text(node).unwrap_or("").trim().to_string();
    }
    let mut out = String::new();
    if let Some(t) = et_text(node) {
        out.push_str(t);
    }
    for child in element_children(node) {
        let inner = formatted(Some(child));
        match child.tag_name().name().to_lowercase().as_str() {
            "b" | "bold" => out.push_str(&format!("**{inner}**")),
            "i" | "italic" => out.push_str(&format!("*{inner}*")),
            "sup" => out.push_str(&format!("^{inner}^")),
            "sub" => out.push_str(&format!("~{inner}~")),
            "u" | "underline" => out.push_str(&format!("__{inner}__")),
            _ => out.push_str(&inner),
        }
        if let Some(t) = et_tail(child) {
            out.push_str(t);
        }
    }
    out.trim().to_string()
}

/// Port of `_format_abstract_markdown`.
fn abstract_markdown(abstract_elem: Option<Node>) -> String {
    let Some(abs) = abstract_elem else { return String::new() };
    let mut parts = Vec::new();
    for at in findall(abs, &["AbstractText"]) {
        let mut label = at.attribute("Label").unwrap_or("").trim().to_string();
        if label.is_empty() {
            let cat = at.attribute("NlmCategory").unwrap_or("").trim();
            if !cat.is_empty() && cat != "UNASSIGNED" && cat != "UNLABELLED" {
                label = cat.to_string();
            }
        }
        let text = formatted(Some(at));
        if text.is_empty() {
            continue;
        }
        if label.is_empty() {
            parts.push(text);
        } else {
            parts.push(format!("**{}:** {text}", label.to_uppercase()));
        }
    }
    parts.join("\n\n")
}

/// Port of `_extract_date` (string form, including its quirks).
fn extract_date(pub_date: Option<Node>) -> Option<String> {
    let pd = pub_date?;
    let year = child_findtext(pd, "Year", "").filter(|y| !y.is_empty())?;
    // Year present-but-missing returns the default "", which Python treats as falsy.
    if element_children(pd).all(|c| c.tag_name().name() != "Year") {
        return None;
    }
    let mut month = child_findtext(pd, "Month", "01").unwrap_or("01").to_string();
    let mut day = child_findtext(pd, "Day", "01").unwrap_or("01").to_string();
    let month_num = match month.as_str() {
        "Jan" => Some("01"), "Feb" => Some("02"), "Mar" => Some("03"), "Apr" => Some("04"),
        "May" => Some("05"), "Jun" => Some("06"), "Jul" => Some("07"), "Aug" => Some("08"),
        "Sep" => Some("09"), "Oct" => Some("10"), "Nov" => Some("11"), "Dec" => Some("12"),
        _ => None,
    };
    if let Some(m) = month_num {
        month = m.to_string();
    } else if month.chars().count() == 1 {
        month = format!("0{month}");
    }
    if day.chars().count() == 1 {
        day = format!("0{day}");
    }
    Some(format!("{year}-{month}-{day}"))
}

/// The article as the same JSON the Python parity dump writes.
pub fn to_json(a: &Article) -> Value {
    let mut meta = Map::new();
    if !a.grants.is_empty() {
        meta.insert(
            "grants".into(),
            Value::Array(
                a.grants
                    .iter()
                    .map(|g| json!({"agency": g.agency, "grant_id": g.grant_id, "country": g.country}))
                    .collect(),
            ),
        );
    }
    if !a.publication_types.is_empty() {
        meta.insert("publication_types".into(), json!(a.publication_types));
    }
    meta.insert("is_retracted".into(), json!(a.is_retracted));
    if !a.affiliations.is_empty() {
        meta.insert(
            "author_affiliations".into(),
            Value::Array(
                a.affiliations
                    .iter()
                    .map(|(n, affs)| json!({"author": n, "affiliations": affs}))
                    .collect(),
            ),
        );
    }
    json!({
        "pmid": a.pmid, "doi": a.doi, "title": a.title, "abstract": a.abstract_md,
        "authors": a.authors, "publication": a.publication,
        "publication_date": a.publication_date,
        "url": format!("https://pubmed.ncbi.nlm.nih.gov/{}/", a.pmid),
        "mesh_terms": a.mesh_terms, "keywords": a.keywords,
        "transparency_metadata": Value::Object(meta),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(xml: &str) -> Article {
        parse_article(xml.as_bytes()).unwrap().unwrap()
    }

    const MIN: &str = r#"<PubmedArticle><MedlineCitation><PMID>42</PMID><Article>
        <Journal><JournalIssue><PubDate><Year>2020</Year><Month>Mar</Month><Day>5</Day></PubDate></JournalIssue><Title>J Test</Title></Journal>
        <ArticleTitle>CO<sub>2</sub> and <i>E. coli</i> </ArticleTitle>
        <Abstract><AbstractText Label="Background">Some <b>bold</b> text.</AbstractText>
        <AbstractText NlmCategory="UNASSIGNED">Plain.</AbstractText></Abstract>
        <AuthorList><Author><LastName>Smith</LastName><ForeName>J</ForeName>
        <AffiliationInfo><Affiliation>Uni A</Affiliation></AffiliationInfo></Author>
        <Author><CollectiveName>Group</CollectiveName></Author></AuthorList>
        <PublicationTypeList><PublicationType>Retracted Publication</PublicationType></PublicationTypeList>
        </Article></MedlineCitation>
        <PubmedData><ArticleIdList><ArticleId IdType="pubmed">42</ArticleId></ArticleIdList>
        <ReferenceList><Reference><ArticleIdList><ArticleId IdType="doi">10.1/ref</ArticleId></ArticleIdList></Reference></ReferenceList>
        </PubmedData></PubmedArticle>"#;

    #[test]
    fn formatting_and_abstract_match_python_rules() {
        let a = parse(MIN);
        assert_eq!(a.title, "CO~2~ and *E. coli*");
        assert_eq!(a.abstract_md, "**BACKGROUND:** Some **bold** text.\n\nPlain.");
        assert_eq!(a.publication_date.as_deref(), Some("2020-03-05"));
        assert_eq!(a.authors, vec!["Smith J"]);
        assert_eq!(a.affiliations, vec![("Smith J".to_string(), vec!["Uni A".to_string()])]);
        assert!(a.is_retracted);
    }

    #[test]
    fn reproduces_python_quirk_doi_from_reference_list() {
        assert_eq!(parse(MIN).doi.as_deref(), Some("10.1/ref"));
    }

    #[test]
    fn slices_articles() {
        let xml = format!("<PubmedArticleSet>{MIN}{MIN}</PubmedArticleSet>");
        assert_eq!(article_slices(xml.as_bytes()).len(), 2);
    }
}
