# GitHub Repository Data Collector

This project collects public GitHub repository metadata using the GitHub REST API. It is designed for a data acquisition assignment where the data source must be an API or web scraping.

## Research Question

What are the characteristics of popular GitHub repositories matching a chosen topic, language, organization, or keyword?

Example questions:

- Which programming languages are most common among highly starred repositories about data visualization?
- Which repositories dominate a topic such as machine learning, cybersecurity, or web scraping?
- How do stars, forks, open issues, licenses, and update dates vary across repositories?

## Data Source

- API: GitHub REST API
- Endpoint: `GET https://api.github.com/search/repositories`
- Documentation:
  - Search repositories: https://docs.github.com/en/rest/search/search
  - REST API pagination: https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api
  - REST API rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
  - API versions: https://docs.github.com/en/rest/about-the-rest-api/api-versions

## Collected Fields

The script exports these fields to `repositories.csv`:

- Repository identity: `id`, `full_name`, `name`, `html_url`
- Owner information: `owner_login`, `owner_type`
- Popularity metrics: `stargazers_count`, `forks_count`, `watchers_count`
- Activity metrics: `open_issues_count`, `created_at`, `updated_at`, `pushed_at`
- Repository descriptors: `description`, `language`, `topics`, `license`, `default_branch`, `visibility`
- Data collection metadata: `collected_at`, `query`, `rank`

## Setup

Python 3.10+ is recommended. The collector uses only the Python standard library, so there are no required packages to install.

Optional but recommended: create a GitHub personal access token and set it as an environment variable. This increases the API rate limit for authenticated requests.

```bash
export GITHUB_TOKEN="YOUR_TOKEN_HERE"
```

For public repositories, a token does not need special repository permissions.

## How to Run

From this folder:

```bash
python3 collector.py \
  --query "topic:data-visualization language:python stars:>100" \
  --max-results 100 \
  --sort stars \
  --order desc \
  --out-dir data
```

Then run the summary script:

```bash
python3 analyze.py data/repositories.csv
```

## Example Queries

```bash
python3 collector.py --query "topic:machine-learning language:python stars:>500" --max-results 100
python3 collector.py --query "web scraping language:python stars:>100" --max-results 100
python3 collector.py --query "org:openai" --max-results 50 --sort updated
python3 collector.py --query "data acquisition language:javascript stars:>50" --max-results 100
```

## Output Files

The collector writes three files into the output directory:

- `repositories.csv`: cleaned tabular data for analysis
- `repositories_raw.json`: raw API responses, including response headers
- `metadata.json`: query, endpoint, API version, collection time, and count metadata

## Methodology

1. Build a GitHub repository search query using keywords and qualifiers.
2. Send requests to the GitHub REST API with `q`, `sort`, `order`, `per_page`, and `page` parameters.
3. Use pagination to collect multiple result pages.
4. Flatten nested JSON fields such as `owner`, `license`, and `topics`.
5. Save raw JSON for reproducibility and CSV for analysis.
6. Summarize the cleaned CSV by language, owner type, stars, forks, and top repositories.

## Limitations and Ethics

- The Search API returns public repository data only unless authenticated access is added.
- Search results reflect GitHub's ranking and indexing at collection time.
- Very broad searches can return many matches, but API search endpoints expose a limited result window.
- The script uses delays and rate-limit headers to avoid excessive requests.
- Do not publish private tokens. Keep `GITHUB_TOKEN` in your environment, not in source code.

## Short Report Template

Use this structure for your assignment write-up:

1. Introduction: Explain why GitHub repositories are useful for studying open-source software trends.
2. Data Source: Describe the GitHub REST API and the repository search endpoint.
3. Acquisition Method: Explain query parameters, pagination, API headers, and optional token authentication.
4. Data Fields: List key fields such as stars, forks, language, license, topics, and timestamps.
5. Data Cleaning: Explain how nested JSON was flattened into CSV.
6. Results: Include summary statistics from `analyze.py`.
7. Limitations: Discuss rate limits, search ranking, public-data scope, and time sensitivity.
8. Conclusion: State what the collected data suggests about the chosen topic.
