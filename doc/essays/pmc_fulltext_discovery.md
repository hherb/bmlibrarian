# The Journey to Full-Text: Discovering PMC's Hidden Treasures

*An essay on debugging PDF discovery and finding unexpected riches in biomedical literature archives*

**November 2024**

---

## The Bug That Started It All

It began, as many discoveries do, with something broken. A simple PDF download failure for PMC article 11052067 — a paper about metformin and the liver. The actual URL was right there: `https://pmc.ncbi.nlm.nih.gov/articles/PMC11052067/pdf/metabolites-14-00186.pdf`. Why couldn't we find it?

The error logs told a familiar story of software entropy: the code was looking in the wrong place. PMC had migrated from `www.ncbi.nlm.nih.gov/pmc` to `pmc.ncbi.nlm.nih.gov`, and our resolvers hadn't kept up. A simple fix, one might think. Change the domain, move on.

But the new domain had other ideas.

## The Bot That Wasn't Welcome

The first surprise came when Python's `requests` library returned HTTP 403 — Forbidden. The same URL that worked perfectly in a browser was blocking our code. NCBI had implemented bot detection on their new infrastructure, and we looked suspiciously robotic.

The solution was almost embarrassingly simple: shell out to `curl`. Whatever magic the command-line tool possessed — perhaps its venerable User-Agent string, perhaps something deeper in its implementation — NCBI's servers accepted it without complaint. Not elegant, but functional.

## The Proof of Work Challenge

The browser-based fallback presented a more interesting puzzle. When Playwright navigated to the PDF URL, instead of a document, we received an HTML page titled "Preparing to download..." with a cryptic JavaScript payload. PMC had implemented a Proof of Work (PoW) challenge — similar to Cloudflare's protection, but custom-built.

The challenge worked like this:
1. First navigation serves JavaScript that performs cryptographic calculations
2. Upon completion, a cookie named `cloudpmc-viewer-pow` is set
3. Second navigation, with the cookie present, triggers the actual download

This is a clever defense against bulk scrapers while remaining transparent to human users (whose browsers execute the JavaScript automatically). For our purposes, it meant waiting for the cookie and navigating twice — a small price for legitimate access.

## The Unexpected Discovery

With the download working, we turned to the PMC Open Access service to understand the source landscape. The OA API (`oa.fcgi`) returns metadata about available formats for each article. We expected PDF links. What we found was more interesting.

```
Articles with direct PDF links: ~2 million
Articles with tar.gz packages: ~7.3 million
```

Seven million articles with packages, but only two million with direct PDFs? What was in these packages?

```
PMC11052067/
├── metabolites-14-00186.pdf      (1.4 MB)
├── metabolites-14-00186.nxml     (structured full text)
├── metabolites-14-00186-g001.jpg
├── metabolites-14-00186-g001.gif
├── metabolites-14-00186-g002.jpg
└── metabolites-14-00186-g002.gif
```

The NXML file. There it was — the full structured text of the article in JATS XML format (Journal Article Tag Suite), the standard for biomedical publishing. Not just the abstract that we store in our database, but the complete article: introduction, methods, results, discussion, everything.

## JATS XML: The Librarian's Dream

JATS XML is what happens when librarians design a data format. Every element of a scientific article is tagged with semantic meaning:

```xml
<article-title>Metformin and the Liver: Unlocking the Full Therapeutic Potential</article-title>
<abstract>
  <p>Metformin is a highly effective medication...</p>
</abstract>
<body>
  <sec sec-type="intro">
    <title>Introduction</title>
    <p>Type 2 diabetes mellitus (T2DM) is a growing...</p>
  </sec>
  ...
</body>
```

This structure enables things that plain text cannot: section-aware search, citation graph analysis, figure extraction, and — crucially for our AI agents — understanding the logical flow of an argument.

We built a parser that walks this structure and extracts clean, readable text with Markdown formatting preserved:

```markdown
# Metformin and the Liver: Unlocking the Full Therapeutic Potential

## Abstract

Metformin is a highly effective medication for managing type 2 diabetes mellitus...

## Introduction

Type 2 diabetes mellitus (T2DM) is a growing public health concern...
```

52,691 characters of full text from a single article — vastly more useful than the 500-word abstract we previously had access to.

## The Offline Library

This discovery had immediate practical implications. One of our users works primarily in remote Indigenous communities with sporadic internet access. They have time for literature research but limited connectivity. Could we build an offline library?

The answer was already there, hiding in plain sight on NCBI's FTP servers.

PMC provides bulk download access through baseline packages — complete snapshots of their Open Access collection, split by license type and PMCID range. The commercial-use subset (CC BY, CC0, etc.) alone contains millions of articles, each with PDF and full-text NXML.

We built a CLI that:
- Downloads packages with configurable rate limiting (polite to NCBI's servers)
- Tracks progress and supports resumption (essential for unreliable connections)
- Extracts PDFs and NXML to organized directories
- Imports metadata and full text into the local database

```bash
# Before going to the field
uv run python pmc_bulk_cli.py sync --license oa_comm

# Returns: 7.3 million articles, ready for offline access
```

For a researcher in a remote clinic, this transforms what's possible. The entire open-access biomedical literature, searchable and readable without an internet connection.

## Lessons Learned

**1. Debug failures thoroughly.** The initial bug led us to discover bot detection, PoW challenges, and ultimately the existence of full-text packages we didn't know we could access.

**2. Read the documentation.** NCBI's FTP service documentation describes the bulk download options in detail. We just hadn't looked because we didn't know we needed to.

**3. The gap between "available" and "accessible" is real.** 7.3 million articles were technically available via tar.gz, but our code only knew how to request direct PDF links. The data existed; we just hadn't built the bridge.

**4. Infrastructure changes break things.** PMC's domain migration was routine maintenance for them, but it broke downstream systems that had hardcoded the old URL. This is why we now use configurable constants and test against live services.

**5. Browser automation is sometimes necessary.** For sites with sophisticated anti-bot protection, there's no substitute for a real browser environment. The PoW challenge couldn't be solved any other way.

## The Road Ahead

The full-text capability opens new possibilities for our AI agents:

- **Citation extraction** can now work from complete papers, not just abstracts
- **Fact-checking** can verify claims against the methods and results sections
- **Systematic reviews** can assess methodological quality from full descriptions
- **Semantic search** can find relevant passages anywhere in an article

We've also exposed the gap in our existing document collection. Millions of PubMed articles in our database have only abstracts. For those in PMC's Open Access subset, we can now retrieve the full text — a project for future work.

## Conclusion

What started as a simple bug fix — updating a URL from one domain to another — became a journey through bot detection, cryptographic challenges, XML parsing, and bulk data infrastructure. We ended with capabilities we didn't know we were missing: full-text access for millions of articles and an offline library for remote work.

The lesson, perhaps, is that bugs are gifts. They force us to look closely at systems we take for granted, and sometimes what we find there is more valuable than what we were originally looking for.

---

*This essay documents the development of PMC full-text discovery in BMLibrarian, November 2024. The code changes are preserved in commits `4bcbaa9` (PMC domain migration and PoW handling), `827ede2` (tar.gz package extraction), and `7f5a7b2` (bulk download CLI).*
