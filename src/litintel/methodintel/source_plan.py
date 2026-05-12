from litintel.methodintel.schema import RouterMode, SourceType


def build_source_plan(mode: RouterMode) -> list[SourceType]:
    """Create an auditable source plan for a routed MethodIntel question."""
    base = [SourceType.EXISTING_METHODINTEL, SourceType.NOTION_PAGES]

    if mode == RouterMode.LEARN_METHOD:
        return base + [
            SourceType.ORIGINAL_PAPERS,
            SourceType.BENCHMARK_PAPERS,
            SourceType.OFFICIAL_DOCS,
        ]

    if mode == RouterMode.COMPARE_METHODS:
        return base + [
            SourceType.BENCHMARK_PAPERS,
            SourceType.ORIGINAL_PAPERS,
            SourceType.OFFICIAL_DOCS,
        ]

    if mode == RouterMode.CHOOSE_FOR_DATASET:
        return base + [
            SourceType.BENCHMARK_PAPERS,
            SourceType.OFFICIAL_DOCS,
            SourceType.RECENT_REVIEWS,
        ]

    if mode == RouterMode.STAGE_OVERVIEW:
        return base + [
            SourceType.BENCHMARK_PAPERS,
            SourceType.RECENT_REVIEWS,
            SourceType.OFFICIAL_DOCS,
        ]

    if mode == RouterMode.STALENESS_CHECK:
        return base + [
            SourceType.RECENT_REVIEWS,
            SourceType.OFFICIAL_DOCS,
            SourceType.GITHUB_REPOS,
            SourceType.BENCHMARK_PAPERS,
            SourceType.ORIGINAL_PAPERS,
        ]

    return base + [SourceType.BROAD_WEB_FALLBACK]

