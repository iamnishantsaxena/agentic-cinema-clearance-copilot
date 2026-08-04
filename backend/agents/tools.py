from parallel import AsyncParallel

from backend.config import PARALLEL_API_KEY

_client = AsyncParallel(api_key=PARALLEL_API_KEY)


def make_research_tool(seen_urls: set[str]):
    """Builds a research_entity_web tool bound to `seen_urls`, which
    collects every URL Parallel actually returned. The researcher agent's
    citations are later filtered against this set so a model can never cite
    a URL that wasn't genuinely surfaced by search."""

    async def research_entity_web(objective: str, search_queries: list[str]) -> dict:
        """Search the live web for the current legal/clearance status of a
        screenplay entity (trademark status, litigation, right-of-publicity
        risk, recent news). Use this before assessing risk for any entity —
        clearance status changes over time and cannot be answered from memory.

        Args:
            objective: what you're trying to find out about this entity, e.g.
                "Is 'Bridge Over Troubled Water' under active copyright and
                who controls sync licensing?"
            search_queries: 2-4 concrete web search queries to answer the
                objective.
        """
        result = await _client.search(
            objective=objective,
            search_queries=search_queries,
            mode="advanced",
            max_chars_total=6000,
        )
        results = [
            {
                "url": r.url,
                "title": r.title,
                "excerpts": r.excerpts,
                "publish_date": r.publish_date,
            }
            for r in result.results
        ]
        seen_urls.update(r["url"] for r in results)
        return {"results": results}

    return research_entity_web
