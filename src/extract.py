import requests
import logging
from config import BASE_URL, HEADERS

logger = logging.getLogger(__name__)


def get_repositories(include_languages: bool = True):
    """
    Fetch all user repositories, extracting vital activity timestamps
    and optionally fetching per-repository language byte distributions.
    """
    url = f"{BASE_URL}/user/repos"
    params = {
        "per_page": 100,
        "page": 1,
        "affiliation": "owner,collaborator",
        "sort": "pushed",
        "direction": "desc",
    }
    repos = []

    while True:
        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data:
                break

            repos.extend(data)
            logger.info(f"Fetched page {params['page']}: {len(data)} repos")
            params["page"] += 1

        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                logger.error("Authentication failed. Check GITHUB_TOKEN")
            elif response.status_code == 403:
                logger.error("Rate limit exceeded")
            else:
                logger.error(f"HTTP error: {e}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            raise

    logger.info(f"Total repositories fetched: {len(repos)}")

    # Enrich repos with language byte breakdown if requested
    if include_languages:
        logger.info("Fetching detailed language byte statistics...")
        for repo in repos:
            repo_name = repo.get("full_name")
            lang_url = repo.get("languages_url")
            if not lang_url:
                repo["languages_bytes"] = {}
                continue

            try:
                lang_resp = requests.get(lang_url, headers=HEADERS, timeout=15)
                if lang_resp.status_code == 200:
                    repo["languages_bytes"] = lang_resp.json()
                else:
                    repo["languages_bytes"] = {}
            except Exception as ex:
                logger.warning(f"Could not fetch languages for {repo_name}: {ex}")
                repo["languages_bytes"] = {}

    return repos


def get_user_profile():
    """Fetch profile summary info (public repo counts, followers, account created date)."""
    url = f"{BASE_URL}/user"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Could not fetch user profile info: {e}")
        return {}