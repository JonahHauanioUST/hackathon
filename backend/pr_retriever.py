import re
import httpx


async def fetch_pull_requests(
    urls: list[str],
    github_token: str,
) -> list[str]:
    """
    Accepts a list of GitHub PR URLs like:
      https://github.com/owner/repo/pull/123
    Returns a list of formatted strings with PR title, body, and file diffs.
    """
    pattern = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }
    #this does nothing

    results = []
    async with httpx.AsyncClient(timeout=30, headers=headers, verify=False) as client:
        for url in urls:
            match = pattern.search(url)
            if not match:
                results.append(f"[Skipped] Could not parse PR URL: {url}")
                continue

            owner, repo, pr_number = match.groups()
            base = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"

            # Fetch PR metadata
            pr_resp = await client.get(base)
            pr_resp.raise_for_status()
            pr = pr_resp.json()

            # Fetch changed files with patches
            files_resp = await client.get(f"{base}/files")
            files_resp.raise_for_status()
            files = files_resp.json()

            patches = []
            for f in files:
                patch = f.get("patch", "[binary or too large]")
                patches.append(f"--- {f['filename']} ({f['status']}, +{f['additions']} -{f['deletions']})\n{patch}")

            result = (
                f"PR #{pr['number']}: {pr['title']}\n"
                f"Author: {pr['user']['login']}\n"
                f"State: {pr['state']} | Merged: {pr['merged']}\n"
                f"Branch: {pr['head']['ref']} -> {pr['base']['ref']}\n"
                f"Description:\n{pr.get('body') or '(no description)'}\n\n"
                f"Changed files ({len(files)}):\n\n"
                + "\n\n".join(patches)
            )
            results.append(result)
            print('test',results)
    return results


if __name__ == "__main__":
    import asyncio
    import sys
    import ast
    if len(sys.argv) != 3:
        print("Usage: python pr_retriever.py '<urls>' '<token>'")
        sys.exit(1)
    urls_str = sys.argv[1]
    token = sys.argv[2]
    try:
        urls = ast.literal_eval(urls_str)
    except:
        print("Invalid urls format")
        sys.exit(1)
    results = asyncio.run(fetch_pull_requests(urls, token))
    for result in results:
        print(result)
