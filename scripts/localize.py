import argparse
import json
from pathlib import Path

from graphmem.graph.builder import GraphBuilder
from graphmem.ingestion.scanner import RepositoryScanner
from graphmem.ranking.config import ablation_configs
from graphmem.retrieval.localizer import Localizer


def main():
    configs = ablation_configs()
    ap = argparse.ArgumentParser()
    ap.add_argument("repository")
    ap.add_argument("issue", help="issue text, or @path/to/issue.txt")
    ap.add_argument("--config", default="full", choices=list(configs))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    issue = Path(args.issue[1:]).read_text() if args.issue.startswith("@") else args.issue

    parsed = RepositoryScanner(args.repository).parse()
    graph = GraphBuilder().build(parsed)
    result = Localizer(graph).localize(issue, args.top_k, configs[args.config])
    data = result.to_dict()

    if args.json:
        print(json.dumps(data, indent=2))
        return

    print(f"config={data['config']}  total={data['timings_ms']['total']}ms\n")
    for c in data["candidates"][: args.top_k * 3]:
        print(f"{c['score']:.3f}  {c['file']}:{c['start_line']}-{c['end_line']}  [{c['scope']}]")
        for e in c["evidence"]:
            print(f"        - {e['type']}: {e['source']} ({e['weight']})")


if __name__ == "__main__":
    main()