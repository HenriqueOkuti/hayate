"""A reference label set from a panel of teachers: the labels most of them agree on.

Each member gives a page its labels (id and confidence, main label first). The reference for a
page is every label at least `min_votes` members gave, at Tier 2 (the ids as given) and at Tier 1
(each member's labels rolled up first). A page falls in one of four states:
- "agreed": some Tier-2 label has the votes;
- "tier1_only": no Tier-2 label has them, but a Tier-1 category does;
- "none": at least `min_votes` members gave no labels, so the reference is "no topic";
- "split": nothing has the votes. There is no reference, and the page is left out of scoring.
Agreement between models is not accuracy: a mistake the members share is invisible here.
"""

from collections import Counter

from hayate.evaluation.agreement import rollup


def consensus(votes: list[list[dict]], tier1: dict[str, str], min_votes: int = 2) -> dict:
    """The panel's reference for one page from its members' label lists."""

    def winners(member_ids: list[list[str]]) -> list[str]:
        # Most votes first, then the label members rank higher on average. Confidences are not
        # used: members put them on different scales, so a sum would favor the surest member.
        count = Counter(i for ids in member_ids for i in ids)
        rank = Counter({i: 0 for i in count})
        for ids in member_ids:
            for pos, i in enumerate(ids):
                rank[i] += pos
        kept = [i for i, n in count.items() if n >= min_votes]
        return sorted(kept, key=lambda i: (-count[i], rank[i] / count[i], i))

    ids = [list(dict.fromkeys(lab["id"] for lab in labels)) for labels in votes]
    labels2 = winners(ids)
    labels1 = winners([rollup(x, tier1) for x in ids])
    if sum(not x for x in ids) >= min_votes:
        status = "none"
    elif labels2:
        status = "agreed"
    elif labels1:
        status = "tier1_only"
    else:
        status = "split"
    return {"status": status, "labels": labels2, "tier1": labels1}


def has_reference(ref: dict, tier: int) -> bool:
    """Whether a page can be scored at this tier (2: exact labels, 1: rolled up)."""
    return ref["status"] in (("agreed", "none") if tier == 2 else ("agreed", "tier1_only", "none"))
