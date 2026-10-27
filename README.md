# VFX Lead Generation Pipeline

A repeatable pipeline for finding and qualifying decision-makers at AI-forward production companies (film, VFX, animation, advertising and virtual production), and recording them in a shared Google Sheet.

Qualification is governed by three standard operating procedures in [`SOP/`](SOP):

| SOP | Scope |
|---|---|
| [SOP 01](SOP/SOP_01_Account_Opportunity_Qualification.md) | Account and opportunity qualification: is the company a real production business that uses generative AI in its own work? |
| [SOP 02](SOP/SOP_02_Decision_Owner_Discovery_Qualification.md) | Decision-owner discovery: who owns the problem, and is their current role and employment confirmed? |
| [SOP 03](SOP/SOP_03_Independent_Validation_Reachability_Outreach_Readiness.md) | Independent validation, reachability and outreach readiness. |

## How it works

```
 company discovery ──► AI-use pre-filter ──► company verification ──► people discovery ──► person verification ──► Google Sheet
 (Tavily search)       (homepage + subpages)  (SOP 01, agent review)    (Apify lead finder)   (SOP 02/03, agent review)   (de-duplicated append)
```

1. **Discover** candidate companies with web search ([`tavily_search.py`](pipeline/tavily_search.py)).
2. **Pre-filter** by fetching each site and keeping only those that mention generative-AI use ([`ai_prefilter.py`](pipeline/ai_prefilter.py), then [`ai_subpage_check.py`](pipeline/ai_subpage_check.py) for sites that only mention AI on inner pages).
3. **Find people** at the surviving companies with the Apify lead finder, rotating across a token pool ([`lead_harvest.py`](pipeline/lead_harvest.py)).
4. **Verify** companies and people against the SOPs. The review prompts used for this step are in [`docs/agent_playbooks`](docs/agent_playbooks).
5. **Append** qualified rows to the Google Sheet with cross-tab de-duplication ([`common.py`](pipeline/common.py)).

### Hard rules applied throughout

- Approved-country list only; India is excluded for both companies and people.
- AI tool/SaaS vendors, publishers, broadcasters, educators and consultancies are rejected: only companies that *produce* content and *use* generative AI in their own client work qualify.
- Every row needs a personal LinkedIn URL and a sourced evidence link.
- No person appears twice; at most three contacts per company.

## Repository layout

```
SOP/                    Qualification procedures (SOP 01 to 03)
pipeline/               Python modules: discovery, crawling, filtering, harvesting, key checks, Sheets I/O
docs/SETUP_AND_RUN_PROMPT.md   Prompt for an operator: setup, key rolling, Apify limits, duplicates, edge cases
docs/prompts/           One prompt per stage (companies, people, validation, sheet writes) plus a cycle overview
docs/agent_playbooks/   Review prompts for company and person verification
.env.example            Required configuration (names only, no values)
requirements.txt        Python dependencies
```

Modules in `pipeline/`:

| Module | Purpose |
|---|---|
| `common.py` | Shared helpers: approved countries, role filters, Sheets I/O, Apify runner, de-duplication |
| `check_keys.py` | Live balance check of every Apify/Tavily key; writes the usable pool |
| `maps_harvest.py` | Google Maps company discovery with AI-worded, local-language searches |
| `build_universe.py` | Merges harvests into one entry per company domain |
| `company_crawl.py` | Visits each company site and scores generative-AI evidence |
| `ai_prefilter.py`, `ai_subpage_check.py` | Homepage and inner-page AI-use filters |
| `lead_harvest.py` | Lead-finder people harvest with key rotation |
| `tavily_search.py` | Web search with key rotation |

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your own values
set -a && source .env && set +a
```

To run the pipeline end to end, give your AI assistant [`docs/SETUP_AND_RUN_PROMPT.md`](docs/SETUP_AND_RUN_PROMPT.md).

Configuration is read from environment variables only (see [`.env.example`](.env.example)). Credentials, API keys, lead exports and working data are deliberately **not** stored in this repository; `data/` is git-ignored.

## Data handling

This repository contains code and procedures only. Lead data, contact details and API credentials live outside version control (the Google Sheet and a local, git-ignored `data/` folder) and must never be committed.
