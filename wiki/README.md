# BMLibrarian Wiki Documentation

This directory contains the source files for the BMLibrarian GitHub Wiki.

## Wiki Structure

The wiki is organized into several main sections:

### For All Users

- **[Home](Home.md)** - Main landing page with navigation
- **[Getting Started](Getting-Started.md)** - Installation and setup
- **[User Guide](User-Guide.md)** - Complete usage guide

### For Developers

- **[Architecture Overview](Architecture-Overview.md)** - System design and components
- **[Plugin Development Guide](Plugin-Development-Guide.md)** - Create Qt GUI plugins (MOST IMPORTANT for contributors)
- **[Contributing](Contributing.md)** - How to contribute to the project

## Using the Wiki

### On GitHub

The GitHub wiki is automatically published at:
`https://github.com/hherb/bmlibrarian/wiki`

To edit the wiki on GitHub:
1. Navigate to the Wiki tab
2. Click "Edit" on any page
3. Make your changes
4. Save with a commit message

### Local Editing

You can also edit wiki files locally in this directory:

1. Edit the Markdown files in `wiki/`
2. Preview changes locally
3. Commit to the repository
4. Manually update the GitHub wiki (or use automated sync)

## File Organization

```
wiki/
├── README.md                      # This file
├── Home.md                        # Wiki home page
├── Getting-Started.md             # Installation and setup
├── User-Guide.md                  # Complete user guide
├── Architecture-Overview.md       # System architecture
├── Plugin-Development-Guide.md    # Plugin development (comprehensive)
├── Contributing.md                # Contributing guidelines
└── ... (additional pages as needed)
```

## Adding New Pages

To add a new wiki page:

1. Create a new Markdown file in this directory (e.g., `My-New-Page.md`)
2. Use kebab-case for the filename (e.g., `Multi-Model-Queries.md`)
3. Add a link to the page from relevant existing pages
4. Update `Home.md` navigation if it's a major page
5. Commit the changes

### Naming Conventions

- Use kebab-case for filenames: `Plugin-Development-Guide.md`
- Use sentence case for page titles: "Plugin Development Guide"
- Match the filename to the page title (with hyphens instead of spaces)

## Markdown Style

### Headers

```markdown
# Page Title (H1 - only one per page)

## Main Section (H2)

### Subsection (H3)

#### Sub-subsection (H4)
```

### Code Blocks

```markdown
\```python
def example():
    return "Use language identifier for syntax highlighting"
\```

\```bash
# Use bash for shell commands
uv run python bmlibrarian_cli.py
\```
```

### Links

```markdown
# Internal wiki links (GitHub auto-converts)
[Getting Started](Getting-Started)
[Plugin Development Guide](Plugin-Development-Guide)

# External links
[BMLibrarian Repository](https://github.com/hherb/bmlibrarian)

# Links to code files
[BaseAgent](../src/bmlibrarian/agents/base.py)
```

### Images

```markdown
# Upload images to wiki and reference them
![Screenshot](images/screenshot.png)

# Or use external URLs
![Diagram](https://example.com/diagram.png)
```

## Documentation Principles

### 1. Clear and Concise

- Use simple language
- Short paragraphs
- Bullet points for lists
- Examples for complex concepts

### 2. Up-to-Date

- Keep documentation synchronized with code
- Update when features change
- Remove outdated information
- Add version numbers when relevant

### 3. Complete

- Cover all major features
- Include prerequisites
- Provide examples
- Link to related pages

### 4. Accessible

- Assume minimal prior knowledge
- Define technical terms
- Provide context
- Multiple learning paths (tutorial, reference, guide)

### 5. Searchable

- Use descriptive headers
- Include keywords
- Cross-reference related content
- Consistent terminology

## Maintenance

### Regular Tasks

- Review wiki pages monthly
- Update for new features
- Fix broken links
- Improve clarity based on user feedback
- Add missing examples

### Before Major Releases

- Review all documentation
- Update version numbers
- Add new features to relevant pages
- Update screenshots
- Test all code examples

## Contributing to the Wiki

See [Contributing](Contributing.md) for general contribution guidelines.

For wiki-specific contributions:

1. **Small changes**: Edit directly on GitHub
2. **Large changes**: Edit locally, preview, then commit
3. **New pages**: Follow structure and naming conventions
4. **Always**: Preview before committing

### Preview Locally

Use a Markdown previewer:

```bash
# Using grip (GitHub Markdown preview)
pip install grip
grip wiki/Home.md

# Using mdv (terminal viewer)
pip install mdv
mdv wiki/Home.md
```

## Wiki Maintenance Team

If you're interested in helping maintain the wiki:

1. Review open documentation issues
2. Fix typos and improve clarity
3. Add examples and screenshots
4. Keep content up-to-date
5. Help answer questions in Discussions

## Questions?

- **General**: [GitHub Discussions](https://github.com/hherb/bmlibrarian/discussions)
- **Documentation Issues**: [GitHub Issues](https://github.com/hherb/bmlibrarian/issues) with `documentation` label
- **Quick Fixes**: Submit a pull request

---

**Thank you for helping improve BMLibrarian documentation!** 📚
