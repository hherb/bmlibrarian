# Fulltext discovery, retrieval and processing

- Presently, BMLibrarian works only wir=th document abstracts. The database however already contains all URLs from unpaywall and other sources and allows retrieval of fulltext. This should be integrated into the workflow.

- additionally, we could use library proxies (if the user has any) in order to retrieve fulltexts. 

- many abstracts already have full texts in our database, eg nearly everything from medrxiv. This needs to be used already

---

# Source discovery

- once we have fulltext available, we can trace back any statements to their original primary source, and reject secondary sources. This should be integrated into the workflow.

---

# Source rating

- once we have fulltext available, we can properly analyzeq to rate the quality of the evidence. This should be integrated into the workflow. ULtimately, the analysis should mimmick a proper systematic peer review process. This is best done on the postgres server side at the time of document import as a background process once the process is validated